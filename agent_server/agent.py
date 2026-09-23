import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain.agents.middleware import (
    PIIMiddleware,
    TodoListMiddleware,
    wrap_model_call,
    wrap_tool_call,
)
from databricks_langchain import ChatDatabricks
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemPermission

from agent_server.backends import VolumeBackend
from agent_server.tools import get_current_time, init_mcp_client, jakarta_workspace_client, days_until, roll_dice

logger = logging.getLogger(__name__)

# Kept as prose in its own file so the agent's instructions can be edited and
# reviewed without touching Python. Read once at import, as a constant would be.
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system_prompt.md").read_text()

# Appended to the prompt for the length of a run that has no SQL tool. Losing
# the tool is not the dangerous part; answering anyway is. Without this the
# model reads its own instruction to query the table, finds nothing that can,
# and improvises — inventing tool names, delegating to a subagent that cannot
# help either, and sometimes producing a figure that looks measured. Telling it
# plainly that the tool is gone turns that into one honest sentence.
NO_SQL_NOTICE = """

# This run has no SQL tool

The Databricks SQL tool could not be offered for this run: {reason}

You therefore cannot read the ticket table at all, and nothing else in your
tool list can substitute for it — `execute` has no backend here, and a subagent
has no tools you lack. No skill can supply the data either; a skill carries
method, not figures.

Say that the ticket data is not available for this run, name the reason above,
and stop. Do not estimate, do not reason from a figure given earlier in the
conversation, and do not present anything as measured.
"""

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILLS_MOUNT = "/skills/"

# The two halves of the wiki tier. Both are subdirectories of one Unity Catalog
# Volume; the prefix, not the storage, is what states provenance.
WIKI_SOURCE_MOUNT = "/wiki/raw/"
WIKI_NOTES_MOUNT = "/wiki/notes/"
WIKI_SOURCE_SUBDIR = "raw"
WIKI_NOTES_SUBDIR = "notes"

# Chosen by measurement, not preference: of the open-weight endpoints served
# here, this is the one that actually uses the planning tool. See design
# Decision 9 of `migrate-to-deep-agent`.
MODEL_ENDPOINT = "databricks-glm-5-3-flash" # TODO: 1. LLM Selection

# OKF §7 actor convention: `<producer>/<version>` for an agent. Recorded in
# `generated.by` on every note the agent writes, so a reader can tell which
# model produced a durable claim — and tell it apart from a `human:` actor,
# which is what OKF's trust tiers key off.
OKF_ACTOR = f"agent-ptmn-training/{MODEL_ENDPOINT}"


# Mirrors `SKILLS_ALL`. The two selection points are meant to be edited the
# same way, so they take the same three kinds of argument.
TOOLS_ALL = "__all__"

_mcp_tools: Optional[list[Any]] = None
_mcp_tools_lock = asyncio.Lock()

# Why the SQL tool is absent, or None while it is present. Set on every
# resolution attempt, so a server that recovers mid-session stops warning.
_mcp_unavailable: Optional[str] = None

# Staging directories by fingerprint — the selection plus the modification
# times of the files in it. Nothing is ever removed from here: a directory an
# in-flight turn still has mounted must outlive the turn that replaced it.
_staged: dict[tuple, Path] = {}


async def mcp_tools(names: Union[str, Sequence[str]] = TOOLS_ALL) -> list[Any]:
    """The MCP tools this run offers the model — `names` of them, discovered once.

    Both routes call `init_agent()` per request, and discovery is an
    `initialize` plus `tools/list` round trip to a server in another region —
    too much to put in front of every turn. The tool list is static, so cache
    it. A failure is not cached, so an unreachable server at startup degrades
    this run rather than the whole process.

    Skill staging is cached too, but on a different key and for a different
    reason. It looks like the same problem and is not: this is a network call
    to another region, that is a write to local disk. What it has to avoid is
    accumulating a copy of the tree per turn — and, because the files can
    change under it, it keys on their contents rather than caching outright.
    See `stage_skills`.

    Selection is applied to the cached list on the way out, never before it is
    stored. Caching the *selection* would bake the first request's choice into
    the process — and because `init_agent()` runs per request, that only shows
    up on the second, differing call.
    """
    global _mcp_tools, _mcp_unavailable
    if _mcp_tools is not None:
        return _select_tools(_mcp_tools, names)
    async with _mcp_tools_lock:
        if _mcp_tools is None:
            # Client construction is inside the try, not before it: building a
            # WorkspaceClient validates its config and raises on a bad or
            # missing host, so leaving it outside turned an unreachable remote
            # into a 500 from the route rather than a degraded run.
            #
            # Degrading is still right — an agent that cannot reach one remote
            # should answer what it can. What was wrong was degrading *quietly*:
            # the reason went to a log nobody was reading while the model, which
            # is the one component that needed to know, was told nothing. Both
            # paths now record why, and `init_agent` puts that reason in the
            # prompt. See `NO_SQL_NOTICE`.
            try:
                client = init_mcp_client()
                if client is None:
                    _mcp_unavailable = (
                        "DATABRICKS_JAKARTA_* is not configured for this process"
                    )
                    logger.error(
                        "NO SQL TOOL: %s. The agent will not be able to read the "
                        "ticket table this run.",
                        _mcp_unavailable,
                    )
                    return []
                tools = await client.get_tools()
            except Exception as exc:
                _mcp_unavailable = (
                    f"the dbsql MCP server could not be reached "
                    f"({type(exc).__name__})"
                )
                logger.error(
                    "NO SQL TOOL: %s. The agent will not be able to read the "
                    "ticket table this run.",
                    _mcp_unavailable,
                    exc_info=True,
                )
                return []
            logger.info("Resolved %d MCP tools: %s", len(tools), [t.name for t in tools])
            _mcp_tools = tools
            _mcp_unavailable = None
    return _select_tools(_mcp_tools, names)


def _select_tools(discovered: Sequence[Any], names: Union[str, Sequence[str]]) -> list[Any]:
    """The named subset of what the server offers, in the order asked for.

    Unknown names raise, for the reason `stage_skills` raises: a typo that
    silently drops a tool changes the agent's behaviour with nothing in the
    logs pointing at the cause. This runs only once the server has answered —
    an unreachable server returns early, above, and degrades rather than
    raising, which is the older and more important rule.
    """
    if names == TOOLS_ALL:
        selected = list(discovered)
    else:
        available = {t.name: t for t in discovered}
        if unknown := [n for n in names if n not in available]:
            raise ValueError(
                f"No MCP tool named {unknown} on the SQL server; "
                f"available: {sorted(available)}"
            )
        selected = [available[n] for n in names]
    logger.info("Tools mounted (%d): %s", len(selected), [t.name for t in selected])
    return selected


SKILLS_ALL = "__all__"


def _fingerprint(selected: Sequence[str], available: dict[str, Path]) -> tuple:
    """What a staged copy is a copy *of* — the selection and the files' mtimes.

    Cheap enough to run per request: a stat walk over a few dozen markdown
    files costs far less than the `copytree` it saves. Modification time rather
    than a content hash on purpose — this exists to notice an edit between two
    turns of a demo, not to defend against anything.
    """
    return tuple(
        (
            name,
            max(
                (p.stat().st_mtime_ns for p in available[name].rglob("*") if p.is_file()),
                default=0,
            ),
        )
        for name in selected
    )


def stage_skills(names: Union[str, Sequence[str]]) -> Optional[Path]:
    """Copy the selected skills into a staging directory, and return it.

    The skills middleware takes a *directory* and reads every skill under it,
    so a subset cannot be expressed at the mount. Staging makes the selection
    explicit at the call site instead, which is where a reader looks to find
    out what the agent was given — and keeps the repository's `skills/` tree
    the catalogue rather than the configuration.

    Copying rather than symlinking: the mount resolves paths against its root,
    and a link out of that root is the kind of thing a backend is entitled to
    refuse. Eight markdown files cost nothing to copy.

    Returns `None` when nothing is selected, which is a supported state — an
    agent without skills answers from the standing instructions alone.
    """
    available = (
        {p.parent.name: p.parent for p in SKILLS_DIR.glob("*/SKILL.md")}
        if SKILLS_DIR.is_dir()
        else {}
    )
    selected = sorted(available) if names == SKILLS_ALL else list(names)

    # Loudly, at startup. A typo that silently drops a skill is a change in
    # behaviour that no test and no log line would attribute to its cause.
    if unknown := [n for n in selected if n not in available]:
        raise ValueError(
            f"No skill named {unknown} under {SKILLS_DIR}; "
            f"available: {sorted(available)}"
        )

    if not selected:
        logger.info("No skills selected — continuing without them.")
        return None

    # `init_agent()` runs per request, so staging unconditionally would leave a
    # copy of the tree behind per turn. Reuse instead — but keyed on the files'
    # modification times, not just on the selection, so that editing a
    # `SKILL.md` reaches the next turn without restarting the server. That is
    # what makes this tier demonstrable.
    #
    # A superseded directory is left on disk rather than removed. The evaluation
    # harness runs several turns at once (`agent_evaluation/runner.py`,
    # `--concurrency`, default 4), and each holds its directory mounted for the
    # length of its turn; deleting the one it is reading from would fail its
    # skill reads silently and depress the very score the run reports. Growth is
    # therefore bounded by the number of *edits* in a session, not by traffic.
    key = _fingerprint(selected, available)
    staged = _staged.get(key)
    if staged is None or not staged.is_dir():
        staged = Path(tempfile.mkdtemp(prefix="agent-skills-"))
        for name in selected:
            shutil.copytree(available[name], staged / name)
        _staged[key] = staged
    logger.info("Skills mounted (%d): %s", len(selected), selected)
    return staged


# The SQL tools, named so a turn's answer can be traced back to whether any of
# them actually ran. Kept beside `UNUSABLE_BUILTINS` because both describe what
# the tool list means rather than what it contains.
SQL_TOOL_NAMES = frozenset({"execute_sql", "poll_sql_result"})

# Edit these two lines to change what a reader sees; nothing else depends on
# their wording.
PROVENANCE_SOURCED = "\n\n— Sumber: {n} query SQL dijalankan pada giliran ini."
PROVENANCE_UNSOURCED = (
    "\n\n— ⚠ Sumber: TIDAK ADA query yang dijalankan pada giliran ini. "
    "Jawaban di atas tidak bersandar pada data tiket."
)

# Sent to the model, never written to state. Phrased to be answerable both ways:
# a question that needs data is sent to get it, and one that does not is sent to
# say so, so a correct refusal is not argued out of itself.
PROVENANCE_NUDGE = (
    "Kamu menjawab tanpa memanggil tool apa pun pada giliran ini, jadi jawaban "
    "itu belum bersandar pada data. Jika jawabanmu memuat angka atau pernyataan "
    "tentang isi tabel tiket, jalankan query untuk memastikannya — jangan "
    "mengandalkan jawaban dari giliran sebelumnya. Jika pertanyaan ini memang "
    "tidak membutuhkan data tiket, tidak apa-apa. "
    "Apa pun pilihanmu, tulis ulang jawaban untuk pertanyaan pengguna secara "
    "utuh dan berdiri sendiri. Jangan menyebut, membahas, atau menjawab pesan "
    "ini — pengguna tidak melihatnya."
)


def _turn_start(messages: Sequence[Any]) -> int:
    """Index of the last thing the person said — where this turn begins.

    Everything downstream is scoped to the turn, not the thread, and that is
    the point. A model that answers a later question from an earlier answer's
    figures runs no query of its own; counting over the thread would credit it
    with the first question's work and hide the failure this exists to show.
    """
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return 0


def _sql_results(messages: Sequence[Any], start: int) -> int:
    """Successful SQL results in this turn.

    Results rather than calls, so a statement the warehouse rejected does not
    read as a source.
    """
    return sum(
        1
        for m in messages[start:]
        if isinstance(m, ToolMessage)
        and m.name in SQL_TOOL_NAMES
        and getattr(m, "status", None) != "error"
    )


def _used_any_tool(messages: Sequence[Any], start: int) -> bool:
    """Whether the model reached for anything at all this turn."""
    return any(getattr(m, "tool_calls", None) for m in messages[start:])


def _append_note(content: Any, note: str) -> Any:
    """Add a line to a message whose content may be text or a block list."""
    if isinstance(content, str):
        return content + note
    if isinstance(content, list):
        return [*content, {"type": "text", "text": note}]
    return content


@wrap_model_call
async def record_query_provenance(request, handler):
    """Send an unexamined answer back once, then state what stood behind it.

    Two mechanisms, and the split between them is deliberate.

    **The note** reports the one thing that is decidable — whether a query ran
    — and leaves the judgement to the reader. It is not a refusal: deciding
    from the text whether a figure was invented means regexing digits, and
    `P1`, `2026` and any number quoted back from the question all trip it.
    Counting tool results has no false positives.

    **The bounce** is narrower, and aimed at one failure: answering with no
    tool call at all. That is what a model does when it answers a later
    question from an earlier answer in the same conversation — the shape six
    questions asked in one sitting will actually take. It is asked to look, or
    to say why looking is unnecessary; a question that genuinely needs no data,
    such as one the role should decline, passes on the second pass by saying so.

    The bounce fires only when the turn made *no* tool call, which is also what
    bounds it: after it, any tool call at all disqualifies the turn from being
    bounced again, so at most one extra model call is ever spent. A turn that
    worked but never reached SQL gets the note and no bounce — it examined
    something, and the note already says what.

    The nudge is passed to the model, not written to state, so it never reaches
    the transcript, the next turn, or the person reading the answer.
    """
    start = _turn_start(request.messages)
    response = await handler(request)
    messages = getattr(response, "result", None)
    if not messages:
        return response

    final = messages[-1]
    # Only the turn's last message: an AIMessage carrying tool calls is still
    # working, and a note appended there would be read back to the model as
    # though the model had written it.
    if not isinstance(final, AIMessage) or final.tool_calls:
        return response

    ran = _sql_results(request.messages, start)
    if (
        ran == 0
        and not _used_any_tool(request.messages, start)
        # Nothing to go back for when the tool is not there at all; the prompt
        # already carries `NO_SQL_NOTICE` in that case.
        and _mcp_unavailable is None
    ):
        retry = request.override(
            messages=[*request.messages, final, HumanMessage(content=PROVENANCE_NUDGE)]
        )
        response = await handler(retry)
        messages = getattr(response, "result", None) or [final]
        final = messages[-1]
        if not isinstance(final, AIMessage) or final.tool_calls:
            return response
        ran = _sql_results(request.messages, start)

    note = PROVENANCE_SOURCED.format(n=ran) if ran else PROVENANCE_UNSOURCED
    final.content = _append_note(final.content, note)
    return response


# langchain's built-in email pattern ends `[A-Z|a-z]{2,}` — a character class
# that literally contains a pipe, almost certainly meant as alternation. A pipe
# straight after the TLD is therefore part of the match. That was harmless while
# the SQL server returned JSON; `system.ai.dbsql` returns markdown tables, so
# every address now swallows its own column separator and, mid-row, the next
# cell's value with it. The same person then hashes two ways and the grouping
# that `strategy="hash"` exists to preserve is lost.
#
# Identical to the upstream pattern but for that class. See
# `test_a_pipe_separator_is_swallowed_upstream`.
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"


# Built-in tools this deployment cannot honour. `execute` needs a backend
# implementing `SandboxBackendProtocol`, which this agent does not have, so it
# fails every time it is called. `task` delegates to a subagent built from the
# same tool list, so it can only return the caller's own problem restated.
#
# Both are reached for hardest at exactly the wrong moment: when the SQL tool
# is missing, a model looking for a way to run a query finds two entries that
# sound like one. Offering a tool that cannot work is worse than offering none.
UNUSABLE_BUILTINS = frozenset({"execute", "task"})


@wrap_model_call
async def hide_unusable_tools(request, handler):
    """Keep tools this deployment cannot honour out of the model's list.

    Filtered at the request rather than removed at construction because the
    built-in suite is assembled inside `create_deep_agent`; passing `tools=`
    there is additive and never removes one.

    Async for the same reason as `mark_skill_reads`: the agent is only ever
    driven by `astream`, and a sync hook is not registered as the async one.
    """
    offered = [t for t in request.tools if getattr(t, "name", None) not in UNUSABLE_BUILTINS]
    if len(offered) != len(request.tools):
        request = request.override(tools=offered)
    return await handler(request)


# Backoff for a rate-limited SQL endpoint. Doubling from a second, so the three
# waits total seven — long enough to clear a burst, short enough that a person
# waiting on an answer does not conclude the agent has hung.
RATE_LIMIT_BACKOFF = (1.0, 2.0, 4.0)


def _is_rate_limited(exc: BaseException, depth: int = 0) -> bool:
    """Whether this failure is the SQL endpoint asking to be called less often.

    Matched on the response where one is attached and on the text otherwise,
    because the exception arrives through the MCP client rather than from an
    HTTP call this code made, and its type is not guaranteed.

    Recursive because the MCP client runs its transport in a task group, so the
    429 arrives wrapped: `str()` on the group is "unhandled errors in a
    TaskGroup (1 sub-exception)" and says nothing about the status. Matching
    only the outer layer is why the first version of this never fired.
    """
    if depth > 3:
        return False
    if getattr(getattr(exc, "response", None), "status_code", None) == 429:
        return True
    if "429" in str(exc):
        return True
    for inner in (*(getattr(exc, "exceptions", None) or ()), exc.__cause__):
        if inner is not None and _is_rate_limited(inner, depth + 1):
            return True
    return False


@wrap_tool_call
async def retry_rate_limited(request, handler):
    """Wait and retry when the SQL endpoint returns 429.

    The managed MCP SQL endpoint rate-limits, and a refusal there arrives as an
    exception that kills the whole turn: the evaluation lost roughly two items a
    run to it, and a person asking a question would simply get nothing back. A
    burst is transient by definition, so waiting is the correct response and the
    only one that keeps the answer.

    Deliberately narrow. Any other failure is returned untouched on the first
    attempt, because retrying a statement the warehouse rejected would only
    reject it again more slowly.
    """
    for wait in (*RATE_LIMIT_BACKOFF, None):
        try:
            return await handler(request)
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is a 429
            if wait is None or not _is_rate_limited(exc):
                raise
            logger.warning(
                "Rate limited on %s; retrying in %.0fs",
                request.tool_call.get("name"), wait,
            )
            await asyncio.sleep(wait)


@wrap_tool_call
async def mark_skill_reads(request, handler):
    """Label a skill read where a person can see it, in the log and in the UI.

    A skill is read with `read_file`, the same tool that serves the wiki, so
    neither the trace nor the chat UI distinguishes the two by name. The
    prefix restores that distinction without a second tool and without a
    frontend change: the UI renders tool output expanded by default.

    Async because the agent is only ever driven by `astream`; a sync hook is
    not registered as the async one and raises on the first tool call.
    """
    path = str((request.tool_call.get("args") or {}).get("file_path", ""))
    response = await handler(request)
    if path.startswith(SKILLS_MOUNT):
        name = path[len(SKILLS_MOUNT):].split("/")[0]
        logger.info(">>> SKILL SELECTED: %s", name)
        # A handler may return a Command rather than a ToolMessage; only a
        # message carries text to prefix.
        if isinstance(getattr(response, "content", None), str):
            response.content = f"[SKILL: {name}]\n{response.content}"
    return response


def wiki_routes(client: Optional[Any] = None) -> dict[str, Any]:
    """The two wiki routes, or nothing when the Volume is not configured.

    Both tiers are subdirectories of a single Volume, reached with the same
    Jakarta credentials as the SQL tools. The grant is therefore uniform and
    read-only on `/wiki/raw/` is *not* enforced by it — a UC volume grant
    is per-volume, not per-path. The deny rule in `filesystem_permissions()` is
    what refuses the write, which makes that rule load-bearing rather than
    defence in depth.

    Absence is a supported state, not a failure: the course is taught on
    laptops that may not hold the credential, and an agent that refuses to
    start without a wiki is worse than one that starts without the tier.

    `client` is injectable so a caller can supply one. Constructing a
    `WorkspaceClient` is not free or reliably fast — a wrong host sends the SDK
    into an authentication retry that blocks rather than raising — so the
    construction is guarded and a failure degrades this run to no tier.
    """
    volume = os.environ.get("DATABRICKS_WIKI_VOLUME")
    if not volume:
        logger.info(
            "DATABRICKS_WIKI_VOLUME not set — continuing without the /wiki/ tier."
        )
        return {}
    if client is None:
        try:
            client = jakarta_workspace_client()
        except Exception:
            logger.warning(
                "Could not build a client for the wiki Volume. "
                "Continuing without the /wiki/ tier.",
                exc_info=True,
            )
            return {}
    if client is None:
        logger.info(
            "DATABRICKS_WIKI_VOLUME is set but DATABRICKS_JAKARTA_* is not — "
            "continuing without the /wiki/ tier."
        )
        return {}
    return {
        WIKI_SOURCE_MOUNT: VolumeBackend(client, volume, WIKI_SOURCE_SUBDIR),
        # No write-time identity guard on this tier: the check it used was
        # removed with `agent_server/privacy.py`. Durable writes are covered
        # only by the system prompt and, for the main agent, by the fact that
        # `PIIMiddleware` pseudonymises identities before the model sees them.
        WIKI_NOTES_MOUNT: VolumeBackend(
            client,
            volume,
            WIKI_NOTES_SUBDIR,
            # The write path supplies OKF frontmatter itself. Asking the prompt
            # for it would make conformance a matter of good behaviour; this
            # makes it a property of the tier.
            okf_actor=OKF_ACTOR,
        ),
    }


def build_backend(skills_root: Optional[Path] = None, wiki_client: Optional[Any] = None) -> CompositeBackend:
    """The agent's filesystem, tiered so a path prefix states a file's lifetime,
    who wrote it, and whether the agent may write there.

        /                  turn-scoped scratch, discarded with the thread
        /skills/           read-only, from the repository, changes only by merge
        /wiki/raw/    read-only, synced from OpenWiki, an OKF bundle
        /wiki/notes/       durable, agent-written, shared across users

    The default is state rather than local disk on purpose. An agent writing
    scratch files onto a container's ephemeral filesystem has produced something
    that looks durable and is not; keeping the default in state makes the
    lifetime honest and the prefix makes it visible.

    Note that `/wiki/` itself is not a route. A bare `/wiki/…` path falls
    through to scratch, so a file only becomes durable at a prefix that says
    which of the two tiers it belongs to.
    """
    routes: dict[str, Any] = {}
    if skills_root is not None:
        # virtual_mode mounts a real directory at a virtual path beneath the
        # composite. The general caution against a local-filesystem backend is
        # about agent-writable disk; this mount is read-only by the permission
        # rule in `init_agent`.
        routes[SKILLS_MOUNT] = FilesystemBackend(
            root_dir=skills_root, virtual_mode=True
        )
    routes.update(wiki_routes(wiki_client))
    logger.info("Filesystem tiers: / (scratch), %s", ", ".join(sorted(routes)) or "none")
    return CompositeBackend(default=StateBackend(), routes=routes)


def filesystem_permissions() -> list[FilesystemPermission]:
    """Deny writes under the skills mount and the synced wiki source.

    Telling the agent not to edit its own instructions is not a control. A rule
    that refuses the write is, and it holds against an injected instruction as
    well as against an agent's own initiative — which is the point of keeping
    skills in the repository, where a change to them has to pass review.

    The same rule covers `/wiki/raw/` for a different reason. Content a
    person authored in an internal system should change in that system, not
    through the agent. Here the rule is the *only* thing enforcing that: the
    Volume grant covers both subdirectories, so a gap in this list is a
    correctness bug and not a missing hardening measure.
    """
    return [
        FilesystemPermission(
            operations=["write"],
            paths=[f"{SKILLS_MOUNT}**", f"{WIKI_SOURCE_MOUNT}**"],
            mode="deny",
        )
    ]


async def init_agent(flag_pii: bool = True, show_provenance: bool = True):
    """Build the agent.

    `flag_pii=False` is for evaluation only: with the net on, a scored run
    would be measuring the net rather than the model and every privacy item
    would pass unconditionally. The net is covered by unit tests instead.
    """

    middlewares = [
        TodoListMiddleware(),
        retry_rate_limited,
        mark_skill_reads,
        hide_unusable_tools,
    ]
    if show_provenance:
        # Off for scored runs: the note ends up inside the answer text, and the
        # numeric scorers read figures out of that text. The evaluation measures
        # tool use through the trace instead, which is where it belongs.
        middlewares.append(record_query_provenance)
    if flag_pii:
        # Upstream of generation: a streamed answer is gone before `after_model`.
        middlewares.append(
            PIIMiddleware(
                "email",
                strategy="hash",
                detector=EMAIL_PATTERN,
                apply_to_input=True,
                apply_to_output=True,
                apply_to_tool_results=True,
            )
        )

    # TODO 3: Tool Selection:
    # TOOLS_ALL                              every tool the SQL server offers
    # ["execute_sql", "poll_sql_result"]     only the ones named — least privilege
    # []                                     none; the agent cannot read the table
    #
    # execute_sql and poll_sql_result are a pair: a slow statement returns a
    # statement_id that only poll_sql_result can collect. Selecting the first
    # without the second works until a query is slow, then strands the model.
    sql_tools = await mcp_tools(TOOLS_ALL)

    # Tell the model when it has no way to run a query — either the server is
    # unreachable, or this run did not select `execute_sql`. If it's told nothing, it
    # invents a figure instead of saying it cannot look.
    no_sql = _mcp_unavailable or (
        None
        if any(getattr(t, "name", None) == "execute_sql" for t in sql_tools)
        else "no tool that can run a query was selected for this run"
    )
    system_prompt = SYSTEM_PROMPT
    if no_sql:
        system_prompt += NO_SQL_NOTICE.format(reason=no_sql)

    # TODO 4: Skill Selection:
    # SKILLS_ALL            every skill in skills/
    # ["skill-a", ...]      only the ones named — least privilege
    # []                    none; the agent answers from the prompt alone
    skills_root = stage_skills(SKILLS_ALL)

    return create_deep_agent(
        model=ChatDatabricks(endpoint=MODEL_ENDPOINT),
        system_prompt=system_prompt,
        tools=[
            # 1. Manually Defined Tools: get_current_time, days_until, roll_dice
            get_current_time,
            # days_until,
            # roll_dice,

            # 2. Databricks Managed MCP: SQL (as defined by TODO 3)
            *sql_tools,

            # 3. Databricks Managed MCP: UC Functions
            # least privilege function URL with specified scope
            # /api/2.0/mcp/functions/{catalog}/{schema}/{function}
        ],

        # Skills as defined by TODO 4
        skills=[SKILLS_MOUNT] if skills_root else None,
        backend=build_backend(skills_root),
        permissions=filesystem_permissions(),

        middleware=middlewares,
    )

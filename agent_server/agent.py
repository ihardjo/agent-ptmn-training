import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from langchain.agents.middleware import PIIMiddleware, TodoListMiddleware, wrap_tool_call
from databricks_langchain import ChatDatabricks
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemPermission

from agent_server.backends import VolumeBackend
from agent_server.tools import get_current_time, init_mcp_client, jakarta_workspace_client, print_hello_world

logger = logging.getLogger(__name__)

# Kept as prose in its own file so the agent's instructions can be edited and
# reviewed without touching Python. Read once at import, as a constant would be.
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system_prompt.md").read_text()

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
MODEL_ENDPOINT = "databricks-qwen35-122b-a10b" # TODO: 1. LLM Selection

# OKF §7 actor convention: `<producer>/<version>` for an agent. Recorded in
# `generated.by` on every note the agent writes, so a reader can tell which
# model produced a durable claim — and tell it apart from a `human:` actor,
# which is what OKF's trust tiers key off.
OKF_ACTOR = f"agent-ptmn-training/{MODEL_ENDPOINT}"


_mcp_tools: Optional[list[Any]] = None
_mcp_tools_lock = asyncio.Lock()

# Staging directories by fingerprint — the selection plus the modification
# times of the files in it. Nothing is ever removed from here: a directory an
# in-flight turn still has mounted must outlive the turn that replaced it.
_staged: dict[tuple, Path] = {}


async def mcp_tools(names: Optional[Sequence[str]] = None) -> list[Any]:
    """MCP tools, discovered once per process.

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
    """
    global _mcp_tools
    if _mcp_tools is not None:
        return _mcp_tools
    async with _mcp_tools_lock:
        if _mcp_tools is None:
            # Client construction is inside the try, not before it: building a
            # WorkspaceClient validates its config and raises on a bad or
            # missing host, so leaving it outside turned an unreachable remote
            # into a 500 from the route rather than a degraded run.
            try:
                client = init_mcp_client()
                if client is None:
                    return []
                tools = await client.get_tools()
            except Exception:
                logger.warning(
                    "Could not reach the jakarta-sql MCP server. "
                    "Continuing without its tools.",
                    exc_info=True,
                )
                return []
            logger.info("Resolved %d MCP tools: %s", len(tools), [t.name for t in tools])
            _mcp_tools = tools
    return _mcp_tools


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


async def init_agent(flag_pii: bool = True):
    """Build the agent.

    `flag_pii=False` is for evaluation only: with the net on, a scored run
    would be measuring the net rather than the model and every privacy item
    would pass unconditionally. The net is covered by unit tests instead.
    """

    middlewares = [TodoListMiddleware(), mark_skill_reads]
    if flag_pii:
        # Upstream of generation: a streamed answer is gone before `after_model`.
        middlewares.append(
            PIIMiddleware(
                "email",
                strategy="hash",
                apply_to_input=True,
                apply_to_output=True,
                apply_to_tool_results=True,
            )
        )

    # TODO 4: Skill Selection:
    # SKILLS_ALL          every skill in skills/
    # ["skill-a", ...]    only the ones named — least privilege
    # []                  none; the agent answers from the prompt alone
    skills_root = stage_skills(SKILLS_ALL)
    
    return create_deep_agent(
        model=ChatDatabricks(endpoint=MODEL_ENDPOINT),
        system_prompt=SYSTEM_PROMPT,

        # TODO 3: Tool Selection:
        tools=[
            # 1. get_current_time()
            get_current_time,

            # 2. print_hello_world()
            print_hello_world,

            # 3. Databricks Managed MCP: SQL
            # in bulk — everything this server offers
            *await mcp_tools(),

            # one-by-one — comment out the splat above and uncomment this:
            # *only(await mcp_tools(), ["execute_sql_read_only", "poll_sql_result"]),

            # 4. Databricks Managed MCP: UC Functions
            # least privilege function URL with specified scope
            # /api/2.0/mcp/functions/{catalog}/{schema}/{function}
        ],

        skills=[SKILLS_MOUNT] if skills_root else None,
        backend=build_backend(skills_root),
        permissions=filesystem_permissions(),

        middleware=middlewares,
    )

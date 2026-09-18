import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from databricks_langchain import ChatDatabricks
from langchain.agents.middleware import TodoListMiddleware
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemPermission

from agent_server.backends import VolumeBackend
from agent_server.tools import init_mcp_client, jakarta_workspace_client

logger = logging.getLogger(__name__)

# Kept as prose in its own file so the agent's instructions can be edited and
# reviewed without touching Python. Read once at import, as a constant would be.
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system_prompt.md").read_text()

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILLS_MOUNT = "/skills/"

# The two halves of the wiki tier. Both are subdirectories of one Unity Catalog
# Volume; the prefix, not the storage, is what states provenance.
WIKI_SOURCE_MOUNT = "/wiki/openwiki/"
WIKI_NOTES_MOUNT = "/wiki/notes/"
WIKI_SOURCE_SUBDIR = "openwiki"
WIKI_NOTES_SUBDIR = "notes"

# Chosen by measurement, not preference: of the open-weight endpoints served
# here, this is the one that actually uses the planning tool. See design
# Decision 9 of `migrate-to-deep-agent`.
MODEL_ENDPOINT = "databricks-qwen35-122b-a10b"

# OKF §7 actor convention: `<producer>/<version>` for an agent. Recorded in
# `generated.by` on every note the agent writes, so a reader can tell which
# model produced a durable claim — and tell it apart from a `human:` actor,
# which is what OKF's trust tiers key off.
OKF_ACTOR = f"agent-ptmn-training/{MODEL_ENDPOINT}"


_mcp_tools: Optional[list[Any]] = None
_mcp_tools_lock = asyncio.Lock()


async def mcp_tools() -> list[Any]:
    """MCP tools, discovered once per process.

    Both routes call `init_agent()` per request, and discovery is an
    `initialize` plus `tools/list` round trip to a server in another region —
    too much to put in front of every turn. The tool list is static, so cache
    it. A failure is not cached, so an unreachable server at startup degrades
    this run rather than the whole process.

    Skill discovery is deliberately *not* cached this way. The two look like the
    same problem and are not: this is a network call to another region, that is
    a read of files on local disk.
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


def _skills_present() -> bool:
    """Whether there is a skills directory holding at least one skill.

    Checked rather than assumed: the deployed copy and a working tree are not
    guaranteed to look alike, and an agent that cannot start because a directory
    is missing is worse than one that starts without skills.
    """
    return SKILLS_DIR.is_dir() and any(SKILLS_DIR.glob("*/SKILL.md"))


def wiki_routes(client: Optional[Any] = None) -> dict[str, Any]:
    """The two wiki routes, or nothing when the Volume is not configured.

    Both tiers are subdirectories of a single Volume, reached with the same
    Jakarta credentials as the SQL tools. The grant is therefore uniform and
    read-only on `/wiki/openwiki/` is *not* enforced by it — a UC volume grant
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
        # The privacy guard lives on the writable tier only. A durable file
        # outlives the reply that prompted it and is readable by users who never
        # asked the question, so it is the wider disclosure, not the narrower.
        WIKI_NOTES_MOUNT: VolumeBackend(
            client,
            volume,
            WIKI_NOTES_SUBDIR,
            forbid_person_names=True,
            # The write path supplies OKF frontmatter itself. Asking the prompt
            # for it would make conformance a matter of good behaviour; this
            # makes it a property of the tier.
            okf_actor=OKF_ACTOR,
        ),
    }


def build_backend(wiki_client: Optional[Any] = None) -> CompositeBackend:
    """The agent's filesystem, tiered so a path prefix states a file's lifetime,
    who wrote it, and whether the agent may write there.

        /                  turn-scoped scratch, discarded with the thread
        /skills/           read-only, from the repository, changes only by merge
        /wiki/openwiki/    read-only, synced from OpenWiki, an OKF bundle
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
    if _skills_present():
        # virtual_mode mounts a real directory at a virtual path beneath the
        # composite. The general caution against a local-filesystem backend is
        # about agent-writable disk; this mount is read-only by the permission
        # rule in `init_agent`.
        routes[SKILLS_MOUNT] = FilesystemBackend(
            root_dir=SKILLS_DIR, virtual_mode=True
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

    The same rule covers `/wiki/openwiki/` for a different reason. Content a
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


async def init_agent():
    skills = [SKILLS_MOUNT] if _skills_present() else None
    if skills:
        logger.info(
            "Loaded %d skill(s) from %s: %s",
            len(list(SKILLS_DIR.glob("*/SKILL.md"))),
            SKILLS_DIR,
            sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")),
        )
    else:
        logger.info("No skills found under %s — continuing without them.", SKILLS_DIR)

    return create_deep_agent(
        # `gpt-oss-120b` never called `write_todos` on a multi-step question
        # even when told to plan first, so the deep loop cost turns without
        # buying the capability. See `MODEL_ENDPOINT`.
        model=ChatDatabricks(endpoint=MODEL_ENDPOINT),
        tools=await mcp_tools(),
        system_prompt=SYSTEM_PROMPT,
        backend=build_backend(),
        skills=skills,
        permissions=filesystem_permissions(),
        # Planning is not part of `create_deep_agent` in deepagents 0.7.15 — it
        # provides delegation, the filesystem, and skills, but no todo tool, so
        # without this the agent cannot record a plan at all. The middleware
        # lives upstream in langchain now.
        middleware=[TodoListMiddleware()],
    )

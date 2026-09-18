import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from databricks_langchain import ChatDatabricks
from langchain.agents.middleware import TodoListMiddleware
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemPermission

from agent_server.tools import init_mcp_client

logger = logging.getLogger(__name__)

# Kept as prose in its own file so the agent's instructions can be edited and
# reviewed without touching Python. Read once at import, as a constant would be.
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system_prompt.md").read_text()

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SKILLS_MOUNT = "/skills/"


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


def build_backend() -> CompositeBackend:
    """The agent's filesystem, tiered so a path prefix states a file's lifetime.

        /          turn-scoped scratch, discarded with the thread
        /skills/   read-only, mounted from the repository, changes only by merge

    The default is state rather than local disk on purpose. An agent writing
    scratch files onto a container's ephemeral filesystem has produced something
    that looks durable and is not; keeping the default in state makes the
    lifetime honest and the prefix makes it visible.

    The `/wiki/` tier — durable, agent-written knowledge on a Unity Catalog
    Volume — is a later change. It routes here the same way.
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
    return CompositeBackend(default=StateBackend(), routes=routes)


def skill_permissions() -> list[FilesystemPermission]:
    """Deny writes under the skills mount.

    Telling the agent not to edit its own instructions is not a control. A rule
    that refuses the write is, and it holds against an injected instruction as
    well as against an agent's own initiative — which is the point of keeping
    skills in the repository, where a change to them has to pass review.
    """
    return [
        FilesystemPermission(
            operations=["write"], paths=[f"{SKILLS_MOUNT}**"], mode="deny"
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
        # Chosen by measurement, not preference: of the open-weight endpoints
        # served here, this is the one that actually uses the planning tool.
        # `gpt-oss-120b` never called `write_todos` on a multi-step question
        # even when told to plan first, so the deep loop cost turns without
        # buying the capability. See design Decision 9.
        model=ChatDatabricks(endpoint="databricks-qwen35-122b-a10b"),
        tools=await mcp_tools(),
        system_prompt=SYSTEM_PROMPT,
        backend=build_backend(),
        skills=skills,
        permissions=skill_permissions(),
        # Planning is not part of `create_deep_agent` in deepagents 0.7.15 — it
        # provides delegation, the filesystem, and skills, but no todo tool, so
        # without this the agent cannot record a plan at all. The middleware
        # lives upstream in langchain now.
        middleware=[TodoListMiddleware()],
    )

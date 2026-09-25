"""Assembling the agent: the model, its prompt, its tools, and its tiers.

This is the composition root and nothing else. What each part *is* lives in the
module that owns it — `mcp` for tool discovery, `skills` for the skill menu,
`backends` for the tiers, `middleware` for the stack — so that changing one
does not mean reading all of them.
"""

import logging
from pathlib import Path

from databricks_langchain import ChatDatabricks
from deepagents import create_deep_agent

from agent_server.backends import build_backend, filesystem_permissions
from agent_server.config import MODEL_ENDPOINT
from agent_server.middleware import build_middlewares
from agent_server.skills import SKILLS_MOUNT
from agent_server.tools import agent_tools

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


# TODO 2: System Prompt — edit `prompts/system_prompt.md`.
SYSTEM_PROMPT = (PROMPTS_DIR / "system_prompt.md").read_text()

async def init_agent(flag_pii: bool = True, flag_tool_retries: bool = True):
    return create_deep_agent(
        model=ChatDatabricks(endpoint=MODEL_ENDPOINT),
        system_prompt=SYSTEM_PROMPT,
        tools=await agent_tools(),
        skills=[SKILLS_MOUNT],
        backend=build_backend(),
        permissions=filesystem_permissions(),
        middleware=build_middlewares(flag_pii, flag_tool_retries),
    )

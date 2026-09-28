"""The composition root: the model, its prompt, its tools and its tiers.

What each part *is* lives in the module that owns it.
"""

import logging
from pathlib import Path

from deepagents import create_deep_agent

from agent_server.backends import build_backend, filesystem_permissions
from agent_server.middleware import build_middlewares
from agent_server.model import build_model
from agent_server.skills import SKILLS_MOUNT
from agent_server.env import resolve
from agent_server.tools import agent_tools

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

## TODO 1: LLM Selection
MODEL_ENDPOINT = "databricks-glm-5-3-flash"

## TODO 2: System Prompt — edit `prompts/system_prompt.md`.
SYSTEM_PROMPT = resolve((PROMPTS_DIR / "system_prompt.md").read_text())

OKF_ACTOR = "agent"

async def init_agent(flag_pii: bool = True, flag_tool_retries: bool = True):
    return create_deep_agent(
        model=build_model(MODEL_ENDPOINT),
        system_prompt=SYSTEM_PROMPT,
        tools=await agent_tools(),
        skills=[SKILLS_MOUNT],
        backend=build_backend(okf_actor=OKF_ACTOR),
        permissions=filesystem_permissions(),
        middleware=build_middlewares(flag_pii, flag_tool_retries),
    )

"""What the agent is, in the two places something else has to agree with it.

Both values live here rather than in `agent.py` because the filesystem tier
needs the actor and the agent needs the endpoint, and a module holding both
would have them importing each other.
"""

## TODO 1: LLM Selection
MODEL_ENDPOINT = "databricks-glm-5-3-flash"

OKF_ACTOR = f"agent-ptmn-training/{MODEL_ENDPOINT}"

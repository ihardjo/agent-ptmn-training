from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Load env vars from .env before importing the agent for proper auth
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

# Import app — routes are registered at import time
from agent_server.agent import app  # noqa: E402, F401


def main():
    uvicorn.run(
        "agent_server.start_server:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
        reload=False,
    )

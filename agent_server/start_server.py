import argparse
import logging
import os
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Load env vars from .env before importing the agent for proper auth
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

from agent_server.routes import router  # noqa: E402

logger = logging.getLogger(__name__)

# uvicorn configures only its own loggers, leaving the root logger at WARNING —
# so every `logger.info` in this application was silently dropped, including the
# MCP tool discovery line that has been there since the beginning. Requirements
# that say something is "recorded in the application log" need this to be set.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s %(name)s: %(message)s",
)

# ── Chat proxy middleware ──────────────────────────────────────────────────────
# Proxies frontend paths to the Next.js app on CHAT_APP_PORT.

_CHAT_PORT = os.environ.get("CHAT_APP_PORT", "3000")
_PROXY_TIMEOUT = float(os.environ.get("CHAT_PROXY_TIMEOUT_SECONDS", "300"))
_PROXY_EXACT = {"/", "/favicon.ico", "/ping"}
_PROXY_PREFIXES = ("/assets/", "/api/", "/chat/")

_proxy_client = httpx.AsyncClient(timeout=_PROXY_TIMEOUT)


class ChatProxyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _PROXY_EXACT or path.startswith(_PROXY_PREFIXES):
            target = f"http://localhost:{_CHAT_PORT}{path}"
            if request.url.query:
                target += f"?{request.url.query}"
            try:
                req = _proxy_client.build_request(
                    method=request.method,
                    url=target,
                    headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
                    content=await request.body(),
                )
                resp = await _proxy_client.send(req, stream=True)
                content_type = resp.headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    return StreamingResponse(
                        resp.aiter_bytes(),
                        status_code=resp.status_code,
                        headers=dict(resp.headers),
                        media_type="text/event-stream",
                    )
                content = await resp.aread()
                await resp.aclose()
                return Response(
                    content=content,
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                )
            except Exception:
                logger.exception(f"Chat proxy error for {path}")
                return Response(status_code=502, content=b"Chat app unavailable")
        return await call_next(request)


app = FastAPI(title="Agent API")
app.include_router(router)
app.add_middleware(ChatProxyMiddleware)


def main():
    # `--port` is honoured because `scripts/preflight.py` starts this server on
    # a free port and then health-checks that port. Hard-coding 8000 made the
    # argument silently ignored, so preflight always probed a port nothing was
    # listening on and reported a connection refused as a failed health check.
    # The default stays 8000: that is the port Databricks Apps expects.
    parser = argparse.ArgumentParser(description="Run the agent server.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 8000)),
        help="port to listen on (default: $PORT or 8000)",
    )
    args = parser.parse_args()
    uvicorn.run(
        "agent_server.start_server:app",
        host="0.0.0.0",
        port=args.port,
        workers=1,
        reload=False,
    )

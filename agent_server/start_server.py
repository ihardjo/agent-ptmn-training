"""The HTTP server: the agent's routes, and a proxy to the chat frontend."""

import argparse
import logging
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Before importing the agent, which reads credentials at import time.
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

from agent_server.env import env  # noqa: E402
from agent_server.routes import router  # noqa: E402

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=env("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s %(name)s: %(message)s",
)

# ── Chat proxy: frontend paths go to the Next.js app on CHAT_APP_PORT ─────────

_CHAT_PORT = env("CHAT_APP_PORT", "3000")
_PROXY_TIMEOUT = float(env("CHAT_PROXY_TIMEOUT_SECONDS", "300"))
_PROXY_EXACT = {"/", "/favicon.ico", "/ping"}
_PROXY_PREFIXES = ("/assets/", "/api/", "/chat/")

_proxy_client = httpx.AsyncClient(timeout=_PROXY_TIMEOUT)


class ChatProxyMiddleware(BaseHTTPMiddleware):
    """Forwards the frontend's paths to the chat app, streaming SSE through."""

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
    """Run the server on `--port`, `$PORT`, or 8000."""
    parser = argparse.ArgumentParser(description="Run the agent server.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(env("PORT", "8000")),
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

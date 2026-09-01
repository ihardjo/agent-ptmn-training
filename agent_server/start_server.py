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
    uvicorn.run(
        "agent_server.start_server:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
        reload=False,
    )

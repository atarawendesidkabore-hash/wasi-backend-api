import logging
import traceback

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config import settings
from src.middleware.request_id import request_id_var

logger = logging.getLogger("wasi.errors")


class GlobalErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            rid = request_id_var.get("")
            tb = traceback.format_exc()

            # Log full traceback server-side with request ID
            logger.error(
                "Unhandled exception [request_id=%s] %s %s: %s\n%s",
                rid,
                request.method,
                request.url.path,
                str(exc),
                tb,
            )

            # Structured JSON response
            body = {
                "error": "Internal Server Error",
                "request_id": rid,
            }
            if settings.DEBUG:
                body["detail"] = str(exc)
                body["traceback"] = tb.splitlines()

            return JSONResponse(status_code=500, content=body)

from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class EnforceDomainMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, allowed_host: str, app_env: str) -> None:
        super().__init__(app)
        self.allowed_host = allowed_host
        self.app_env = app_env

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self.app_env != "production":
            return await call_next(request)

        host = request.headers.get("host", "").split(":")[0]

        is_allowed = host == self.allowed_host or host.endswith(f".{self.allowed_host}")

        if not is_allowed:
            redirect_url = str(request.url).replace(host, self.allowed_host)
            return RedirectResponse(url=redirect_url, status_code=301)

        return await call_next(request)

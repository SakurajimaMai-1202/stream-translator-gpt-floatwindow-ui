"""桌面程式與管理 API 共用的驗證設定。"""
import hmac
import os
import secrets

TOKEN_ENV = "FLOATWINDOW_ADMIN_TOKEN"
TOKEN_HEADER = "X-FloatWindow-Token"
TOKEN_COOKIE = "fw_admin_token"
DEV_ORIGIN_REGEX = r"http://(localhost|127\.0\.0\.1)(:\d+)?"


def get_admin_token():
    return os.environ.get(TOKEN_ENV, "")


def ensure_admin_token():
    token = get_admin_token()
    if not token:
        token = secrets.token_urlsafe(32)
        os.environ[TOKEN_ENV] = token
    return token


def token_matches(candidate, token):
    return bool(token and candidate) and hmac.compare_digest(
        candidate.encode("utf-8"), token.encode("utf-8")
    )


class AdminAuthMiddleware:
    def __init__(self, app, api_prefix="/api"):
        self.app = app
        self.api_prefix = api_prefix

    async def __call__(self, scope, receive, send):
        # CORS 預檢不帶自訂標頭，交給 CORSMiddleware 處理
        if (scope["type"] == "http" and scope["method"] != "OPTIONS"
                and scope["path"].startswith(self.api_prefix)):
            from starlette.requests import Request

            request = Request(scope)
            token = get_admin_token()
            health = request.method == "GET" and scope["path"] == f"{self.api_prefix}/health"
            session = request.method == "GET" and scope["path"] == f"{self.api_prefix}/auth/session"
            valid = token_matches(request.headers.get(TOKEN_HEADER), token) or token_matches(
                request.cookies.get(TOKEN_COOKIE), token
            )
            if session:
                valid = token_matches(request.query_params.get("token"), token)
            if token and not health and not valid:
                from fastapi.responses import JSONResponse

                response = JSONResponse({"detail": "管理 API 驗證失敗"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def register_admin_auth(app, api_prefix):
    from fastapi.responses import JSONResponse, RedirectResponse

    app.add_middleware(AdminAuthMiddleware, api_prefix=api_prefix)

    @app.get(f"{api_prefix}/auth/session", include_in_schema=False)
    async def admin_session(token: str = ""):
        if not token_matches(token, get_admin_token()):
            return JSONResponse({"detail": "管理 API 驗證失敗"}, status_code=401)
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(TOKEN_COOKIE, token, httponly=True, samesite="strict", path="/")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

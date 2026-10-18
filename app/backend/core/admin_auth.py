"""桌面程式與管理 API 共用的驗證設定。"""
import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from collections import deque

TOKEN_ENV = "FLOATWINDOW_ADMIN_TOKEN"
TOKEN_HEADER = "X-FloatWindow-Token"
TOKEN_COOKIE = "fw_admin_token"
LAN_SESSION_COOKIE = "fw_lan_session"
LAN_SESSION_MAX_AGE = 30 * 24 * 3600
DEV_ORIGIN_REGEX = r"http://(localhost|127\.0\.0\.1)(:\d+)?"
FORWARDED_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded")

# 登入失敗上限：反向代理後所有請求來源相同，因此不分 IP 計算。
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 300


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


def lan_session_value(password):
    """Cookie 存的是密碼的 HMAC，不是密碼本身；改密碼後舊登入全部失效。"""
    return hmac.new(password.encode("utf-8"), b"floatwindow-lan-session", hashlib.sha256).hexdigest()


def is_remote_client(request):
    """區網或反向代理進來的連線；本機桌面程式維持權杖驗證、不需要密碼。"""
    if any(header in request.headers for header in FORWARDED_HEADERS):
        return True
    host = request.client.host if request.client else ""
    try:
        return not ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() != "localhost"


class LoginLimiter:
    def __init__(self, max_failures=LOGIN_MAX_FAILURES, window=LOGIN_WINDOW_SECONDS, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window
        self.clock = clock
        self._failures = deque()
        self._lock = threading.Lock()

    def _prune(self, now):
        while self._failures and now - self._failures[0] >= self.window:
            self._failures.popleft()

    def blocked(self):
        with self._lock:
            self._prune(self.clock())
            return len(self._failures) >= self.max_failures

    def record_failure(self):
        with self._lock:
            now = self.clock()
            self._prune(now)
            self._failures.append(now)

    def reset(self):
        with self._lock:
            self._failures.clear()


login_limiter = LoginLimiter()


def _no_password():
    return ""


class AdminAuthMiddleware:
    def __init__(self, app, api_prefix="/api", lan_password=_no_password):
        self.app = app
        self.api_prefix = api_prefix
        self.lan_password = lan_password

    def _lan_session_valid(self, request):
        password = self.lan_password()
        return bool(password) and token_matches(
            request.cookies.get(LAN_SESSION_COOKIE), lan_session_value(password)
        )

    async def __call__(self, scope, receive, send):
        # CORS 預檢不帶自訂標頭，交給 CORSMiddleware 處理
        if scope["type"] == "http" and scope["method"] != "OPTIONS":
            from starlette.requests import Request

            request = Request(scope)
            path = scope["path"]
            is_api = path.startswith(self.api_prefix)
            token = get_admin_token()
            health = request.method == "GET" and path == f"{self.api_prefix}/health"
            session = request.method == "GET" and path == f"{self.api_prefix}/auth/session"
            login = path in {"/login", f"{self.api_prefix}/auth/login"}
            valid = token_matches(request.headers.get(TOKEN_HEADER), token) or token_matches(
                request.cookies.get(TOKEN_COOKIE), token
            )
            if session:
                valid = token_matches(request.query_params.get("token"), token)

            if is_remote_client(request):
                # 區網／反向代理：整個介面都要先登入（權杖或區網密碼）。
                if not (health or login or valid or self._lan_session_valid(request)):
                    from fastapi.responses import JSONResponse, RedirectResponse

                    response = (JSONResponse({"detail": "管理 API 驗證失敗"}, status_code=401) if is_api
                                else RedirectResponse("/login", status_code=302))
                    await response(scope, receive, send)
                    return
            elif is_api and token and not health and not login and not valid:
                from fastapi.responses import JSONResponse

                response = JSONResponse({"detail": "管理 API 驗證失敗"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


LOGIN_PAGE = """<!doctype html>
<html lang="zh-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Stream Translator 登入</title>
<style>
:root{color-scheme:dark}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0c111b;color:#eef2f7;
font-family:system-ui,"Segoe UI","Microsoft JhengHei UI",sans-serif}
form{width:min(360px,calc(100vw - 32px));background:#17202d;border:1px solid #ffffff1a;border-radius:16px;padding:28px;box-sizing:border-box}
h1{font-size:20px;margin:0 0 6px}p{margin:0 0 20px;color:#ffffff99;font-size:14px;line-height:1.6}
label{display:block;font-size:14px;margin-bottom:8px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:10px;border:1px solid #ffffff33;background:#0c111b;color:#eef2f7;font-size:16px}
button{width:100%;margin-top:16px;padding:11px;border:0;border-radius:10px;background:#2563eb;color:#fff;font-size:15px;font-weight:600;cursor:pointer}
button:disabled{opacity:.5}#error{color:#fca5a5;min-height:1.4em;margin:12px 0 0;font-size:14px}
</style></head><body>
<form id="login"><h1>Stream Translator</h1><p>從區網或外部連線需要輸入控制介面密碼。</p>
<label for="password">密碼</label><input id="password" type="password" autocomplete="current-password" required autofocus>
<button type="submit">登入</button><p id="error" role="alert"></p></form>
<script>
const form=document.getElementById('login'),error=document.getElementById('error');
form.addEventListener('submit',async(e)=>{e.preventDefault();const b=form.querySelector('button');b.disabled=true;error.textContent='';
try{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',
body:JSON.stringify({password:document.getElementById('password').value})});
if(r.ok){location.replace('/');return}
const d=await r.json().catch(()=>({}));error.textContent=d.detail||'登入失敗';}
catch{error.textContent='無法連線，請稍後再試'}finally{b.disabled=false}});
</script></body></html>"""


def register_admin_auth(app, api_prefix, lan_password=_no_password):
    """lan_password：回傳目前區網登入密碼的函式（未設定時回傳空字串）。"""
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

    app.add_middleware(AdminAuthMiddleware, api_prefix=api_prefix, lan_password=lan_password)

    @app.get(f"{api_prefix}/auth/session", include_in_schema=False)
    async def admin_session(token: str = ""):
        if not token_matches(token, get_admin_token()):
            return JSONResponse({"detail": "管理 API 驗證失敗"}, status_code=401)
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(TOKEN_COOKIE, token, httponly=True, samesite="strict", path="/")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/login", include_in_schema=False)
    async def login_page():
        return HTMLResponse(LOGIN_PAGE, headers={"Cache-Control": "no-store"})

    @app.post(f"{api_prefix}/auth/login", include_in_schema=False)
    async def lan_login(request: Request):
        password = lan_password()
        if not password:
            return JSONResponse({"detail": "未開啟區網連線或尚未設定密碼，請在本機的「一般設定」設定後再試。"}, status_code=403)
        if login_limiter.blocked():
            return JSONResponse({"detail": "嘗試次數過多，請 5 分鐘後再試。"}, status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        candidate = payload.get("password") if isinstance(payload, dict) else None
        if not isinstance(candidate, str) or not token_matches(candidate, password):
            login_limiter.record_failure()
            return JSONResponse({"detail": "密碼錯誤"}, status_code=401)
        login_limiter.reset()
        response = JSONResponse({"success": True})
        response.set_cookie(LAN_SESSION_COOKIE, lan_session_value(password), max_age=LAN_SESSION_MAX_AGE,
                            httponly=True, samesite="strict", path="/")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post(f"{api_prefix}/auth/logout", include_in_schema=False)
    async def lan_logout():
        response = JSONResponse({"success": True})
        response.delete_cookie(LAN_SESSION_COOKIE, path="/")
        return response

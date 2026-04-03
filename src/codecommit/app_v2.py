import json
import os
import secrets
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

import httpx

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from .auth import create_jwt, decode_jwt, hash_password, verify_password
from .avatars import avatar_url_for_user, generate_avatar_url, setup_url_for_user
from .config import DB_PATH, MEDIA_DIR
from .db import Database
from .service import CodeCommitService, DomainError


JWT_SECRET = os.getenv("CODECOMMIT_JWT_SECRET")
if not JWT_SECRET:
    raise ValueError("CODECOMMIT_JWT_SECRET environment variable must be set")
JWT_TTL_SECONDS = int(os.getenv("CODECOMMIT_JWT_TTL", "86400"))
ADMIN_DASH_SECRET = os.getenv("CODECOMMIT_ADMIN_DASH_SECRET", "codecommit-admin")
ADMIN_BOOTSTRAP_KEY = os.getenv("CODECOMMIT_ADMIN_BOOTSTRAP_KEY", "codecommit-bootstrap")
RATE_LIMIT_MAX = int(os.getenv("CODECOMMIT_RATE_LIMIT_MAX", "180"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("CODECOMMIT_RATE_LIMIT_WINDOW_SECONDS", "60"))
APP_VERSION = os.getenv("CODECOMMIT_APP_VERSION", "5.9")

# ── GitHub OAuth ──────────────────────────────────────────────────────────────
GITHUB_CLIENT_ID = os.getenv("CODECOMMIT_GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("CODECOMMIT_GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv(
    "CODECOMMIT_GITHUB_REDIRECT_URI",
    "http://localhost:8080/v2/auth/github/callback",
)
GITHUB_SCOPE = os.getenv("CODECOMMIT_GITHUB_OAUTH_SCOPE", "read:user user:email")

# ── CORS allowlist (comma-separated origins in env, falls back to localhost) ──
_RAW_ORIGINS = os.getenv(
    "CODECOMMIT_CORS_ORIGINS",
    "http://localhost,http://localhost:8080,http://127.0.0.1:8080,http://74.208.227.87",
)
ALLOW_ORIGINS: list[str] = [o.strip() for o in _RAW_ORIGINS.split(",") if o.strip()]

db = Database(DB_PATH)
service = CodeCommitService(db)
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="CodeCommit API v2", version="2.0.0")
_rate_limiter: dict[str, list[float]] = defaultdict(list)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
WEB_INDEX = Path(__file__).resolve().parent / "web" / "index.html"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if RATE_LIMIT_MAX <= 0:
        return await call_next(request)
    path = request.url.path
    if path.startswith("/media/") or path == "/":
        return await call_next(request)
    now = time.time()
    client_ip = request.client.host if request.client else "unknown"
    bucket = _rate_limiter[client_ip]
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= RATE_LIMIT_MAX:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit excedido. Intenta nuevamente en unos segundos.",
                "retry_after_seconds": RATE_LIMIT_WINDOW_SECONDS,
            },
        )
    bucket.append(now)
    return await call_next(request)


class ChatHub:
    def __init__(self):
        self.rooms = defaultdict(list)

    async def connect(self, chat_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms[chat_id].append(ws)

    def disconnect(self, chat_id: int, ws: WebSocket):
        if ws in self.rooms.get(chat_id, []):
            self.rooms[chat_id].remove(ws)

    async def broadcast(self, chat_id: int, payload: dict):
        stale = []
        for ws in self.rooms.get(chat_id, []):
            try:
                await ws.send_json(payload)
            except RuntimeError:
                stale.append(ws)
        for ws in stale:
            self.disconnect(chat_id, ws)


hub = ChatHub()
ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _token_from_ws(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return websocket.query_params.get("token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        payload = decode_jwt(credentials.credentials, JWT_SECRET)
    except ValueError as err:
        raise HTTPException(status_code=401, detail=str(err)) from err

    user_id = int(payload.get("sub", 0))
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists.")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
):
    if not credentials:
        return None
    try:
        payload = decode_jwt(credentials.credentials, JWT_SECRET)
    except ValueError as err:
        raise HTTPException(status_code=401, detail=str(err)) from err
    user_id = int(payload.get("sub", 0))
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists.")
    return user


def _is_admin_authorized(user: dict | None, secret: str | None) -> bool:
    if user and bool(user.get("is_admin", False)):
        return True
    return bool(secret) and str(secret) == ADMIN_DASH_SECRET


def _save_profile_image(file: UploadFile, user_id: int, kind: str) -> str:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Formato no permitido. Usa png, jpg o webp.")
    ext = ALLOWED_IMAGE_TYPES[file.content_type]
    filename = f"user_{user_id}_{kind}_{secrets.token_hex(8)}{ext}"
    target = Path(MEDIA_DIR) / filename

    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Imagen excede 5MB.")
    target.write_bytes(data)
    return f"/media/{filename}"


@app.get("/api/health")
def health():
    return {"ok": True, "service": "codecommit-v2"}


@app.get("/health")
def health_simple():
    return {"status": "online"}


@app.get("/v2/health")
def health_v2():
    return {"status": "online", "version": APP_VERSION}


@app.get("/")
def web_root():
    return FileResponse(WEB_INDEX)


# ── GitHub OAuth endpoints ────────────────────────────────────────────────────

@app.get("/v2/auth/github/login")
def github_login():
    """Redirect the browser to GitHub's OAuth authorization page."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth no configurado. Establece CODECOMMIT_GITHUB_CLIENT_ID en el servidor.",
        )
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": GITHUB_SCOPE,
        "state": state,
    }
    github_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=github_url)


@app.get("/v2/auth/github/callback")
async def github_callback(code: str, state: str | None = None):
    """Exchange the OAuth code for a GitHub token, fetch the user profile,
    then create/login the user and return our own JWT."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth no configurado en el servidor.",
        )

    # 1. Exchange code for access token
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Error obteniendo token de GitHub.")

    token_data = token_resp.json()
    if "error" in token_data:
        raise HTTPException(
            status_code=400,
            detail=f"GitHub OAuth error: {token_data.get('error_description', token_data['error'])}",
        )
    github_token = token_data.get("access_token", "")
    if not github_token:
        raise HTTPException(status_code=502, detail="No se recibió access_token de GitHub.")

    # 2. Fetch GitHub user profile
    async with httpx.AsyncClient(timeout=15) as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "CodeCommitApp/5.9",
            },
        )
    if user_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Error obteniendo perfil de GitHub.")

    gh_profile = user_resp.json()
    github_login_name: str = gh_profile.get("login", "")
    gh_name: str = gh_profile.get("name") or github_login_name

    if not github_login_name:
        raise HTTPException(status_code=502, detail="GitHub no devolvió un login válido.")

    # 3. Find or create user by github_username
    existing = db.get_user_by_github_username(github_login_name)
    if existing:
        user = existing
    else:
        # Auto-register with GitHub identity
        username_candidate = github_login_name[:32]  # max 32 chars
        # Ensure unique username if collision
        if db.get_user_by_username(username_candidate):
            username_candidate = f"{username_candidate}_{secrets.token_hex(3)}"
        try:
            user_id = db.create_user(
                {
                    "username": username_candidate,
                    "password_hash": "",  # no password for OAuth users
                    "stack": [],
                    "years": 0,
                    "prefers_tabs": False,
                    "dark_mode": True,
                    "is_admin": False,
                    "github_username": github_login_name,
                }
            )
            user = db.get_user(user_id)
        except Exception as err:
            raise HTTPException(
                status_code=500, detail=f"Error creando usuario OAuth: {err}"
            ) from err

    # 4. Issue our own JWT
    token = create_jwt(
        {"sub": str(user["id"]), "username": user["username"], "github_login": github_login_name},
        JWT_SECRET,
        ttl_seconds=JWT_TTL_SECONDS,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "github_username": github_login_name,
        "user_id": user["id"],
        "new_user": existing is None,
    }


@app.post("/v2/auth/register")
def register(payload: dict):
    password = str(payload.get("password", ""))
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="password debe tener 8+ caracteres.")
    try:
        user = service.register_user(
            {
                "username": payload.get("username"),
                "password_hash": hash_password(password),
                "stack": payload.get("stack"),
                "years": payload.get("years", payload.get("years_exp")),
                "prefers_tabs": payload.get(
                    "prefers_tabs", payload.get("tabs_vs_spaces", False)
                ),
                "dark_mode": payload.get("dark_mode", True),
                "github_username": payload.get("github_username"),
                "puzzle_answer": payload.get("puzzle_answer"),
                "is_admin": bool(payload.get("is_admin", False))
                and str(payload.get("admin_bootstrap_key", "")) == ADMIN_BOOTSTRAP_KEY,
            }
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    # Auto-asignar avatar DiceBear si el usuario no subió uno
    if user and not user.get("avatar_url"):
        auto_avatar = avatar_url_for_user(user["username"])
        auto_setup = setup_url_for_user(user["username"])
        db.update_user_images(user["id"], avatar_url=auto_avatar, setup_url=auto_setup)
        user["avatar_url"] = auto_avatar
        user["setup_url"] = auto_setup

    return user


@app.post("/v2/auth/login")
def login(payload: dict):
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    auth_user = db.get_user_auth_by_username(username)
    if not auth_user or not verify_password(password, auth_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales invalidas.")

    db.update_user_streak(auth_user["id"])

    token = create_jwt(
        {"sub": str(auth_user["id"]), "username": auth_user["username"]},
        JWT_SECRET,
        ttl_seconds=JWT_TTL_SECONDS,
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/v2/me")
def me(current_user: dict = Depends(get_current_user)):
    user = db.get_user(int(current_user["sub"]))
    return user


@app.get("/v2/profiles")
def profiles(stack: str | None = None, current_user: dict = Depends(get_current_user)):
    return {"profiles": service.list_profiles(current_user["id"], stack_filter=stack)}


@app.get("/v2/suggested-matches")
def suggested_matches(limit: int = 10, current_user: dict = Depends(get_current_user)):
    return {"profiles": service.suggested_matches(current_user["id"], limit=limit)}


@app.post("/v2/feed")
def publish_feed(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.create_feed_post(
            user_id=current_user["id"],
            title=str(payload.get("title", "")),
            content=str(payload.get("content", "")),
            category=str(payload.get("category", "")),
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/feed")
def get_feed(limit: int = 20):
    return {"posts": service.list_feed_posts(limit=limit)}


@app.post("/v2/clusters")
def create_cluster(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.create_cluster(
            creator_id=current_user["id"],
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            min_karma_required=int(payload.get("min_karma_required", 0)),
            tech_stack_focus=payload.get("tech_stack_focus"),
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/clusters")
def get_clusters(q: str | None = None, limit: int = 50):
    return {"clusters": service.list_clusters(query=q, limit=limit)}


@app.post("/v2/clusters/{cluster_id}/join")
def join_cluster(cluster_id: int, current_user: dict = Depends(get_current_user)):
    try:
        return service.join_cluster(current_user["id"], cluster_id)
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/feed/interactions")
def feed_interactions(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.interact_feed(
            user_id=current_user["id"],
            target_type=str(payload.get("target_type", "")),
            target_id=int(payload.get("target_id", 0)),
            interaction_type=str(payload.get("interaction_type", "")),
            fork_cluster_id=int(payload["fork_cluster_id"])
            if payload.get("fork_cluster_id") is not None
            else None,
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/feed/interactions")
def list_feed_interactions(target_type: str, target_id: int, limit: int = 200):
    try:
        return {"interactions": service.list_interactions(target_type, target_id, limit=limit)}
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/feed/threads")
def create_feed_thread(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.create_thread_comment(
            user_id=current_user["id"],
            target_type=str(payload.get("target_type", "")),
            target_id=int(payload.get("target_id", 0)),
            content=str(payload.get("content", "")),
            parent_thread_id=int(payload["parent_thread_id"])
            if payload.get("parent_thread_id") is not None
            else None,
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/feed/threads")
def list_feed_threads(target_type: str, target_id: int, limit: int = 200):
    try:
        return {"threads": service.list_thread_comments(target_type, target_id, limit=limit)}
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/github/{username}")
def github_repos(username: str):
    try:
        return service.get_github_repositories(username)
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/github/sync")
def github_sync(current_user: dict = Depends(get_current_user)):
    try:
        return service.sync_github_activity(current_user["id"])
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/bounties")
def create_bounty(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.create_bounty(
            creator_id=current_user["id"],
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            reward_amount=float(payload.get("reward_amount", 0)),
            reward_currency=str(payload.get("reward_currency", "USD")),
            tech_stack=str(payload.get("tech_stack", "")),
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/bounties")
def get_bounties(status: str | None = None):
    return {"bounties": service.list_bounties(status=status)}


@app.post("/v2/showcase")
def create_showcase(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.create_showcase_project(
            user_id=current_user["id"],
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            price=payload.get("price"),
            demo_url=payload.get("demo_url"),
            image_url=payload.get("image_url"),
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/showcase")
def get_showcase(limit: int = 30):
    return {"projects": service.list_showcase_projects(limit=limit)}


@app.post("/v2/resources")
def create_resource(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.create_resource(
            user_id=current_user["id"],
            link=str(payload.get("link", "")),
            topic=str(payload.get("topic", "")),
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/resources")
def get_resources(topic: str | None = None, limit: int = 50):
    return {"resources": service.list_resources(topic=topic, limit=limit)}


@app.post("/v2/snippets")
def create_snippet(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        snippet_id = db.create_snippet(
            user_id=int(current_user["sub"]),
            title=str(payload.get("title", "")),
            language=str(payload.get("language", "")),
            code=str(payload.get("code", "")),
        )
        return {"id": snippet_id, "message": "Snippet creado"}
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/snippets")
def get_snippets(limit: int = 50):
    return {"snippets": db.list_snippets(limit=limit)}


@app.post("/v2/endorse")
def endorse_user(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        to_user_id = int(payload.get("to_user_id"))
        skill = str(payload.get("skill", "")).strip()
        if not skill:
            raise HTTPException(status_code=400, detail="Skill requerido")
        result = db.create_endorsement(
            from_user_id=int(current_user["sub"]),
            to_user_id=to_user_id,
            skill=skill,
        )
        if result == -1:
            return {"message": "Ya endorsement existente para esta skill"}
        return {"message": "Endorsement registrado", "skill": skill}
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/user/{user_id}/endorsements")
def get_user_endorsements(user_id: int):
    return {"endorsements": db.get_user_endorsements(user_id), "counts": db.get_user_endorsement_count(user_id)}


@app.get("/v2/karma/top")
def karma_top(limit: int = 10):
    return {"users": service.top_karma_users(limit=limit)}


@app.get("/v2/stats/global")
def stats_global():
    return service.global_stats()


@app.get("/v2/admin/analytics")
def admin_analytics(
    secret: str | None = None,
    current_user: dict | None = Depends(get_optional_user),
):
    if not _is_admin_authorized(current_user, secret):
        raise HTTPException(status_code=403, detail="Admin authorization requerida.")
    return service.admin_analytics()


@app.post("/v2/resources/{resource_id}/helpful")
def mark_helpful(resource_id: int, current_user: dict = Depends(get_current_user)):
    try:
        return service.mark_resource_helpful(current_user["id"], resource_id)
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/showcase/{project_id}/collaborate")
def collaborate_showcase(project_id: int, current_user: dict = Depends(get_current_user)):
    try:
        return service.collaborate_showcase(current_user["id"], project_id)
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/me/avatar/generate")
def generate_avatar(
    style: str = "bottts",
    provider: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Genera y asigna automáticamente un avatar para el usuario actual.
    - style: bottts | identicon | pixel-art | adventurer | lorelei | notionists
    - provider: dicebear | robohash (overrides env config)
    """
    url = generate_avatar_url(seed=current_user["username"], style=style, provider=provider)
    db.update_user_images(current_user["id"], avatar_url=url)
    return {"avatar_url": url, "style": style, "provider": provider or "default"}


@app.post("/v2/me/avatar")
def upload_avatar(
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    url = _save_profile_image(image, current_user["id"], "avatar")
    db.update_user_images(current_user["id"], avatar_url=url)
    return {"avatar_url": url}


@app.post("/v2/me/setup")
def upload_setup(
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    url = _save_profile_image(image, current_user["id"], "setup")
    db.update_user_images(current_user["id"], setup_url=url)
    return {"setup_url": url}


@app.get("/v2/match/{target_id}")
def match(target_id: int, current_user: dict = Depends(get_current_user)):
    try:
        return service.compatibility(current_user["id"], target_id)
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/pull-requests")
def open_pr(payload: dict, current_user: dict = Depends(get_current_user)):
    to_user_id = int(payload["to_user_id"])
    bounty_id = payload.get("bounty_id")
    try:
        result = service.send_pull_request(
            current_user["id"],
            to_user_id,
            bounty_id=int(bounty_id) if bounty_id is not None else None,
        )
        if result.get("matched") and result.get("chat_id"):
            result["match_id"] = result["chat_id"]
        return result
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/pull-requests/{pr_id}/merge")
def merge_pr(pr_id: int, current_user: dict = Depends(get_current_user)):
    try:
        pr = db.get_pull_request(pr_id)
        if not pr:
            raise HTTPException(status_code=404, detail="PR no existe.")
        if pr["to_user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Solo el destinatario puede mergear.")
        return service.merge_pull_request(pr_id)
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/v2/pull-requests/incoming")
def incoming_prs(current_user: dict = Depends(get_current_user)):
    return {"pull_requests": db.list_pull_requests_for_user(current_user["id"], "incoming", "open")}


@app.post("/v2/chat/{chat_id}/messages")
async def post_chat_message(chat_id: int, payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        msg = service.send_message(chat_id, current_user["id"], str(payload["body"]))
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    await hub.broadcast(chat_id, {"type": "chat.message", "message": msg})
    return msg


@app.get("/v2/chat/{chat_id}/messages")
def get_chat_messages(chat_id: int, current_user: dict = Depends(get_current_user)):
    if not db.chat_has_user(chat_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="No tienes acceso a este chat.")
    return {"messages": service.list_messages(chat_id)}


@app.get("/v2/chat/{chat_id}/scratchpad")
def get_chat_scratchpad(chat_id: int, current_user: dict = Depends(get_current_user)):
    try:
        return service.get_scratchpad(chat_id, current_user["id"])
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/chat/{chat_id}/scratchpad")
def update_chat_scratchpad(chat_id: int, payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.update_scratchpad(chat_id, current_user["id"], str(payload.get("content", "")))
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/v2/export/gist")
def export_gist(payload: dict, current_user: dict = Depends(get_current_user)):
    try:
        return service.export_gist(
            user_id=current_user["id"],
            chat_id=int(payload.get("chat_id", 0)),
            content=str(payload.get("content", "")),
            filename=payload.get("filename"),
            language=payload.get("language"),
        )
    except DomainError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.websocket("/v2/ws/chat/{chat_id}")
async def ws_chat(websocket: WebSocket, chat_id: int):
    token = _token_from_ws(websocket)
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return
    try:
        payload = decode_jwt(token, JWT_SECRET)
        user_id = int(payload.get("sub", 0))
    except Exception:
        await websocket.close(code=4401, reason="Invalid token")
        return

    if not db.chat_has_user(chat_id, user_id):
        await websocket.close(code=4403, reason="Forbidden chat")
        return

    await hub.connect(chat_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event_type = str(data.get("type", "chat.message")).strip()
            if event_type in {"chat.message", "message"}:
                body = str(data.get("body", "")).strip()
                if not body:
                    continue
                msg = service.send_message(chat_id, user_id, body)
                await hub.broadcast(chat_id, {"type": "chat.message", "message": msg})
                continue
            if event_type in {"scratchpad.update", "chat.scratchpad"}:
                content = str(data.get("content", ""))
                scratch = service.update_scratchpad(chat_id, user_id, content)
                await hub.broadcast(chat_id, {"type": "chat.scratchpad", "scratchpad": scratch})
                continue
    except WebSocketDisconnect:
        hub.disconnect(chat_id, websocket)

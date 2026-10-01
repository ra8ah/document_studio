import os
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from fastapi import Request, HTTPException

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


PRINT_TOKEN_TTL_S = 60


def create_print_token(doc_id: str) -> str:
    """Read-only, ~60s, bound to one document; accepted ONLY by GET /api/print/{id}."""
    payload = {"doc": doc_id, "type": "print",
               "exp": datetime.now(timezone.utc) + timedelta(seconds=PRINT_TOKEN_TTL_S)}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_print_token(token: str, doc_id: str) -> bool:
    try:
        p = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return False
    return p.get("type") == "print" and p.get("doc") == doc_id


_SAMESITE_VALUES = {"lax", "strict", "none"}


def cookie_samesite() -> str:
    """SameSite for auth cookies, from COOKIE_SAMESITE (default "lax").

    "lax" is right when the browser talks to the API first-party (Vercel rewrite /api -> backend,
    or the same host). Use "none" only if the frontend calls the backend cross-site directly.
    """
    v = (os.environ.get("COOKIE_SAMESITE") or "lax").strip().lower()
    if v not in _SAMESITE_VALUES:
        raise RuntimeError(f"COOKIE_SAMESITE must be one of {sorted(_SAMESITE_VALUES)}")
    return v


def _cookie_opts() -> dict:
    return {"httponly": True, "secure": True, "samesite": cookie_samesite(), "path": "/"}


def set_auth_cookies(response, access_token: str, refresh_token: str):
    opts = _cookie_opts()
    response.set_cookie(key="access_token", value=access_token, max_age=3600, **opts)
    response.set_cookie(key="refresh_token", value=refresh_token, max_age=604800, **opts)


def clear_auth_cookies(response):
    # attributes must match the ones used when setting, or some browsers keep the cookie
    opts = _cookie_opts()
    response.delete_cookie("access_token", **opts)
    response.delete_cookie("refresh_token", **opts)


def _extract_token(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token


async def get_current_user_from(request: Request, db) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        sub = payload.get("sub")
        if not isinstance(sub, str) or not ObjectId.is_valid(sub):
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"_id": ObjectId(sub)})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def seed_admin(db):
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_password)}})

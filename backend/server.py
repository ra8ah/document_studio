from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import io
import re
import base64
import csv
import json
import secrets
import logging
import unicodedata
from urllib.parse import quote
from datetime import datetime, timezone, timedelta, date

from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel

import auth
from models import BusinessProfile, ClientIn, DocumentIn, DocumentUpdate, PackageIn, ResetIn
from renderer import compute_totals, TYPE_META
from docdata import build_default_data, default_line_items
import docx_export
import pdf_export

mongo_url = os.environ["MONGO_URL"]
# Works for local MongoDB and Atlas (mongodb+srv://). Pool sized for small hosts / Atlas M0 (500 conn cap).
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=int(os.environ.get("MONGO_MAX_POOL_SIZE", "20")),
    minPoolSize=0,
    serverSelectionTimeoutMS=int(os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000")),
    connectTimeoutMS=10000,
    retryWrites=True,
    appname="document-studio",
)
db = client[os.environ["DB_NAME"]]


def _cors_origins() -> list:
    """CORS must be explicit: credentials are enabled, so "*" (or nothing) is refused at startup."""
    raw = os.environ.get("CORS_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if not origins:
        raise RuntimeError("CORS_ORIGINS is required (comma-separated list of allowed origins)")
    if "*" in origins:
        raise RuntimeError('CORS_ORIGINS must not contain "*" while credentials are enabled')
    return origins


CORS_ORIGINS = _cors_origins()
auth.cookie_samesite()  # validate COOKIE_SAMESITE at startup


def _frontend_url() -> str:
    v = (os.environ.get("FRONTEND_URL") or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[^\s/#?]+(/[^\s#?]*)?", v):
        raise RuntimeError("FRONTEND_URL is required: the public frontend URL (e.g. https://your-app.vercel.app). "
                           "Server PDFs are rendered from its /print route.")
    return v


FRONTEND_URL = _frontend_url()

app = FastAPI()
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agency")

DEFAULT_PREFIXES = {
    "invoice": "INV", "quotation": "QUO", "receipt": "REC", "proposal": "PRO",
    "statement_of_work": "SOW", "service_agreement": "MSA", "nda": "NDA",
    "project_status": "PSR", "maintenance_plan": "MSP", "welcome_doc": "WEL",
    "thank_you_doc": "THX", "letterhead": "LTR", "expense_report": "EXP",
}
UNPAID_STATES = {"draft", "sent", "viewed", "overdue"}
STATUSES = {"draft", "sent", "viewed", "paid", "overdue", "cancelled"}
DOC_SORT_FIELDS = {"created_at", "updated_at", "number", "client_name", "status", "type", "total"}
MAX_PAGE_SIZE = 100


# ---------------- helpers ----------------
async def current_user(request: Request):
    return await auth.get_current_user_from(request, db)


def oid(value, detail: str = "Not found") -> ObjectId:
    """Parse a path id; malformed ids are a clean 404 instead of a 500."""
    if isinstance(value, ObjectId):
        return value
    if not isinstance(value, str) or not ObjectId.is_valid(value):
        raise HTTPException(404, detail)
    return ObjectId(value)


def body_oid(value, field: str) -> ObjectId:
    """Parse an id supplied in a request body; malformed -> 422."""
    if not isinstance(value, str) or not ObjectId.is_valid(value):
        raise HTTPException(422, f"Invalid {field}")
    return ObjectId(value)


def search_regex(text: str) -> dict:
    """Case-insensitive *literal* match: user text is escaped, never interpreted as a regex."""
    return {"$regex": re.escape(text.strip()[:100]), "$options": "i"}


def page_params(page: int, page_size: int):
    if page < 1:
        raise HTTPException(422, "page must be >= 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise HTTPException(422, f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    return (page - 1) * page_size, page_size


def page_envelope(items, total: int, page: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": max(1, -(-total // page_size))}


def _num(expr):
    return {"$convert": {"input": expr, "to": "double", "onError": 0.0, "onNull": 0.0}}


# Same maths as renderer.compute_totals, evaluated inside MongoDB.
_SUBTOTAL = {"$sum": {"$map": {"input": {"$ifNull": ["$line_items", []]}, "as": "i",
                                "in": {"$multiply": [_num("$$i.qty"), _num("$$i.rate")]}}}}
TOTAL_EXPR = {"$let": {"vars": {"sub": _SUBTOTAL}, "in": {"$let": {
    "vars": {"base": {"$subtract": ["$$sub", {"$cond": [
        {"$eq": ["$discount.enabled", True]},
        {"$cond": [{"$eq": ["$discount.mode", "percent"]},
                   {"$divide": [{"$multiply": ["$$sub", _num("$discount.value")]}, 100]},
                   _num("$discount.value")]},
        0]}]}},
    "in": {"$add": ["$$base", {"$cond": [
        {"$eq": ["$tax.enabled", True]},
        {"$cond": [{"$eq": ["$tax.mode", "percent"]},
                   {"$divide": [{"$multiply": ["$$base", _num("$tax.value")]}, 100]},
                   _num("$tax.value")]},
        0]}]}}}}}


def ser(doc: dict) -> dict:
    if not doc:
        return doc
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


async def get_profile() -> dict:
    p = await db.profile.find_one({"_id": "singleton"})
    if not p:
        base = BusinessProfile().model_dump()
        base["prefixes"] = dict(DEFAULT_PREFIXES)
        base["_id"] = "singleton"
        await db.profile.insert_one(base)
        p = base
    p.pop("_id", None)
    if not p.get("prefixes"):
        p["prefixes"] = dict(DEFAULT_PREFIXES)
    return p


async def next_number(dtype: str, profile: dict) -> str:
    prefix = (profile.get("prefixes") or {}).get(dtype) or DEFAULT_PREFIXES.get(dtype, "DOC")
    r = await db.counters.find_one_and_update(
        {"_id": dtype}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    seq = r.get("seq", 1)
    return f"{prefix}-{seq:04d}"


# ---------------- health ----------------
@api.get("/health")
async def health():
    try:
        await db.command("ping")
        return {"status": "ok", "database": "ok"}
    except Exception:
        logger.exception("health: database ping failed")
        return JSONResponse(status_code=503, content={"status": "error", "database": "unreachable"})


# ---------------- auth ----------------
class LoginIn(BaseModel):
    email: str
    password: str


@api.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    uid = str(user["_id"])
    at = auth.create_access_token(uid, email)
    rt = auth.create_refresh_token(uid)
    auth.set_auth_cookies(response, at, rt)
    # tokens live only in httpOnly cookies; never in the response body
    return {"id": uid, "email": email, "name": user.get("name", "Admin"), "role": user.get("role", "admin")}


@api.get("/auth/me")
async def me(user=Depends(current_user)):
    return user


@api.post("/auth/logout")
async def logout(response: Response, user=Depends(current_user)):
    auth.clear_auth_cookies(response)
    return {"ok": True}


@api.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    import jwt
    try:
        payload = jwt.decode(token, auth.get_jwt_secret(), algorithms=[auth.JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token")
        sub = payload.get("sub")
        u = await db.users.find_one({"_id": ObjectId(sub)}) if isinstance(sub, str) and ObjectId.is_valid(sub) else None
        if not u:
            auth.clear_auth_cookies(response)
            raise HTTPException(status_code=401, detail="User no longer exists")
        at = auth.create_access_token(str(u["_id"]), u["email"])
        rt = auth.create_refresh_token(str(u["_id"]))
        auth.set_auth_cookies(response, at, rt)
        return {"ok": True}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------- profile ----------------
@api.get("/profile")
async def read_profile(user=Depends(current_user)):
    return await get_profile()


LOGO_DATA_URI = re.compile(r"^data:image/(svg\+xml|png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+$")
MAX_LOGO_CHARS = 2_800_000  # ~2 MB binary once base64-encoded


def validate_logo(value) -> str:
    """Logos must be an uploaded image embedded as a data URI. Remote URLs are rejected
    so printing never depends on (or leaks requests to) third-party hosts."""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) > MAX_LOGO_CHARS:
        raise HTTPException(413, "Logo is too large (max 2 MB)")
    if not LOGO_DATA_URI.match(v):
        raise HTTPException(400, "Logo must be an uploaded SVG, PNG, JPEG or WebP image (remote URLs are not allowed)")
    if v.startswith("data:image/svg+xml"):
        try:
            svg = base64.b64decode(v.split(",", 1)[1]).decode("utf-8", "ignore").lower()
        except Exception:
            raise HTTPException(400, "Invalid SVG logo")
        if "<script" in svg or "javascript:" in svg or "<foreignobject" in svg:
            raise HTTPException(400, "SVG logo contains disallowed content")
    return v


@api.put("/profile")
async def update_profile(body: dict, user=Depends(current_user)):
    body.pop("_id", None)
    if "logo_url" in body:
        body["logo_url"] = validate_logo(body.get("logo_url"))
    await db.profile.update_one({"_id": "singleton"}, {"$set": body}, upsert=True)
    return await get_profile()


# ---------------- clients ----------------
@api.get("/clients")
async def list_clients(user=Depends(current_user), search: str = "", page: int = 1, page_size: int = 25):
    skip, limit = page_params(page, page_size)
    q = {}
    if search.strip():
        rx = search_regex(search)
        q = {"$or": [{"name": rx}, {"company": rx}, {"email": rx}]}
    total = await db.clients.count_documents(q)
    rows = await db.clients.find(q).sort([("name", 1), ("_id", 1)]).skip(skip).limit(limit).to_list(limit)
    return page_envelope([ser(r) for r in rows], total, page, page_size)


@api.post("/clients")
async def create_client(body: ClientIn, user=Depends(current_user)):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.clients.insert_one(doc)
    return ser(await db.clients.find_one({"_id": r.inserted_id}))


@api.get("/clients/{cid}")
async def get_client(cid: str, user=Depends(current_user)):
    c = await db.clients.find_one({"_id": oid(cid, "Client not found")})
    if not c:
        raise HTTPException(404, "Client not found")
    return ser(c)


@api.put("/clients/{cid}")
async def update_client(cid: str, body: ClientIn, user=Depends(current_user)):
    _id = oid(cid, "Client not found")
    r = await db.clients.update_one({"_id": _id}, {"$set": body.model_dump()})
    if not r.matched_count:
        raise HTTPException(404, "Client not found")
    return ser(await db.clients.find_one({"_id": _id}))


@api.delete("/clients/{cid}")
async def delete_client(cid: str, user=Depends(current_user)):
    r = await db.clients.delete_one({"_id": oid(cid, "Client not found")})
    if not r.deleted_count:
        raise HTTPException(404, "Client not found")
    return {"ok": True}


@api.get("/clients/{cid}/documents")
async def client_documents(cid: str, user=Depends(current_user)):
    if not await db.clients.find_one({"_id": oid(cid, "Client not found")}, {"_id": 1}):
        raise HTTPException(404, "Client not found")
    rows = await db.documents.find({"client_id": cid}).sort("created_at", -1).to_list(1000)
    return [ser(r) for r in rows]


# ---------------- documents ----------------
async def _build_document(dtype: str, client_id, theme, currency, profile):
    cl = None
    if client_id:
        cl = await db.clients.find_one({"_id": body_oid(client_id, "client_id")})
    number = await next_number(dtype, profile)
    cur = currency or (cl.get("currency") if cl else None) or profile.get("default_currency", "USD")
    data = build_default_data(dtype, profile, cl or {}, number)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "type": dtype, "number": number, "status": "draft",
        "client_id": client_id, "client_name": (cl.get("name") if cl else "") if cl else "",
        "theme": theme or "light", "currency": cur, "page_size": "A4",
        "data": data, "line_items": default_line_items(dtype),
        "discount": {"enabled": False, "mode": "percent", "value": 0, "label": "Discount"},
        "tax": {"enabled": False, "mode": "percent", "value": 0, "label": "Tax"},
        "recurring": {"enabled": False, "frequency": "monthly", "next_date": None},
        "paid_date": None,  # share_token is only set once shared (unique sparse index)
        "created_at": now, "updated_at": now,
    }
    return doc


@api.post("/documents")
async def create_document(body: DocumentIn, user=Depends(current_user)):
    if body.type not in TYPE_META:
        raise HTTPException(400, "Unknown document type")
    profile = await get_profile()
    doc = await _build_document(body.type, body.client_id, body.theme, body.currency, profile)
    if body.title:
        doc["data"]["project_reference"] = body.title
    r = await db.documents.insert_one(doc)
    return ser(await db.documents.find_one({"_id": r.inserted_id}))


@api.get("/documents")
async def list_documents(user=Depends(current_user), search: str = "", type: str = "",
                         status: str = "", sort: str = "-created_at", page: int = 1, page_size: int = 25):
    skip, limit = page_params(page, page_size)
    q = {}
    if type:
        if type not in TYPE_META:
            raise HTTPException(422, "Unknown document type")
        q["type"] = type
    if status:
        if status not in STATUSES:
            raise HTTPException(422, "Unknown status")
        q["status"] = status
    if search.strip():
        rx = search_regex(search)
        q["$or"] = [{"number": rx}, {"client_name": rx}, {"data.project_reference": rx}]
    field = sort.lstrip("-")
    if field not in DOC_SORT_FIELDS:
        raise HTTPException(422, f"sort must be one of {sorted(DOC_SORT_FIELDS)} (prefix - for descending)")
    direction = -1 if sort.startswith("-") else 1
    pipeline = [{"$match": q}]
    if field == "total":
        pipeline.append({"$addFields": {"total": TOTAL_EXPR}})
    pipeline += [
        {"$sort": {field: direction, "_id": direction}},
        {"$facet": {
            "items": [{"$skip": skip}, {"$limit": limit}, {"$addFields": {"total": TOTAL_EXPR}}],
            "count": [{"$count": "n"}],
        }},
    ]
    res = (await db.documents.aggregate(pipeline).to_list(1))[0]
    total = res["count"][0]["n"] if res["count"] else 0
    return page_envelope([ser(r) for r in res["items"]], total, page, page_size)


@api.get("/documents/{did}")
async def get_document(did: str, user=Depends(current_user)):
    d = await db.documents.find_one({"_id": oid(did)})
    if not d:
        raise HTTPException(404, "Not found")
    s = ser(d)
    s["totals"] = compute_totals(d)
    return s


DATA_KEY = re.compile(r"^[A-Za-z0-9_]{1,64}$")
# rendered from the document itself, never taken from the client payload
PROTECTED_DATA_KEYS = {"number"}


@api.put("/documents/{did}")
async def update_document(did: str, body: DocumentUpdate, user=Depends(current_user)):
    _id = oid(did)
    payload = body.model_dump(exclude_none=True)
    expected = payload.pop("expected_updated_at", None)
    force = payload.pop("force", False)
    update = {}
    # data is MERGED key by key (dotted $set): fields the editor does not render/scrape
    # (label, logo_url, reference_label, …) are never wiped by a save.
    data = payload.pop("data", None)
    if data is not None:
        if not isinstance(data, dict):
            raise HTTPException(422, "data must be an object")
        if "logo_url" in data:
            data["logo_url"] = validate_logo(data.get("logo_url"))
        for k, v in data.items():
            if not DATA_KEY.match(str(k)):
                raise HTTPException(422, f"Invalid data field name: {k!r}")
            if k not in PROTECTED_DATA_KEYS:
                update[f"data.{k}"] = v
    for k, v in payload.items():
        update[k] = [dict(i) for i in v] if k == "line_items" else v
    if update.get("client_id"):
        cl = await db.clients.find_one({"_id": body_oid(update["client_id"], "client_id")})
        if cl:
            update["client_name"] = cl.get("name", "")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    flt = {"_id": _id}
    if expected and not force:
        flt["updated_at"] = expected
    r = await db.documents.update_one(flt, {"$set": update})
    if not r.matched_count:
        current = await db.documents.find_one({"_id": _id}, {"updated_at": 1})
        if not current:
            raise HTTPException(404, "Not found")
        raise HTTPException(409, {"message": "This document changed elsewhere",
                                  "server_updated_at": current.get("updated_at")})
    d = await db.documents.find_one({"_id": _id})
    s = ser(d)
    s["totals"] = compute_totals(d)
    return s


@api.post("/documents/{did}/reset")
async def reset_document(did: str, body: ResetIn, user=Depends(current_user)):
    """Clear & start fresh: keeps id, type, number, client and status; rebuilds content."""
    src = await db.documents.find_one({"_id": oid(did)})
    if not src:
        raise HTTPException(404, "Not found")
    profile = await get_profile()
    cl = None
    if src.get("client_id") and ObjectId.is_valid(src["client_id"]):
        cl = await db.clients.find_one({"_id": ObjectId(src["client_id"])})
    data = build_default_data(src["type"], profile, cl or {}, src["number"])
    items = default_line_items(src["type"])
    if body.mode == "blank":
        keep = {"number", "label", "reference_label", "logo_url"}  # structural, not content
        data = {k: (v if k in keep else ([] if isinstance(v, list) else "")) for k, v in data.items()}
        data["sections"] = []
        items = []
    update = {
        "data": data, "line_items": items,
        "discount": {"enabled": False, "mode": "percent", "value": 0, "label": "Discount"},
        "tax": {"enabled": False, "mode": "percent", "value": 0, "label": "Tax"},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.update_one({"_id": src["_id"]}, {"$set": update})
    d = await db.documents.find_one({"_id": src["_id"]})
    out = ser(d)
    out["totals"] = compute_totals(d)
    return out


@api.delete("/documents/{did}")
async def delete_document(did: str, user=Depends(current_user)):
    r = await db.documents.delete_one({"_id": oid(did)})
    if not r.deleted_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@api.post("/documents/{did}/status")
async def set_status(did: str, body: dict, user=Depends(current_user)):
    status = body.get("status")
    if status not in STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(STATUSES)}")
    _id = oid(did)
    r = await db.documents.update_one({"_id": _id},
                                      {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return ser(await db.documents.find_one({"_id": _id}))


async def _clone(src: dict, target_type: str, profile: dict, status="draft"):
    number = await next_number(target_type, profile)
    now = datetime.now(timezone.utc).isoformat()
    data = dict(src.get("data", {}))
    data["number"] = number
    data["label"] = TYPE_META.get(target_type, {}).get("label", data.get("label"))
    new = {
        "type": target_type, "number": number, "status": status,
        "client_id": src.get("client_id"), "client_name": src.get("client_name", ""),
        "theme": src.get("theme", "light"), "currency": src.get("currency", "USD"),
        "data": data, "line_items": [dict(i) for i in src.get("line_items", [])],
        "discount": dict(src.get("discount", {})), "tax": dict(src.get("tax", {})),
        "recurring": {"enabled": False, "frequency": "monthly", "next_date": None},
        "paid_date": None,
        "created_at": now, "updated_at": now,
    }
    r = await db.documents.insert_one(new)
    return await db.documents.find_one({"_id": r.inserted_id})


@api.post("/documents/{did}/duplicate")
async def duplicate_document(did: str, user=Depends(current_user)):
    src = await db.documents.find_one({"_id": oid(did)})
    if not src:
        raise HTTPException(404, "Not found")
    profile = await get_profile()
    return ser(await _clone(src, src["type"], profile))


CONVERT_MAP = {"quotation": "invoice", "proposal": "statement_of_work", "invoice": "receipt"}


@api.post("/documents/{did}/convert")
async def convert_document(did: str, body: dict, user=Depends(current_user)):
    src = await db.documents.find_one({"_id": oid(did)})
    if not src:
        raise HTTPException(404, "Not found")
    target = body.get("target_type") or CONVERT_MAP.get(src["type"])
    if target and target not in TYPE_META:
        raise HTTPException(422, "Unknown target_type")
    if not target:
        raise HTTPException(400, "No conversion available for this type")
    profile = await get_profile()
    status = "paid" if target == "receipt" else "draft"
    new = await _clone(src, target, profile, status=status)
    if target == "receipt":
        await db.documents.update_one({"_id": new["_id"]},
                                      {"$set": {"paid_date": datetime.now(timezone.utc).date().isoformat(),
                                                "data.paid_date": datetime.now(timezone.utc).date().isoformat()}})
        new = await db.documents.find_one({"_id": new["_id"]})
    return ser(new)


@api.post("/documents/{did}/mark-paid")
async def mark_paid(did: str, user=Depends(current_user)):
    src = await db.documents.find_one({"_id": oid(did)})
    if not src:
        raise HTTPException(404, "Not found")
    today = datetime.now(timezone.utc).date().isoformat()
    await db.documents.update_one({"_id": src["_id"]},
                                  {"$set": {"status": "paid", "paid_date": today,
                                            "updated_at": datetime.now(timezone.utc).isoformat()}})
    receipt = None
    if src["type"] == "invoice":
        profile = await get_profile()
        r = await _clone(src, "receipt", profile, status="paid")
        await db.documents.update_one({"_id": r["_id"]},
                                      {"$set": {"paid_date": today, "data.paid_date": today}})
        receipt = ser(await db.documents.find_one({"_id": r["_id"]}))
    return {"ok": True, "receipt": receipt}


# ---------------- server PDF (headless Chromium renders the frontend /print route) ----------------
_FN_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def pdf_filename(d: dict) -> tuple:
    """('INV-0012 - Client.pdf' ASCII fallback, same in UTF-8). Empty client -> 'INV-0012.pdf'."""
    clean = lambda v: re.sub(r"\s+", " ", _FN_ILLEGAL.sub(" ", v or "")).strip(" .")  # noqa: E731
    number = clean(d.get("number")) or "document"
    client_name = d.get("client_name") or (d.get("data") or {}).get("bill_to_name") or ""
    if re.fullmatch(r"\[.*\]", client_name.strip()):  # template placeholder like "[Client name]"
        client_name = ""
    client_part = clean(client_name)[:60].strip()
    utf8 = f"{number} - {client_part}.pdf" if client_part else f"{number}.pdf"
    ascii_client = clean(unicodedata.normalize("NFKD", client_part).encode("ascii", "ignore").decode())
    ascii_name = f"{number} - {ascii_client}.pdf" if ascii_client else f"{number}.pdf"
    return ascii_name, utf8


async def _pdf_response(d: dict, size: str):
    size = "Letter" if size == "Letter" else "A4"
    did = str(d["_id"])
    tok = auth.create_print_token(did)
    # token travels in the #fragment: never sent to (or logged by) the frontend host
    url = f"{FRONTEND_URL}/print/{did}?size={size}#t={tok}"
    try:
        pdf = await pdf_export.render_pdf(url, size, d.get("theme", "light"))
    except pdf_export.PdfBusy:
        raise HTTPException(503, "PDF service is busy, please try again in a moment")
    except pdf_export.PdfTimeout:
        logger.error(f"pdf: render timed out for document {did}")
        raise HTTPException(504, "PDF rendering timed out")
    except Exception as e:
        logger.error(f"pdf: render failed for document {did}: {type(e).__name__}")
        raise HTTPException(502, "PDF rendering failed")
    ascii_name, utf8 = pdf_filename(d)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(utf8, safe='')}",
        "Cache-Control": "no-store",
    })


@api.get("/documents/{did}/pdf")
async def document_pdf(did: str, size: str = "A4", user=Depends(current_user)):
    d = await db.documents.find_one({"_id": oid(did)})
    if not d:
        raise HTTPException(404, "Not found")
    return await _pdf_response(d, size)


@api.get("/share/{token}/pdf")
async def share_pdf(token: str, size: str = "A4"):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", token):
        raise HTTPException(404, "Not found")
    d = await db.documents.find_one({"share_token": token})
    if not d:
        raise HTTPException(404, "Not found")
    return await _pdf_response(d, size)


@api.get("/print/{did}")
async def print_data(did: str, request: Request):
    """Data for the frontend /print route. Accepts only a print token (X-Print-Token) bound to this id."""
    tok = request.headers.get("X-Print-Token", "")
    if not tok or not auth.verify_print_token(tok, did):
        raise HTTPException(401, "Invalid or expired print token")
    d = await db.documents.find_one({"_id": oid(did)})
    if not d:
        raise HTTPException(404, "Not found")
    s = ser(d)
    s["totals"] = compute_totals(d)
    s.pop("share_token", None)
    return JSONResponse(s, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                    "X-Robots-Tag": "noindex, nofollow"})


@api.get("/health/pdf")
async def health_pdf():
    return {"status": "ok", **pdf_export.status()}


# ---------------- exports ----------------
@api.get("/documents/{did}/docx")
async def document_docx(did: str, user=Depends(current_user)):
    d = await db.documents.find_one({"_id": oid(did)})
    if not d:
        raise HTTPException(404, "Not found")
    data = docx_export.build_docx(ser(d))
    fn = f"{d.get('number','document')}.docx"
    return StreamingResponse(io.BytesIO(data),
                             media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


# ---------------- share ----------------
@api.post("/documents/{did}/share")
async def share_document(did: str, user=Depends(current_user)):
    d = await db.documents.find_one({"_id": oid(did)})
    if not d:
        raise HTTPException(404, "Not found")
    token = d.get("share_token") or secrets.token_urlsafe(16)
    await db.documents.update_one({"_id": d["_id"]}, {"$set": {"share_token": token}})
    return {"token": token, "id": did}


@api.get("/share/{token}")
async def share_view(token: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", token):
        raise HTTPException(404, "Not found")
    d = await db.documents.find_one({"share_token": token})
    if not d:
        raise HTTPException(404, "Not found")
    if d.get("status") == "sent":
        await db.documents.update_one({"_id": d["_id"]}, {"$set": {"status": "viewed"}})
    s = ser(d)
    s["totals"] = compute_totals(d)
    return s


# ---------------- packages / saved items ----------------
@api.get("/packages")
async def list_packages(user=Depends(current_user)):
    rows = await db.packages.find({}).sort("description", 1).to_list(500)
    return [ser(r) for r in rows]


@api.post("/packages")
async def create_package(body: PackageIn, user=Depends(current_user)):
    r = await db.packages.insert_one(body.model_dump())
    return ser(await db.packages.find_one({"_id": r.inserted_id}))


@api.delete("/packages/{pid}")
async def delete_package(pid: str, user=Depends(current_user)):
    r = await db.packages.delete_one({"_id": oid(pid)})
    if not r.deleted_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


# ---------------- recurring ----------------
def _advance(d: date, freq: str) -> date:
    if freq == "weekly":
        return d + timedelta(days=7)
    if freq == "yearly":
        return date(d.year + 1, d.month, d.day)
    m = d.month + 1
    y = d.year + (1 if m > 12 else 0)
    m = 1 if m > 12 else m
    day = min(d.day, 28)
    return date(y, m, day)


@api.post("/recurring/run")
async def run_recurring(user=Depends(current_user)):
    today = datetime.now(timezone.utc).date()
    profile = await get_profile()
    created = 0
    cursor = db.documents.find({"recurring.enabled": True})
    async for src in cursor:
        rec = src.get("recurring", {})
        nd = rec.get("next_date")
        if not nd:
            continue
        try:
            nxt = date.fromisoformat(nd)
        except Exception:
            continue
        while nxt <= today:
            await _clone(src, src["type"], profile, status="draft")
            created += 1
            nxt = _advance(nxt, rec.get("frequency", "monthly"))
        await db.documents.update_one({"_id": src["_id"]},
                                      {"$set": {"recurring.next_date": nxt.isoformat()}})
    return {"created": created}


# ---------------- dashboard ----------------
@api.get("/dashboard")
async def dashboard(user=Depends(current_user)):
    today = datetime.now(timezone.utc).date().isoformat()
    month_key = today[:7]
    unpaid_invoice = {"type": "invoice", "status": {"$in": sorted(UNPAID_STATES)}}
    pipeline = [{"$facet": {
        "outstanding": [
            {"$match": unpaid_invoice},
            {"$group": {"_id": "$currency", "sum": {"$sum": TOTAL_EXPR}, "n": {"$sum": 1}}},
        ],
        "overdue": [
            # ISO YYYY-MM-DD strings compare chronologically; malformed dates are ignored
            {"$match": {**unpaid_invoice, "data.due_date": {"$regex": r"^\d{4}-\d{2}-\d{2}$", "$lt": today}}},
            {"$sort": {"data.due_date": 1}},
            {"$limit": 100},
            {"$project": {"_id": 0, "id": {"$toString": "$_id"}, "number": 1, "client_name": {"$ifNull": ["$client_name", ""]},
                          "total": TOTAL_EXPR, "currency": 1, "due_date": "$data.due_date"}},
        ],
        "overdue_count": [
            {"$match": {**unpaid_invoice, "data.due_date": {"$regex": r"^\d{4}-\d{2}-\d{2}$", "$lt": today}}},
            {"$count": "n"},
        ],
        "revenue": [
            {"$match": {"status": "paid", "type": {"$in": ["invoice", "receipt"]},
                        "paid_date": {"$regex": "^" + re.escape(month_key)}}},
            {"$group": {"_id": "$currency", "sum": {"$sum": TOTAL_EXPR}}},
        ],
        "recent": [
            {"$sort": {"created_at": -1}},
            {"$limit": 8},
            {"$addFields": {"total": TOTAL_EXPR}},
        ],
        "count": [{"$count": "n"}],
    }}]
    r = (await db.documents.aggregate(pipeline).to_list(1))[0]
    first = lambda k, f: (r[k][0][f] if r[k] else 0)  # noqa: E731
    profile = await get_profile()
    cur = profile.get("default_currency", "USD")
    # never add different currencies together: headline = default currency, rest as breakdown
    by_cur = lambda rows: {(x["_id"] or cur): float(x["sum"]) for x in rows}  # noqa: E731
    out_by, rev_by = by_cur(r["outstanding"]), by_cur(r["revenue"])
    return {
        "outstanding": out_by.get(cur, 0.0),
        "outstanding_by_currency": out_by,
        "unpaid_count": int(sum(x["n"] for x in r["outstanding"])),
        "this_month_revenue": rev_by.get(cur, 0.0),
        "revenue_by_currency": rev_by,
        "overdue": r["overdue"],
        "overdue_count": int(first("overdue_count", "n")),
        "recent": [ser(x) for x in r["recent"]],
        "currency": cur,
        "total_documents": int(first("count", "n")),
    }


# ---------------- data export ----------------
@api.get("/export/documents.json")
async def export_documents_json(user=Depends(current_user)):
    rows = await db.documents.find({}).to_list(10000)
    data = [ser(r) for r in rows]
    return StreamingResponse(io.BytesIO(json.dumps(data, default=str, indent=2).encode()),
                             media_type="application/json",
                             headers={"Content-Disposition": 'attachment; filename="documents.json"'})


@api.get("/export/documents.csv")
async def export_documents_csv(user=Depends(current_user)):
    rows = await db.documents.find({}).to_list(10000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["number", "type", "status", "client", "currency", "total", "issue_date", "created_at"])
    for r in rows:
        w.writerow([r.get("number"), r.get("type"), r.get("status"), r.get("client_name", ""),
                    r.get("currency"), compute_totals(r)["total"],
                    (r.get("data") or {}).get("issue_date", ""), r.get("created_at")])
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="documents.csv"'})


@api.get("/export/clients.csv")
async def export_clients_csv(user=Depends(current_user)):
    rows = await db.clients.find({}).to_list(10000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "company", "email", "phone", "address", "tax_id", "currency"])
    for r in rows:
        w.writerow([r.get("name"), r.get("company"), r.get("email"), r.get("phone"),
                    r.get("address"), r.get("tax_id"), r.get("currency")])
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="clients.csv"'})


@api.get("/meta/types")
async def meta_types(user=Depends(current_user)):
    return [{"id": k, "label": v["label"], "layout": v["layout"]} for k, v in TYPE_META.items()]


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Print-Token"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(InvalidId)
async def _invalid_id(request: Request, exc: InvalidId):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.exception_handler(DuplicateKeyError)
async def _duplicate_key(request: Request, exc: DuplicateKeyError):
    return JSONResponse(status_code=409, content={"detail": "A record with this value already exists"})


async def ensure_index(coll, keys, **opts):
    """Idempotent create_index: recreates an index whose key matches but options differ."""
    want = {"unique": bool(opts.get("unique")), "sparse": bool(opts.get("sparse"))}
    for name, spec in (await coll.index_information()).items():
        if name != "_id_" and list(spec["key"]) == list(keys):
            if {"unique": bool(spec.get("unique")), "sparse": bool(spec.get("sparse"))} == want:
                return name
            logger.info(f"index {coll.name}.{name}: options changed, recreating")
            await coll.drop_index(name)
    return await coll.create_index(keys, **opts)


INDEXES = [
    ("users", [("email", 1)], {"unique": True}),
    ("documents", [("number", 1)], {"unique": True}),
    ("documents", [("client_id", 1)], {}),
    ("documents", [("status", 1), ("type", 1)], {}),
    ("documents", [("created_at", -1)], {}),
    ("documents", [("share_token", 1)], {"unique": True, "sparse": True}),
    ("documents", [("type", 1)], {}),
    ("clients", [("name", 1)], {}),
]


@app.on_event("startup")
async def startup():
    # sparse indexes still index explicit nulls: drop legacy "share_token: null" fields first
    await db.documents.update_many({"share_token": None}, {"$unset": {"share_token": ""}})
    for coll, keys, opts in INDEXES:
        try:
            await ensure_index(db[coll], keys, **opts)
        except Exception as e:  # e.g. duplicate numbers in legacy data: keep serving, log loudly
            logger.error(f"index {coll} {keys}: {e}")
    await auth.seed_admin(db)
    await get_profile()


@app.on_event("shutdown")
async def shutdown():
    await pdf_export.shutdown()
    client.close()

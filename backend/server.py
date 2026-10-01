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
from datetime import datetime, timezone, timedelta, date

from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic import BaseModel

import auth
from models import BusinessProfile, ClientIn, DocumentIn, DocumentUpdate, PackageIn
from renderer import compute_totals, TYPE_META
from docdata import build_default_data, default_line_items
import docx_export

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

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


# ---------------- helpers ----------------
async def current_user(request: Request):
    return await auth.get_current_user_from(request, db)


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
    return {"id": uid, "email": email, "name": user.get("name", "Admin"), "role": user.get("role", "admin"), "token": at}


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
        u = await db.users.find_one({"_id": ObjectId(payload["sub"])})
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
async def list_clients(user=Depends(current_user), search: str = ""):
    q = {}
    if search:
        rx = {"$regex": search, "$options": "i"}
        q = {"$or": [{"name": rx}, {"company": rx}, {"email": rx}]}
    rows = await db.clients.find(q).sort("name", 1).to_list(1000)
    return [ser(r) for r in rows]


@api.post("/clients")
async def create_client(body: ClientIn, user=Depends(current_user)):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.clients.insert_one(doc)
    return ser(await db.clients.find_one({"_id": r.inserted_id}))


@api.get("/clients/{cid}")
async def get_client(cid: str, user=Depends(current_user)):
    c = await db.clients.find_one({"_id": ObjectId(cid)})
    if not c:
        raise HTTPException(404, "Client not found")
    return ser(c)


@api.put("/clients/{cid}")
async def update_client(cid: str, body: ClientIn, user=Depends(current_user)):
    await db.clients.update_one({"_id": ObjectId(cid)}, {"$set": body.model_dump()})
    return ser(await db.clients.find_one({"_id": ObjectId(cid)}))


@api.delete("/clients/{cid}")
async def delete_client(cid: str, user=Depends(current_user)):
    await db.clients.delete_one({"_id": ObjectId(cid)})
    return {"ok": True}


@api.get("/clients/{cid}/documents")
async def client_documents(cid: str, user=Depends(current_user)):
    rows = await db.documents.find({"client_id": cid}).sort("created_at", -1).to_list(1000)
    return [ser(r) for r in rows]


# ---------------- documents ----------------
async def _build_document(dtype: str, client_id, theme, currency, profile):
    cl = None
    if client_id:
        cl = await db.clients.find_one({"_id": ObjectId(client_id)})
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
        "share_token": None, "paid_date": None,
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
                         status: str = "", sort: str = "-created_at"):
    q = {}
    if type:
        q["type"] = type
    if status:
        q["status"] = status
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"number": rx}, {"client_name": rx}, {"data.project_reference": rx}]
    field = sort.lstrip("-")
    direction = -1 if sort.startswith("-") else 1
    rows = await db.documents.find(q).sort(field, direction).to_list(2000)
    out = []
    for r in rows:
        s = ser(r)
        s["total"] = compute_totals(r)["total"]
        out.append(s)
    return out


@api.get("/documents/{did}")
async def get_document(did: str, user=Depends(current_user)):
    d = await db.documents.find_one({"_id": ObjectId(did)})
    if not d:
        raise HTTPException(404, "Not found")
    s = ser(d)
    s["totals"] = compute_totals(d)
    return s


@api.put("/documents/{did}")
async def update_document(did: str, body: DocumentUpdate, user=Depends(current_user)):
    update = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if "data" in update and "logo_url" in update["data"]:
        update["data"]["logo_url"] = validate_logo(update["data"].get("logo_url"))
    if "line_items" in update:
        update["line_items"] = [dict(i) for i in update["line_items"]]
    if "client_id" in update and update["client_id"]:
        cl = await db.clients.find_one({"_id": ObjectId(update["client_id"])})
        if cl:
            update["client_name"] = cl.get("name", "")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.documents.update_one({"_id": ObjectId(did)}, {"$set": update})
    d = await db.documents.find_one({"_id": ObjectId(did)})
    s = ser(d)
    s["totals"] = compute_totals(d)
    return s


@api.delete("/documents/{did}")
async def delete_document(did: str, user=Depends(current_user)):
    await db.documents.delete_one({"_id": ObjectId(did)})
    return {"ok": True}


@api.post("/documents/{did}/status")
async def set_status(did: str, body: dict, user=Depends(current_user)):
    status = body.get("status")
    await db.documents.update_one({"_id": ObjectId(did)},
                                  {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return ser(await db.documents.find_one({"_id": ObjectId(did)}))


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
        "share_token": None, "paid_date": None,
        "created_at": now, "updated_at": now,
    }
    r = await db.documents.insert_one(new)
    return await db.documents.find_one({"_id": r.inserted_id})


@api.post("/documents/{did}/duplicate")
async def duplicate_document(did: str, user=Depends(current_user)):
    src = await db.documents.find_one({"_id": ObjectId(did)})
    if not src:
        raise HTTPException(404, "Not found")
    profile = await get_profile()
    return ser(await _clone(src, src["type"], profile))


CONVERT_MAP = {"quotation": "invoice", "proposal": "statement_of_work", "invoice": "receipt"}


@api.post("/documents/{did}/convert")
async def convert_document(did: str, body: dict, user=Depends(current_user)):
    src = await db.documents.find_one({"_id": ObjectId(did)})
    if not src:
        raise HTTPException(404, "Not found")
    target = body.get("target_type") or CONVERT_MAP.get(src["type"])
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
    src = await db.documents.find_one({"_id": ObjectId(did)})
    if not src:
        raise HTTPException(404, "Not found")
    today = datetime.now(timezone.utc).date().isoformat()
    await db.documents.update_one({"_id": ObjectId(did)},
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


# ---------------- exports ----------------
@api.get("/documents/{did}/docx")
async def document_docx(did: str, user=Depends(current_user)):
    d = await db.documents.find_one({"_id": ObjectId(did)})
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
    d = await db.documents.find_one({"_id": ObjectId(did)})
    if not d:
        raise HTTPException(404, "Not found")
    token = d.get("share_token") or secrets.token_urlsafe(16)
    await db.documents.update_one({"_id": ObjectId(did)}, {"$set": {"share_token": token}})
    return {"token": token, "id": did}


@api.get("/share/{token}")
async def share_view(token: str):
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
    await db.packages.delete_one({"_id": ObjectId(pid)})
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
    docs = await db.documents.find({}).to_list(5000)
    today = datetime.now(timezone.utc).date()
    month_key = today.strftime("%Y-%m")
    outstanding = 0.0
    unpaid_count = 0
    overdue = []
    this_month_revenue = 0.0
    for d in docs:
        total = compute_totals(d)["total"]
        if d["type"] == "invoice" and d.get("status") in UNPAID_STATES:
            outstanding += total
            unpaid_count += 1
            due = (d.get("data") or {}).get("due_date")
            try:
                if due and date.fromisoformat(due) < today:
                    overdue.append({"id": str(d["_id"]), "number": d.get("number"),
                                    "client_name": d.get("client_name", ""), "total": total,
                                    "currency": d.get("currency"), "due_date": due})
            except Exception:
                pass
        if d.get("status") == "paid" and d["type"] in ("invoice", "receipt"):
            pd = d.get("paid_date") or ""
            if pd.startswith(month_key):
                this_month_revenue += total
    recent = await db.documents.find({}).sort("created_at", -1).to_list(8)
    recent_out = []
    for r in recent:
        s = ser(r)
        s["total"] = compute_totals(r)["total"]
        recent_out.append(s)
    # currency for headline stats = default
    profile = await get_profile()
    return {
        "outstanding": outstanding,
        "unpaid_count": unpaid_count,
        "this_month_revenue": this_month_revenue,
        "overdue": overdue,
        "overdue_count": len(overdue),
        "recent": recent_out,
        "currency": profile.get("default_currency", "USD"),
        "total_documents": len(docs),
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
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await auth.seed_admin(db)
    try:
        await db.users.create_index("email", unique=True)
        await db.clients.create_index("name")
        await db.documents.create_index("type")
        await db.documents.create_index("share_token")
    except Exception as e:
        logger.warning(f"index: {e}")
    await get_profile()


@app.on_event("shutdown")
async def shutdown():
    client.close()

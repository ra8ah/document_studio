# Run serially: pytest -n 0 tests/test_hardening.py  (the dashboard check compares against a quiet DB)
"""Hardening checks: Atlas-ready Mongo usage, ids, search/sort/status whitelists, pagination,
aggregation dashboard, cookies, CORS. Credentials come from env / backend/.env, never hard-coded.
Everything created is deleted and the numbering counters are restored afterwards."""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from renderer import compute_totals  # noqa: E402


def _env():
    vals = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return {**vals, **os.environ}


ENV = _env()
BASE = ENV.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
# Header-level checks (Set-Cookie attributes, CORS) hit the app directly: the Emergent preview
# ingress rewrites Set-Cookie (adds SameSite=None + its own Domain) and answers preflights itself.
DIRECT = ENV.get("BACKEND_DIRECT_URL", "http://localhost:8001").rstrip("/")
BAD = "not-an-id"
MISSING = "65a0000000000000000000ff"  # valid ObjectId that does not exist (deterministic for xdist)


@pytest.fixture(scope="module")
def db():
    return MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]


@pytest.fixture(scope="module")
def s(db):
    counters = list(db.counters.find())
    sess = requests.Session()
    r = sess.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]})
    assert r.status_code == 200
    sess.login_response = r
    sess.made = {"documents": [], "clients": [], "packages": []}
    yield sess
    for kind, ids in sess.made.items():
        for i in ids:
            sess.delete(f"{BASE}/api/{kind}/{i}")
    db.counters.delete_many({})
    if counters:
        db.counters.insert_many(counters)


def mk_doc(s, **body):
    d = s.post(f"{BASE}/api/documents", json={"type": "invoice", **body}).json()
    s.made["documents"].append(d["id"])
    return d


def mk_client(s, name):
    c = s.post(f"{BASE}/api/clients", json={"name": name}).json()
    s.made["clients"].append(c["id"])
    return c


# ---------------------------------------------------------------- health / auth
def test_health():
    r = requests.get(f"{BASE}/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "ok"}


def test_login_body_has_no_token_and_cookie_flags(s):
    assert "token" not in s.login_response.json() and "access_token" not in s.login_response.json()
    r = requests.post(f"{DIRECT}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]})
    assert "token" not in r.json()
    raw = r.headers.get("set-cookie", "")
    for name in ("access_token=", "refresh_token="):
        assert name in raw
    low = raw.lower()
    assert low.count("httponly") >= 2 and low.count("secure") >= 2
    assert low.count("samesite=lax") >= 2 and low.count("path=/") >= 2


def _tok(sub, typ):
    return jwt.encode({"sub": sub, "type": typ, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                      ENV["JWT_SECRET"], algorithm="HS256")


@pytest.mark.parametrize("sub", [MISSING, "garbage"])
def test_refresh_for_missing_or_malformed_user_is_401(sub):
    r = requests.post(f"{BASE}/api/auth/refresh", cookies={"refresh_token": _tok(sub, "refresh")})
    assert r.status_code == 401


@pytest.mark.parametrize("sub", [MISSING, "garbage"])
def test_access_token_for_missing_or_malformed_user_is_401(sub):
    assert requests.get(f"{BASE}/api/auth/me", cookies={"access_token": _tok(sub, "access")}).status_code == 401


def test_refresh_keeps_session(s):
    r = s.post(f"{BASE}/api/auth/refresh")
    assert r.status_code == 200 and s.get(f"{BASE}/api/auth/me").status_code == 200


# ---------------------------------------------------------------- ids
ID_ROUTES = [
    ("get", "/documents/{id}", None), ("put", "/documents/{id}", {}), ("delete", "/documents/{id}", None),
    ("post", "/documents/{id}/status", {"status": "sent"}), ("post", "/documents/{id}/duplicate", None),
    ("post", "/documents/{id}/convert", {}), ("post", "/documents/{id}/mark-paid", None),
    ("get", "/documents/{id}/docx", None), ("post", "/documents/{id}/share", None),
    ("get", "/clients/{id}", None), ("put", "/clients/{id}", {"name": "x"}), ("delete", "/clients/{id}", None),
    ("get", "/clients/{id}/documents", None), ("delete", "/packages/{id}", None),
]


@pytest.mark.parametrize("method,path,body", ID_ROUTES)
@pytest.mark.parametrize("ident", [BAD, MISSING, "1234", "%00"])
def test_bad_or_missing_ids_are_404(s, method, path, body, ident):
    r = getattr(s, method)(f"{BASE}/api{path.format(id=ident)}", **({"json": body} if body is not None else {}))
    # "%00" is rejected with 400 by the HTTP layer/ingress before it reaches the app; any clean 4xx is fine
    assert r.status_code in ((400, 404) if ident == "%00" else (404,)), (method, path, ident, r.status_code, r.text[:120])


def test_bad_share_token_404():
    assert requests.get(f"{BASE}/api/share/..%2F..").status_code == 404
    assert requests.get(f"{BASE}/api/share/{'x' * 20}").status_code == 404


def test_body_client_id_validated(s):
    assert s.post(f"{BASE}/api/documents", json={"type": "invoice", "client_id": "zzz"}).status_code == 422
    d = mk_doc(s)
    assert s.put(f"{BASE}/api/documents/{d['id']}", json={"client_id": "zzz"}).status_code == 422


# ---------------------------------------------------------------- search / whitelists
def test_search_is_literal_not_regex(s):
    mk_client(s, "TEST_Literal a.b (x)")
    for q in ["(", "[", "*", "\\", "(x)"]:
        r = s.get(f"{BASE}/api/clients", params={"search": q})
        assert r.status_code == 200, q
    assert s.get(f"{BASE}/api/clients", params={"search": ".*"}).json()["total"] == 0
    assert s.get(f"{BASE}/api/clients", params={"search": "a.b (x)"}).json()["total"] == 1
    assert s.get(f"{BASE}/api/documents", params={"search": "(.*"}).status_code == 200


@pytest.mark.parametrize("params", [{"sort": "password_hash"}, {"sort": "-$where"}, {"status": "hacked"},
                                    {"type": "nope"}, {"page": 0}, {"page_size": 101}, {"page_size": 0}])
def test_documents_list_rejects_bad_params(s, params):
    assert s.get(f"{BASE}/api/documents", params=params).status_code == 422


def test_status_whitelist(s):
    d = mk_doc(s)
    assert s.post(f"{BASE}/api/documents/{d['id']}/status", json={"status": "hacked"}).status_code == 422
    assert s.post(f"{BASE}/api/documents/{d['id']}/status", json={"status": "sent"}).json()["status"] == "sent"


# ---------------------------------------------------------------- pagination
def test_clients_pagination(s):
    for i in range(3):
        mk_client(s, f"TEST_Page {i}")
    r = s.get(f"{BASE}/api/clients", params={"search": "TEST_Page", "page_size": 2}).json()
    assert set(r) == {"items", "total", "page", "page_size", "pages"}
    assert r["total"] == 3 and len(r["items"]) == 2 and r["pages"] == 2
    r2 = s.get(f"{BASE}/api/clients", params={"search": "TEST_Page", "page_size": 2, "page": 2}).json()
    assert len(r2["items"]) == 1
    assert {c["id"] for c in r["items"]}.isdisjoint({c["id"] for c in r2["items"]})


def test_documents_pagination_and_total_sort(s):
    for rate in (10, 300, 20):
        d = mk_doc(s)
        s.put(f"{BASE}/api/documents/{d['id']}", json={"line_items": [{"description": "x", "qty": 1, "rate": rate}]})
    r = s.get(f"{BASE}/api/documents", params={"sort": "-total", "page_size": 100}).json()
    totals = [x["total"] for x in r["items"]]
    assert totals == sorted(totals, reverse=True) and "total" in r and r["page"] == 1
    p1 = s.get(f"{BASE}/api/documents", params={"page_size": 1}).json()
    assert len(p1["items"]) == 1 and p1["pages"] == p1["total"]


# ---------------------------------------------------------------- dashboard aggregation == reference
def _reference_dashboard(db):
    from datetime import date
    UNPAID = {"draft", "sent", "viewed", "overdue"}
    today = datetime.now(timezone.utc).date()
    out = {"outstanding": 0.0, "unpaid_count": 0, "this_month_revenue": 0.0, "overdue_count": 0}
    docs = list(db.documents.find({"deleted_at": None}))  # trashed docs never count
    for d in docs:
        t = compute_totals(d)["total"]
        if d["type"] == "invoice" and d.get("status") in UNPAID:
            out["outstanding"] += t
            out["unpaid_count"] += 1
            due = (d.get("data") or {}).get("due_date")
            try:
                if due and date.fromisoformat(due) < today:
                    out["overdue_count"] += 1
            except Exception:
                pass
        if d.get("status") == "paid" and d["type"] in ("invoice", "receipt") and (d.get("paid_date") or "").startswith(today.strftime("%Y-%m")):
            out["this_month_revenue"] += t
    out["total_documents"] = len(docs)
    return out


def test_dashboard_aggregation_matches_reference(s, db):
    a = mk_doc(s)
    s.put(f"{BASE}/api/documents/{a['id']}", json={
        "line_items": [{"description": "x", "qty": 3, "rate": 1000.5}, {"description": "y", "qty": 2, "rate": 99.99}],
        "discount": {"enabled": True, "mode": "percent", "value": 10}, "tax": {"enabled": True, "mode": "fixed", "value": 18},
        "data": {**a["data"], "due_date": "2020-01-01"}})
    b = mk_doc(s)
    s.put(f"{BASE}/api/documents/{b['id']}", json={"line_items": [{"description": "z", "qty": 1, "rate": 5000}],
                                                    "tax": {"enabled": True, "mode": "percent", "value": 18}})
    r = s.post(f"{BASE}/api/documents/{b['id']}/mark-paid").json()
    s.made["documents"].append(r["receipt"]["id"])
    c = mk_doc(s)
    s.put(f"{BASE}/api/documents/{c['id']}", json={"data": {**c["data"], "due_date": "not-a-date"}})
    got = s.get(f"{BASE}/api/dashboard").json()
    ref = _reference_dashboard(db)
    for k in ("outstanding", "this_month_revenue"):
        assert abs(got[k] - ref[k]) < 1e-6, (k, got[k], ref[k])
    for k in ("unpaid_count", "overdue_count", "total_documents"):
        assert got[k] == ref[k], (k, got[k], ref[k])
    assert len(got["recent"]) == min(8, ref["total_documents"]) and "total" in got["recent"][0]
    assert any(o["id"] == a["id"] for o in got["overdue"])


# ---------------------------------------------------------------- share tokens + indexes
def test_share_tokens_unique_and_absent_until_shared(s, db):
    d1, d2 = mk_doc(s), mk_doc(s)
    assert "share_token" not in db.documents.find_one({"_id": ObjectId(d1["id"])})
    t1 = s.post(f"{BASE}/api/documents/{d1['id']}/share").json()["token"]
    t2 = s.post(f"{BASE}/api/documents/{d2['id']}/share").json()["token"]
    assert t1 != t2 and requests.get(f"{BASE}/api/share/{t1}").status_code == 200
    idx = {tuple(v["key"]): v for v in db.documents.index_information().values()}
    assert idx[(("share_token", 1),)].get("unique") and idx[(("share_token", 1),)].get("sparse")
    assert idx[(("number", 1),)].get("unique")
    for k in [(("client_id", 1),), (("status", 1), ("type", 1)), (("created_at", -1),)]:
        assert k in idx
    assert db.users.index_information()["email_1"].get("unique")


# ---------------------------------------------------------------- CORS
def test_cors_only_allows_configured_origins():
    allowed = ENV["CORS_ORIGINS"].split(",")[0].strip()
    pre = {"Access-Control-Request-Method": "GET"}
    ok = requests.options(f"{DIRECT}/api/health", headers={"Origin": allowed, **pre})
    assert ok.status_code == 200 and ok.headers.get("access-control-allow-origin") == allowed
    bad = requests.options(f"{DIRECT}/api/health", headers={"Origin": "https://evil.example", **pre})
    assert bad.headers.get("access-control-allow-origin") is None


@pytest.mark.parametrize("env", [{"CORS_ORIGINS": "*"}, {"CORS_ORIGINS": ""}, {"CORS_ORIGINS": "https://a.example,*"},
                                 {"COOKIE_SAMESITE": "bogus"}])
def test_startup_refuses_unsafe_config(env):
    r = subprocess.run([sys.executable, "-c", "import server"], cwd=ROOT, env={**os.environ, **env},
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "RuntimeError" in r.stderr

"""Server PDF: print-token scope, filename rules, routes. Run with REACT_APP_BACKEND_URL exported."""
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
import requests
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import dotenv_values  # noqa: E402

ENV = {**dotenv_values(Path(__file__).resolve().parent.parent / ".env"), **os.environ}
BASE = ENV.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def ctx():
    db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    counters = list(db.counters.find())
    s = requests.Session()
    assert s.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}).ok
    a = s.post(f"{BASE}/api/documents", json={"type": "invoice"}).json()
    b = s.post(f"{BASE}/api/documents", json={"type": "invoice"}).json()
    yield s, a, b
    for d in (a, b):
        s.delete(f"{BASE}/api/documents/{d['id']}")
    db.counters.delete_many({})
    if counters:
        db.counters.insert_many(counters)


def _tok(doc_id, secs=60, typ="print"):
    import auth
    os.environ.setdefault("JWT_SECRET", ENV["JWT_SECRET"])
    if typ == "print" and secs == 60:
        return auth.create_print_token(doc_id)
    return jwt.encode({"doc": doc_id, "type": typ, "exp": datetime.now(timezone.utc) + timedelta(seconds=secs)},
                      ENV["JWT_SECRET"], algorithm="HS256")


def test_print_data_requires_token(ctx):
    _, a, _ = ctx
    assert requests.get(f"{BASE}/api/print/{a['id']}").status_code == 401
    assert requests.get(f"{BASE}/api/print/{a['id']}", headers={"X-Print-Token": "garbage"}).status_code == 401


def test_print_token_bound_to_one_doc(ctx):
    _, a, b = ctx
    t = _tok(a["id"])
    r = requests.get(f"{BASE}/api/print/{a['id']}", headers={"X-Print-Token": t})
    assert r.status_code == 200 and r.json()["id"] == a["id"]
    assert "share_token" not in r.json()
    assert r.headers.get("referrer-policy") == "no-referrer"
    assert "noindex" in r.headers.get("x-robots-tag", "")
    assert requests.get(f"{BASE}/api/print/{b['id']}", headers={"X-Print-Token": t}).status_code == 401


def test_print_token_expired_rejected(ctx):
    _, a, _ = ctx
    t = _tok(a["id"], secs=-5)
    assert requests.get(f"{BASE}/api/print/{a['id']}", headers={"X-Print-Token": t}).status_code == 401


def test_print_token_useless_elsewhere(ctx):
    _, a, _ = ctx
    t = _tok(a["id"])
    for path in ("/api/auth/me", f"/api/documents/{a['id']}", "/api/documents", f"/api/documents/{a['id']}/pdf"):
        assert requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {t}"}).status_code == 401, path
        assert requests.get(f"{BASE}{path}", cookies={"access_token": t}).status_code == 401, path
    # an access-type token is not accepted as a print token
    assert requests.get(f"{BASE}/api/print/{a['id']}", headers={"X-Print-Token": _tok(a["id"], typ="access")}).status_code == 401


def test_pdf_requires_auth(ctx):
    _, a, _ = ctx
    assert requests.get(f"{BASE}/api/documents/{a['id']}/pdf").status_code == 401
    assert requests.get(f"{BASE}/api/share/notarealtoken123/pdf").status_code == 404


def test_pdf_download_and_filename(ctx):
    s, a, _ = ctx
    s.put(f"{BASE}/api/documents/{a['id']}", json={"data": {"bill_to_name": "Zoë Ltd"}})
    t0 = time.time()
    r = s.get(f"{BASE}/api/documents/{a['id']}/pdf", params={"size": "Letter"}, timeout=60)
    assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:200]
    assert time.time() - t0 < 30
    cd = r.headers["content-disposition"]
    assert f'filename="{a["number"]} - Zoe Ltd.pdf"' in cd
    assert f"filename*=UTF-8''{a['number']}%20-%20Zo%C3%AB%20Ltd.pdf" in cd
    assert "content-disposition" in r.headers.get("access-control-expose-headers", "content-disposition").lower()


def test_health_pdf():
    r = requests.get(f"{BASE}/api/health/pdf")
    assert r.status_code == 200 and r.json()["max_concurrent"] == 2 and r.json()["timeout_s"] == 30


@pytest.mark.parametrize("client,data_name,want_ascii,want_utf8", [
    ("", "", "INV-0012.pdf", "INV-0012.pdf"),
    ("", "[Client name]", "INV-0012.pdf", "INV-0012.pdf"),
    ('A/B:C*D?"E<F>G|H\\I', "", "INV-0012 - A B C D E F G H I.pdf", "INV-0012 - A B C D E F G H I.pdf"),
    ("  Acme \t\n  Co  ", "", "INV-0012 - Acme Co.pdf", "INV-0012 - Acme Co.pdf"),
    ("株式会社テスト", "", "INV-0012.pdf", "INV-0012 - 株式会社テスト.pdf"),
    ("Café Müller", "", "INV-0012 - Cafe Muller.pdf", "INV-0012 - Café Müller.pdf"),
    ("", "Bill To Name", "INV-0012 - Bill To Name.pdf", "INV-0012 - Bill To Name.pdf"),
])
def test_pdf_filename_rules(client, data_name, want_ascii, want_utf8):
    os.environ.update({k: v for k, v in ENV.items() if isinstance(v, str)})
    from server import pdf_filename
    assert pdf_filename({"number": "INV-0012", "client_name": client, "data": {"bill_to_name": data_name}}) == (want_ascii, want_utf8)


def test_pdf_filename_caps_client_at_60():
    os.environ.update({k: v for k, v in ENV.items() if isinstance(v, str)})
    from server import pdf_filename
    a, u = pdf_filename({"number": "INV-0001", "client_name": "X" * 200})
    assert u == "INV-0001 - " + "X" * 60 + ".pdf" and a == u

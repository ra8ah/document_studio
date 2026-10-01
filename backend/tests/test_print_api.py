"""API checks for the client-side printing change.

Credentials come from the environment / backend/.env (never hard-coded here).
Creates one throw-away document, deletes it, and restores the numbering counters.
"""
import base64
import os
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]


def _env():
    vals = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return {**vals, **os.environ}


ENV = _env()
BASE = ENV.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def ctx():
    db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    counters = list(db.counters.find())
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]})
    assert r.status_code == 200
    profile = s.get(f"{BASE}/api/profile").json()
    d = s.post(f"{BASE}/api/documents", json={"type": "invoice"}).json()
    yield s, d
    s.delete(f"{BASE}/api/documents/{d['id']}")
    s.put(f"{BASE}/api/profile", json={"logo_url": profile.get("logo_url", "")})
    db.counters.delete_many({})
    if counters:
        db.counters.insert_many(counters)


def test_server_pdf_routes_removed(ctx):
    s, d = ctx
    assert s.get(f"{BASE}/api/documents/{d['id']}/pdf").status_code == 404
    tok = s.post(f"{BASE}/api/documents/{d['id']}/share").json()["token"]
    assert s.get(f"{BASE}/api/share/{tok}/pdf").status_code == 404
    assert s.get(f"{BASE}/api/share/{tok}").status_code == 200


def test_docx_still_works(ctx):
    s, d = ctx
    r = s.get(f"{BASE}/api/documents/{d['id']}/docx")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_page_size_default_and_persist(ctx):
    s, d = ctx
    assert d.get("page_size") == "A4"
    r = s.put(f"{BASE}/api/documents/{d['id']}", json={"page_size": "Letter"})
    assert r.status_code == 200 and r.json()["page_size"] == "Letter"
    assert s.put(f"{BASE}/api/documents/{d['id']}", json={"page_size": "B5"}).status_code == 422


@pytest.mark.parametrize("value,code", [
    ("https://example.com/logo.png", 400),
    ("data:image/gif;base64,R0lGODlh", 400),
    ("data:image/svg+xml;base64," + base64.b64encode(b"<svg><script>x()</script></svg>").decode(), 400),
    ("data:image/svg+xml;base64," + base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode(), 200),
    ("data:image/png;base64,iVBORw0KGgo=", 200),
    ("", 200),
])
def test_logo_validation(ctx, value, code):
    s, _ = ctx
    assert s.put(f"{BASE}/api/profile", json={"logo_url": value}).status_code == code

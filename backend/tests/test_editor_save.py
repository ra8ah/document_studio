"""Editor save semantics: merge (not replace), optimistic concurrency, reset endpoint, per-currency dashboard.
Credentials from env / backend/.env. Cleans up and restores counters. Run: pytest -n 0 tests/test_editor_save.py"""
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
LOGO = "data:image/png;base64,iVBORw0KGgo="


@pytest.fixture(scope="module")
def s():
    db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    counters = list(db.counters.find())
    sess = requests.Session()
    assert sess.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}).status_code == 200
    sess.made = []
    yield sess
    for kind, i in sess.made:
        sess.delete(f"{BASE}/api/{kind}/{i}")
    db.counters.delete_many({})
    if counters:
        db.counters.insert_many(counters)


def mk(s, **kw):
    d = s.post(f"{BASE}/api/documents", json={"type": "invoice", **kw}).json()
    s.made.append(("documents", d["id"]))
    return d


def test_save_preserves_non_edited_fields(s):
    d = mk(s)
    s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"logo_url": LOGO}})
    r = s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"bill_to_name": "Acme"}, "line_items": []})
    data = r.json()["data"]
    assert data["bill_to_name"] == "Acme"
    for k in ("label", "reference_label", "logo_url", "from_name", "payment_terms"):
        assert k in data, k
    assert data["label"] == "Invoice" and data["logo_url"] == LOGO


def test_number_cannot_diverge(s):
    d = mk(s)
    r = s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"number": "HACKED-1"}}).json()
    assert r["number"] == d["number"] == r["data"]["number"]


def test_bad_data_keys_rejected(s):
    d = mk(s)
    for bad in ("$where", "a.b", ""):
        assert s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {bad: 1}}).status_code == 422


def test_concurrent_save_returns_409(s):
    d = mk(s)
    loaded = d["updated_at"]
    tab_a = s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"note": "A"}, "expected_updated_at": loaded})
    assert tab_a.status_code == 200
    tab_b = s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"note": "B (stale)"}, "expected_updated_at": loaded})
    assert tab_b.status_code == 409
    assert tab_b.json()["detail"]["server_updated_at"] == tab_a.json()["updated_at"]
    assert s.get(f"{BASE}/api/documents/{d['id']}").json()["data"]["note"] == "A"
    forced = s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"note": "B"}, "expected_updated_at": loaded, "force": True})
    assert forced.status_code == 200 and forced.json()["data"]["note"] == "B"
    # chaining with the returned updated_at keeps working
    nxt = s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"note": "C"}, "expected_updated_at": forced.json()["updated_at"]})
    assert nxt.status_code == 200


@pytest.mark.parametrize("mode", ["defaults", "blank"])
def test_reset_keeps_identity(s, mode):
    c = s.post(f"{BASE}/api/clients", json={"name": "TEST_Reset Client"}).json()
    s.made.append(("clients", c["id"]))
    d = mk(s, client_id=c["id"])
    s.post(f"{BASE}/api/documents/{d['id']}/status", json={"status": "sent"})
    s.put(f"{BASE}/api/documents/{d['id']}", json={
        "data": {"bill_to_name": "Changed", "billing_note": "custom"},
        "line_items": [{"description": "x", "qty": 9, "rate": 9}],
        "discount": {"enabled": True, "mode": "fixed", "value": 5}})
    r = s.post(f"{BASE}/api/documents/{d['id']}/reset", json={"mode": mode})
    assert r.status_code == 200
    out = r.json()
    for k in ("id", "type", "number", "client_id"):
        assert out[k] == d[k], k
    assert out["status"] == "sent" and out["data"]["number"] == d["number"]
    assert out["discount"]["enabled"] is False
    if mode == "blank":
        assert out["line_items"] == [] and out["data"]["bill_to_name"] == "" and out["data"]["label"] == "Invoice"
    else:
        assert out["data"]["bill_to_name"] == "TEST_Reset Client" and len(out["line_items"]) >= 1


def test_reset_validation(s):
    d = mk(s)
    assert s.post(f"{BASE}/api/documents/{d['id']}/reset", json={"mode": "nuke"}).status_code == 422
    for bad in ("not-an-id", "65a0000000000000000000ff"):
        assert s.post(f"{BASE}/api/documents/{bad}/reset", json={"mode": "blank"}).status_code == 404
        assert s.put(f"{BASE}/api/documents/{bad}", json={"data": {"note": "x"}}).status_code == 404


def test_dashboard_groups_currencies(s):
    a = mk(s, currency="USD")
    s.put(f"{BASE}/api/documents/{a['id']}", json={"line_items": [{"description": "u", "qty": 1, "rate": 100}]})
    b = mk(s, currency="EUR")
    s.put(f"{BASE}/api/documents/{b['id']}", json={"line_items": [{"description": "e", "qty": 1, "rate": 50}]})
    d = s.get(f"{BASE}/api/dashboard").json()
    by = d["outstanding_by_currency"]
    assert by.get("USD", 0) >= 100 and by.get("EUR", 0) >= 50
    assert d["outstanding"] == by.get(d["currency"], 0.0)  # headline never mixes currencies

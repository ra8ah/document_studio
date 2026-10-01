"""Overdue transitions, soft delete / restore / purge, client delete blocking + archive, bulk, search.
Run with REACT_APP_BACKEND_URL exported (see /app/memory/HANDOFF.md)."""
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient
from bson import ObjectId

ENV = {**dotenv_values(Path(__file__).resolve().parent.parent / ".env"), **os.environ}
BASE = ENV.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
PAST = (date.today() - timedelta(days=3)).isoformat()
FUTURE = (date.today() + timedelta(days=10)).isoformat()


@pytest.fixture(scope="module")
def ctx():
    db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    counters = list(db.counters.find())
    s = requests.Session()
    assert s.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}).ok
    made, clients = [], []
    yield s, db, made, clients
    for i in made:
        db.documents.delete_one({"_id": ObjectId(i)})
        db.activity.delete_many({"doc_id": i})
    for c in clients:
        db.clients.delete_one({"_id": ObjectId(c)})
    db.counters.delete_many({})
    if counters:
        db.counters.insert_many(counters)


def new_doc(s, made, dtype="invoice", **body):
    d = s.post(f"{BASE}/api/documents", json={"type": dtype, **body}).json()
    made.append(d["id"])
    return d


def get(s, i):
    return s.get(f"{BASE}/api/documents/{i}").json()


def test_overdue_transitions_and_moved_due_date(ctx):
    s, db, made, _ = ctx
    d = new_doc(s, made)
    s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"due_date": PAST}})
    s.post(f"{BASE}/api/documents/{d['id']}/status", json={"status": "sent"})
    assert get(s, d["id"])["status"] == "overdue"
    assert get(s, d["id"])["status"] == "overdue"  # idempotent
    acts = s.get(f"{BASE}/api/documents/{d['id']}/activity").json()
    assert sum(1 for a in acts if a["action"] == "status_changed" and a["detail"].get("to") == "overdue") == 1
    assert any(a["by"] == "system" for a in acts)
    # due date moved to the future -> back to sent (on the save response itself)
    r = s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"due_date": FUTURE}})
    assert get(s, d["id"])["status"] == "sent"
    assert r.status_code == 200


def test_viewed_becomes_overdue_but_draft_and_paid_never(ctx):
    s, db, made, _ = ctx
    v, dr, pd = new_doc(s, made), new_doc(s, made), new_doc(s, made)
    for x, st in ((v, "viewed"), (dr, "draft"), (pd, "paid")):
        s.put(f"{BASE}/api/documents/{x['id']}", json={"data": {"due_date": PAST}})
        s.post(f"{BASE}/api/documents/{x['id']}/status", json={"status": st})
    s.get(f"{BASE}/api/documents")
    assert get(s, v["id"])["status"] == "overdue"
    assert get(s, dr["id"])["status"] == "draft"
    assert get(s, pd["id"])["status"] == "paid"


def test_overdue_only_for_invoices(ctx):
    s, db, made, _ = ctx
    q = new_doc(s, made, "quotation")
    s.put(f"{BASE}/api/documents/{q['id']}", json={"data": {"due_date": PAST}})
    s.post(f"{BASE}/api/documents/{q['id']}/status", json={"status": "sent"})
    assert get(s, q["id"])["status"] == "sent"


def test_soft_delete_restore(ctx):
    s, db, made, _ = ctx
    d = new_doc(s, made, title="TEST_TRASH_REF")
    assert s.delete(f"{BASE}/api/documents/{d['id']}").ok
    assert s.get(f"{BASE}/api/documents/{d['id']}").status_code == 404
    assert d["id"] not in [x["id"] for x in s.get(f"{BASE}/api/documents", params={"page_size": 100}).json()["items"]]
    assert d["number"] not in s.get(f"{BASE}/api/export/documents.csv").text
    assert d["id"] not in [x["id"] for x in s.get(f"{BASE}/api/search", params={"q": "TEST_TRASH_REF"}).json()["documents"]]
    assert s.get(f"{BASE}/api/documents/{d['id']}/pdf").status_code == 404
    assert s.put(f"{BASE}/api/documents/{d['id']}", json={"data": {"x": "1"}}).status_code == 404
    trash = s.get(f"{BASE}/api/trash").json()
    row = next(x for x in trash if x["id"] == d["id"])
    assert row["days_left"] in (29, 30)
    r = s.post(f"{BASE}/api/documents/{d['id']}/restore")
    assert r.status_code == 200
    assert get(s, d["id"])["number"] == d["number"]
    assert s.post(f"{BASE}/api/documents/{d['id']}/restore").status_code == 404


def test_trashed_excluded_from_dashboard_totals(ctx):
    s, db, made, _ = ctx
    d = new_doc(s, made, currency="CHF")
    s.put(f"{BASE}/api/documents/{d['id']}", json={"line_items": [{"description": "x", "qty": 1, "rate": 777}]})
    s.post(f"{BASE}/api/documents/{d['id']}/status", json={"status": "sent"})
    assert s.get(f"{BASE}/api/dashboard").json()["outstanding_by_currency"].get("CHF", 0) >= 777
    before = s.get(f"{BASE}/api/dashboard").json()["outstanding_by_currency"].get("CHF", 0)
    s.delete(f"{BASE}/api/documents/{d['id']}")
    after = s.get(f"{BASE}/api/dashboard").json()["outstanding_by_currency"].get("CHF", 0)
    assert round(before - after, 2) == 777


def test_permanent_delete_only_from_trash(ctx):
    s, db, made, _ = ctx
    d = new_doc(s, made)
    assert s.delete(f"{BASE}/api/documents/{d['id']}/permanent").status_code == 404
    s.delete(f"{BASE}/api/documents/{d['id']}")
    assert s.delete(f"{BASE}/api/documents/{d['id']}/permanent").ok
    assert db.documents.find_one({"_id": ObjectId(d["id"])}) is None


def test_purge_older_than_30_days(ctx):
    s, db, made, _ = ctx
    old, recent = new_doc(s, made), new_doc(s, made)
    s.delete(f"{BASE}/api/documents/{old['id']}")
    s.delete(f"{BASE}/api/documents/{recent['id']}")
    db.documents.update_one({"_id": ObjectId(old["id"])},
                            {"$set": {"deleted_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()}})
    ids = [x["id"] for x in s.get(f"{BASE}/api/trash").json()]  # listing purges
    assert old["id"] not in ids and recent["id"] in ids
    assert db.documents.find_one({"_id": ObjectId(old["id"])}) is None


def test_cron_endpoint_requires_secret():
    assert requests.post(f"{BASE}/api/cron/maintenance", json={}).status_code == 401
    assert requests.post(f"{BASE}/api/cron/maintenance", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_client_delete_blocked_and_archive(ctx):
    s, db, made, clients = ctx
    c = s.post(f"{BASE}/api/clients", json={"name": "TEST_ArchiveCo"}).json()
    clients.append(c["id"])
    d = new_doc(s, made, client_id=c["id"])
    r = s.delete(f"{BASE}/api/clients/{c['id']}")
    assert r.status_code == 409 and r.json()["detail"]["document_count"] == 1
    # trashed documents still block (they can be restored)
    s.delete(f"{BASE}/api/documents/{d['id']}")
    r = s.delete(f"{BASE}/api/clients/{c['id']}")
    assert r.status_code == 409 and r.json()["detail"]["trashed_count"] == 1
    s.post(f"{BASE}/api/documents/{d['id']}/restore")
    assert s.post(f"{BASE}/api/clients/{c['id']}/archive").json()["archived"] is True
    names = lambda **p: [x["name"] for x in s.get(f"{BASE}/api/clients", params={"page_size": 100, **p}).json()["items"]]  # noqa: E731
    assert "TEST_ArchiveCo" not in names()
    assert "TEST_ArchiveCo" in names(archived="only")
    assert "TEST_ArchiveCo" not in [x["name"] for x in s.get(f"{BASE}/api/search", params={"q": "TEST_ArchiveCo"}).json()["clients"]]
    assert get(s, d["id"])["client_name"] == "TEST_ArchiveCo"  # kept on existing documents
    assert s.post(f"{BASE}/api/clients/{c['id']}/archive", json={"archived": False}).json()["archived"] is False
    assert "TEST_ArchiveCo" in names()
    c2 = s.post(f"{BASE}/api/clients", json={"name": "TEST_EmptyCo"}).json()
    clients.append(c2["id"])
    assert s.delete(f"{BASE}/api/clients/{c2['id']}").ok


def test_bulk_status_trash_and_csv(ctx):
    s, db, made, _ = ctx
    a, b = new_doc(s, made), new_doc(s, made)
    r = s.post(f"{BASE}/api/documents/bulk", json={"ids": [a["id"], b["id"]], "action": "status", "status": "cancelled"})
    assert r.json()["updated"] == 2
    assert get(s, a["id"])["status"] == get(s, b["id"])["status"] == "cancelled"
    assert s.post(f"{BASE}/api/documents/bulk", json={"ids": [a["id"]], "action": "status", "status": "bogus"}).status_code == 422
    csv = s.get(f"{BASE}/api/export/documents.csv", params={"ids": f"{a['id']},{b['id']}"}).text.strip().splitlines()
    assert len(csv) == 3 and a["number"] in csv[1] + csv[2]
    assert s.post(f"{BASE}/api/documents/bulk", json={"ids": [a["id"], b["id"]], "action": "trash"}).json()["updated"] == 2
    assert s.get(f"{BASE}/api/documents/{a['id']}").status_code == 404
    assert s.post(f"{BASE}/api/trash/restore", json={"ids": [a["id"], b["id"]], "action": "restore"}).json()["updated"] == 2


def test_search_documents_and_clients(ctx):
    s, db, made, clients = ctx
    c = s.post(f"{BASE}/api/clients", json={"name": "TEST_SearchCo Zeta"}).json()
    clients.append(c["id"])
    d = new_doc(s, made, client_id=c["id"], title="TEST_REF_QUASAR")
    r = s.get(f"{BASE}/api/search", params={"q": "quasar"}).json()
    assert d["id"] in [x["id"] for x in r["documents"]]
    r = s.get(f"{BASE}/api/search", params={"q": d["number"]}).json()
    assert r["documents"][0]["id"] == d["id"]
    r = s.get(f"{BASE}/api/search", params={"q": "searchco zeta"}).json()
    assert c["id"] in [x["id"] for x in r["clients"]] and d["id"] in [x["id"] for x in r["documents"]]
    assert len(s.get(f"{BASE}/api/search", params={"q": "e"}).json()["documents"]) <= 8
    assert s.get(f"{BASE}/api/search", params={"q": ""}).json() == {"documents": [], "clients": []}

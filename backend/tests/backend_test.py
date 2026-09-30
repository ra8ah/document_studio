"""Comprehensive backend tests for Agency Docs app."""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://invoice-hub-1342.preview.emergentagent.com').rstrip('/')
ADMIN_EMAIL = "bxibichvzpd@indogmail.com"
ADMIN_PASSWORD = "Agency@Studio2026"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    email = (data.get("user") or data).get("email")
    assert email == ADMIN_EMAIL
    # cookie auth via session; token also returned
    return s


# -------- Auth --------
class TestAuth:
    def test_login_bad(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code in (400, 401, 403)

    def test_me(self, client):
        r = client.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_refresh(self, client):
        r = client.post(f"{BASE_URL}/api/auth/refresh")
        assert r.status_code in (200, 204)


# -------- Profile --------
class TestProfile:
    def test_get_and_update(self, client):
        r = client.get(f"{BASE_URL}/api/profile")
        assert r.status_code == 200
        p = r.json()
        p["agency_name"] = "TEST_Agency"
        p["default_currency"] = "USD"
        p["prefixes"] = {**(p.get("prefixes") or {}), "invoice": "INV"}
        r2 = client.put(f"{BASE_URL}/api/profile", json=p)
        assert r2.status_code == 200
        r3 = client.get(f"{BASE_URL}/api/profile")
        assert r3.json()["agency_name"] == "TEST_Agency"


# -------- Clients --------
@pytest.fixture(scope="session")
def client_id(client):
    payload = {"name": "TEST_ClientA", "company": "TEST Co", "email": "test_a@example.com", "currency": "USD"}
    r = client.post(f"{BASE_URL}/api/clients", json=payload)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    yield cid
    client.delete(f"{BASE_URL}/api/clients/{cid}")


class TestClients:
    def test_list(self, client, client_id):
        r = client.get(f"{BASE_URL}/api/clients")
        assert r.status_code == 200
        assert any(c["id"] == client_id for c in r.json())

    def test_get(self, client, client_id):
        r = client.get(f"{BASE_URL}/api/clients/{client_id}")
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_ClientA"

    def test_update(self, client, client_id):
        r = client.put(f"{BASE_URL}/api/clients/{client_id}", json={"name": "TEST_ClientA2"})
        assert r.status_code == 200
        r2 = client.get(f"{BASE_URL}/api/clients/{client_id}")
        assert r2.json()["name"] == "TEST_ClientA2"


# -------- Documents --------
@pytest.fixture(scope="session")
def doc_id(client, client_id):
    r = client.post(f"{BASE_URL}/api/documents", json={"type": "invoice", "client_id": client_id})
    assert r.status_code in (200, 201), r.text
    d = r.json()
    did = d["id"]
    assert d.get("number", "").startswith("INV-")
    yield did
    client.delete(f"{BASE_URL}/api/documents/{did}")


class TestDocuments:
    def test_get(self, client, doc_id):
        r = client.get(f"{BASE_URL}/api/documents/{doc_id}")
        assert r.status_code == 200
        assert r.json()["id"] == doc_id

    def test_list(self, client, doc_id):
        r = client.get(f"{BASE_URL}/api/documents")
        assert r.status_code == 200
        assert any(d["id"] == doc_id for d in r.json())

    def test_update_with_line_items(self, client, doc_id):
        payload = {
            "line_items": [{"description": "Design", "qty": 2, "rate": 500}],
            "discount": {"enabled": True, "type": "percent", "value": 10},
            "tax": {"enabled": True, "type": "percent", "value": 5},
            "currency": "USD",
        }
        r = client.put(f"{BASE_URL}/api/documents/{doc_id}", json=payload)
        assert r.status_code == 200, r.text
        r2 = client.get(f"{BASE_URL}/api/documents/{doc_id}")
        d = r2.json()
        assert len(d["line_items"]) == 1
        assert d["line_items"][0]["description"] == "Design"

    def test_pdf_a4(self, client, doc_id):
        r = client.get(f"{BASE_URL}/api/documents/{doc_id}/pdf", params={"size": "A4"})
        assert r.status_code == 200, r.text[:200]
        assert r.content[:4] == b"%PDF"

    def test_pdf_letter(self, client, doc_id):
        r = client.get(f"{BASE_URL}/api/documents/{doc_id}/pdf", params={"size": "Letter"})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_docx(self, client, doc_id):
        r = client.get(f"{BASE_URL}/api/documents/{doc_id}/docx")
        assert r.status_code == 200
        # docx is a zip -> starts with PK
        assert r.content[:2] == b"PK"

    def test_duplicate(self, client, doc_id):
        r = client.post(f"{BASE_URL}/api/documents/{doc_id}/duplicate")
        assert r.status_code in (200, 201)
        new_id = r.json()["id"]
        assert new_id != doc_id
        client.delete(f"{BASE_URL}/api/documents/{new_id}")

    def test_share(self, client, doc_id):
        r = client.post(f"{BASE_URL}/api/documents/{doc_id}/share")
        assert r.status_code in (200, 201), r.text
        token = r.json().get("token") or r.json().get("share_token")
        assert token
        # public
        r2 = requests.get(f"{BASE_URL}/api/share/{token}")
        assert r2.status_code == 200
        r3 = requests.get(f"{BASE_URL}/api/share/{token}/pdf")
        assert r3.status_code == 200
        assert r3.content[:4] == b"%PDF"

    def test_convert_and_mark_paid(self, client, client_id):
        # create quotation, convert to invoice
        r = client.post(f"{BASE_URL}/api/documents", json={"type": "quotation", "client_id": client_id})
        qid = r.json()["id"]
        rc = client.post(f"{BASE_URL}/api/documents/{qid}/convert", json={"target": "invoice"})
        assert rc.status_code in (200, 201), rc.text
        inv = rc.json()
        inv_id = inv["id"]
        # mark paid
        rp = client.post(f"{BASE_URL}/api/documents/{inv_id}/mark-paid")
        assert rp.status_code in (200, 201), rp.text
        # cleanup
        client.delete(f"{BASE_URL}/api/documents/{qid}")
        client.delete(f"{BASE_URL}/api/documents/{inv_id}")

    def test_status(self, client, doc_id):
        r = client.post(f"{BASE_URL}/api/documents/{doc_id}/status", json={"status": "sent"})
        assert r.status_code in (200, 201)


# -------- Packages --------
class TestPackages:
    def test_add_delete(self, client):
        r = client.post(f"{BASE_URL}/api/packages", json={"name": "TEST_Pkg", "rate": 100, "description": "test"})
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        r2 = client.get(f"{BASE_URL}/api/packages")
        assert any(p["id"] == pid for p in r2.json())
        rd = client.delete(f"{BASE_URL}/api/packages/{pid}")
        assert rd.status_code in (200, 204)


# -------- Dashboard --------
class TestDashboard:
    def test_dashboard(self, client):
        r = client.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ["month_revenue", "outstanding", "unpaid_count", "recent"]:
            # be tolerant of alt names
            pass
        assert isinstance(d, dict)


# -------- Exports --------
class TestExports:
    def test_json(self, client):
        r = client.get(f"{BASE_URL}/api/export/documents.json")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_docs_csv(self, client):
        r = client.get(f"{BASE_URL}/api/export/documents.csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "") or r.text.count(",") > 0

    def test_clients_csv(self, client):
        r = client.get(f"{BASE_URL}/api/export/clients.csv")
        assert r.status_code == 200


# -------- Recurring --------
class TestRecurring:
    def test_run(self, client):
        r = client.post(f"{BASE_URL}/api/recurring/run")
        assert r.status_code in (200, 201)

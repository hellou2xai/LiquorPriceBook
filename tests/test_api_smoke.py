"""Smoke tests for the API: health endpoints and static-admin auth."""

from fastapi.testclient import TestClient

from lpb_api.main import app


def test_healthz():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_rejects_bad_credentials():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
    assert r.status_code == 401


def test_login_admin_returns_token():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["username"] == "admin"


def test_me_requires_token():
    c = TestClient(app)
    assert c.get("/api/v1/auth/me").status_code == 401


def test_me_with_token():
    c = TestClient(app)
    token = c.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    ).json()["token"]
    r = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "admin"

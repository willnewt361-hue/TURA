"""Core API smoke tests for TURA V1."""

from __future__ import annotations

import os
import json

# Use a dedicated test DB
os.environ["DATABASE_URL"] = "sqlite:///./data/tura_test.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-32"
os.environ["TICKET_HMAC_SECRET"] = "test-ticket-hmac-secret-32chars!!"
os.environ["DEMO_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from pydantic import ValidationError

# Reset settings cache
from app.config import Settings, get_google_maps_api_key, get_settings

get_settings.cache_clear()

from app.db.session import init_db, SessionLocal, engine
from app.db.models import AuditEvent, Base, Booking, Trip
from app.db.seed import seed_if_empty
from app.main import app
from app.realtime.manager import manager
from app.security.middleware import _content_security_policy
from app.security.signing import hash_password, sign_ticket_payload, verify_password, verify_ticket_token


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    init_db()
    db = SessionLocal()
    seed_if_empty(db)
    db.close()
    with TestClient(app) as c:
        yield c


def _csrf(client: TestClient) -> str:
    r = client.get("/api/auth/csrf")
    assert r.status_code == 200
    return r.json()["csrf"]


def test_public_config_exposes_optional_maps_browser_key(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    assert isinstance(response.json()["google_maps_api_key"], str)
    assert isinstance(response.json()["backup_export_enabled"], bool)


def test_public_demo_cannot_export_database_backups(client, monkeypatch):
    demo_settings = Settings(_env_file=None, demo_mode=True, demo_instance=True)
    monkeypatch.setattr("app.main.get_settings", lambda: demo_settings)
    monkeypatch.setattr("app.api.reports.get_settings", lambda: demo_settings)

    config = client.get("/api/config")
    assert config.status_code == 200
    assert config.json()["backup_export_enabled"] is False

    login = client.post("/api/auth/demo-login", json={"role": "operator"}, headers=_headers(client))
    assert login.status_code == 200
    headers = {"X-CSRF-Token": login.json()["csrf"]}
    assert client.post("/api/reports/backup", headers=headers).status_code == 403
    assert client.get("/api/reports/backup/download").status_code == 403


def test_landing_page_offers_backend_route_search(client):
    page = client.get("/")
    assert page.status_code == 200
    assert 'data-route-search' in page.text
    assert 'data-route-origin' in page.text
    assert 'data-route-destination' in page.text
    assert 'src="/js/api.js"' in page.text
    assert client.get("/js/demo.js").status_code == 200


def test_reference_image_route_serves_only_allowlisted_assets(client):
    image = client.get("/screens/2nd%20page.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/jpeg")
    assert client.get("/screens/.env").status_code == 404


def test_route_map_pages_and_assets_are_served(client):
    for path in (
        "/pages/map-interface.html",
        "/pages/tracking.html",
        "/css/map.css",
        "/js/map.js",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
    page = client.get("/pages/map-interface.html").text
    assert "TURA | Route map" in page
    assert "API_HERE" not in page
    assert "Mengo Senior School" not in page


def test_service_worker_preloads_public_pages_and_supports_offline_navigation(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "`${CACHE_PREFIX}v12`" in response.text
    for path in ("/app/", "/manifest.webmanifest", "/css/tura.css", "/js/store.js", "/js/app.js"):
        assert f"'{path}'" in response.text
        assert client.get(path).status_code == 200
    assert "event.request.mode === 'navigate'" in response.text
    assert "cache.match('/app/')" in response.text


def test_pwa_manifest_has_install_icons_and_app_entry(client):
    manifest_response = client.get("/manifest.webmanifest")
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["start_url"] == "/app/"
    assert manifest["display"] == "standalone"
    icon_sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= icon_sizes
    for icon in manifest["icons"]:
        response = client.get(icon["src"])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/png")
    apple_icon = client.get("/assets/pwa-icon-180.png")
    assert apple_icon.status_code == 200
    assert apple_icon.headers["content-type"].startswith("image/png")
    assert apple_icon.content[16:24] == (180).to_bytes(4, "big") * 2
    app_page = client.get("/app/")
    assert 'rel="apple-touch-icon"' in app_page.text


def test_map_widget_uses_routes_library_instead_of_legacy_directions(client):
    source = client.get("/js/map.js")
    assert source.status_code == 200
    assert "importLibrary('routes')" in source.text
    assert "Route.computeRoutes" in source.text
    assert "DirectionsService" not in source.text
    assert "DirectionsRenderer" not in source.text


def test_maps_csp_sources_are_enabled_only_when_maps_key_is_configured():
    without_maps = _content_security_policy(False)
    with_maps = _content_security_policy(True)
    assert "googleapis.com" not in without_maps
    assert "https://*.googleapis.com" in with_maps
    assert "'unsafe-eval'" in with_maps
    assert "https://*.google.com" in with_maps
    assert "frame-src 'self'" in without_maps
    assert "frame-src 'self' https://*.google.com" in with_maps


def test_local_maps_key_reload_uses_updated_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    env_file.write_text("GOOGLE_MAPS_API_KEY=first-local-key\n", encoding="utf-8")
    assert get_google_maps_api_key(env_file) == "first-local-key"

    env_file.write_text("GOOGLE_MAPS_API_KEY=updated-local-key\n", encoding="utf-8")
    stat = env_file.stat()
    os.utime(env_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert get_google_maps_api_key(env_file) == "updated-local-key"


def test_maps_key_enables_google_sources_in_response_csp(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-browser-key")
    response = client.get("/pages/map-interface.html")
    assert response.status_code == 200
    assert "https://*.googleapis.com" in response.headers["Content-Security-Policy"]


def _headers(client: TestClient) -> dict:
    return {"X-CSRF-Token": _csrf(client)}


def test_ping(client):
    r = client.get("/api/ping")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert set(r.json()) == {"status", "version"}
    assert r.json()["status"] == "ok"


def test_ticket_hmac_roundtrip():
    payload = {
        "ticket_id": 1,
        "ticket_no": "TURA2501010001",
        "trip_id": 2,
        "seat_id": 3,
        "issued_at": "2026-01-01T00:00:00",
        "expires_at": "2099-01-01T00:00:00",
        "version": 1,
    }
    token = sign_ticket_payload(payload)
    ok, body, reason = verify_ticket_token(token)
    assert ok and reason == "ok"
    assert body["ticket_no"] == payload["ticket_no"]
    # Tamper
    bad = token[:-4] + "xxxx"
    ok2, _, reason2 = verify_ticket_token(bad)
    assert not ok2


def test_password_hashing_verifies_correct_password_only():
    encoded = hash_password("TuraPassphrase2026")
    assert encoded.startswith("$2")
    assert verify_password("TuraPassphrase2026", encoded)
    assert not verify_password("wrong password", encoded)
    assert not verify_password("password", "not-a-bcrypt-hash")


def test_search_and_full_booking_flow(client):
    # Demo login customer
    r = client.post("/api/auth/demo-login", json={"role": "customer"}, headers=_headers(client))
    assert r.status_code == 200
    csrf = r.json()["csrf"]
    h = {"X-CSRF-Token": csrf}

    s = client.get("/api/trips/search", params={"origin": "Kampala", "destination": "Gulu"})
    assert s.status_code == 200
    trips = s.json()["trips"]
    assert len(trips) >= 1
    trip = trips[0]

    seats = client.get(f"/api/trips/{trip['id']}/seats")
    avail = [x for x in seats.json()["seats"] if x["status"] == "available"]
    assert avail
    seat = avail[0]

    lock = client.post(
        f"/api/trips/{trip['id']}/seats/lock",
        json={"seat_id": seat["id"]},
        headers=h,
    )
    assert lock.status_code == 200

    booking = client.post(
        "/api/bookings",
        json={
            "trip_id": trip["id"],
            "seat_id": seat["id"],
            "passenger_name": "Mike Okello",
            "passenger_phone": "+256700000001",
            "include_insurance": True,
            "include_luggage": True,
            "idempotency_key": "test-book-1",
        },
        headers=h,
    )
    assert booking.status_code == 200
    bid = booking.json()["booking"]["id"]

    # Idempotent retry
    booking2 = client.post(
        "/api/bookings",
        json={
            "trip_id": trip["id"],
            "seat_id": seat["id"],
            "passenger_name": "Mike Okello",
            "passenger_phone": "+256700000001",
            "idempotency_key": "test-book-1",
        },
        headers=h,
    )
    assert booking2.json()["booking"]["id"] == bid

    pay = client.post(
        "/api/payments/charge",
        json={"booking_id": bid, "method": "mobile_money", "idempotency_key": "test-pay-1"},
        headers=h,
    )
    assert pay.status_code == 200
    assert pay.json()["payment"]["status"] == "success"
    ticket = pay.json()["ticket"]
    assert ticket and ticket["qr_token"]

    # Second customer cannot take same seat
    client.post("/api/auth/logout", headers=h)
    login = client.post("/api/auth/login", json={"phone": "+256700000002", "password": "demo1234"}, headers=_headers(client))
    h2 = {"X-CSRF-Token": login.json()["csrf"]}
    duplicate = client.post(
        "/api/bookings",
        json={
            "trip_id": trip["id"],
            "seat_id": seat["id"],
            "passenger_name": "Mike Okello",
            "passenger_phone": "+256700000001",
            "idempotency_key": "test-book-1",
        },
        headers=h2,
    )
    assert duplicate.status_code == 409

    conflict = client.post(
        f"/api/trips/{trip['id']}/seats/lock",
        json={"seat_id": seat["id"]},
        headers=h2,
    )
    assert conflict.status_code == 409

    # Failed mock charges cancel the pending booking and release its seat.
    remaining = [
        item for item in client.get(f"/api/trips/{trip['id']}/seats").json()["seats"]
        if item["status"] == "available"
    ]
    assert remaining
    failed_seat = remaining[0]
    lock_failed = client.post(
        f"/api/trips/{trip['id']}/seats/lock",
        json={"seat_id": failed_seat["id"]},
        headers=h2,
    )
    assert lock_failed.status_code == 200
    failed_booking = client.post(
        "/api/bookings",
        json={
            "trip_id": trip["id"],
            "seat_id": failed_seat["id"],
            "passenger_name": "Test Passenger",
            "passenger_phone": "+256700000000",
            "idempotency_key": "test-failed-booking",
        },
        headers=h2,
    )
    assert failed_booking.status_code == 200
    failed_booking_id = failed_booking.json()["booking"]["id"]
    payment_key_collision = client.post(
        "/api/payments/charge",
        json={"booking_id": failed_booking_id, "method": "mobile_money", "idempotency_key": "test-pay-1"},
        headers=h2,
    )
    assert payment_key_collision.status_code == 409
    failed_payment = client.post(
        "/api/payments/charge",
        json={"booking_id": failed_booking_id, "method": "mobile_money", "idempotency_key": "test-failed-payment"},
        headers=h2,
    )
    assert failed_payment.status_code == 200
    assert failed_payment.json()["payment"]["status"] == "failed"
    assert client.get(f"/api/bookings/{failed_booking_id}").json()["booking"]["status"] == "cancelled"
    assert any(
        item["id"] == failed_seat["id"] and item["status"] == "available"
        for item in client.get(f"/api/trips/{trip['id']}/seats").json()["seats"]
    )

    # Driver validates
    client.post("/api/auth/logout", headers=h2)
    drv = client.post("/api/auth/demo-login", json={"role": "driver"}, headers=_headers(client))
    hd = {"X-CSRF-Token": drv.json()["csrf"]}
    val = client.post(
        "/api/tickets/validate",
        json={"token": ticket["qr_token"]},
        headers=hd,
    )
    assert val.status_code == 200
    assert val.json()["valid"] is True

    # Invalid signature rejected
    bad = client.post(
        "/api/tickets/validate",
        json={"token": ticket["qr_token"][:-8] + "deadbeef"},
        headers=hd,
    )
    assert bad.status_code == 400
    db = SessionLocal()
    assert db.query(AuditEvent).filter(AuditEvent.event_type == "ticket.validation_failed").count() >= 1
    db.close()


def test_sos_is_demo_local(client):
    r = client.post("/api/auth/demo-login", json={"role": "customer"}, headers=_headers(client))
    h = {"X-CSRF-Token": r.json()["csrf"]}
    sos = client.post("/api/sos", json={"reason": "Test medical"}, headers=h)
    assert sos.status_code == 200
    assert "Demo/Local" in sos.json()["notice"]
    assert sos.json()["alert"]["demo_note"] == "Demo/Local alert"


def test_public_health_is_minimal_and_diagnostics_are_protected(client):
    public = client.get("/api/health")
    assert public.status_code == 200
    assert set(public.json()) == {"status", "version"}

    user = client.post("/api/auth/demo-login", json={"role": "customer"}, headers=_headers(client))
    assert user.status_code == 200
    protected = client.get("/api/reports/health")
    assert protected.status_code == 403


def test_websocket_requires_auth_and_rejects_customer_ops_room(client):
    unauthenticated = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with unauthenticated.websocket_connect("/ws"):
            pass

    login = client.post("/api/auth/demo-login", json={"role": "customer"}, headers=_headers(client))
    customer_id = login.json()["user"]["id"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws?rooms=ops&user_id={customer_id}"):
            pass

    db = SessionLocal()
    booked_trip_id = db.query(Booking.trip_id).filter(Booking.user_id == customer_id).first()[0]
    unbooked_trip_id = db.query(Trip.id).filter(Trip.id != booked_trip_id).first()[0]
    db.close()
    with client.websocket_connect(f"/ws?rooms=trip:{booked_trip_id}") as websocket:
        assert json.loads(websocket.receive_text())["event"] == "connected"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws?rooms=trip:{unbooked_trip_id}"):
            pass

    operator = client.post("/api/auth/demo-login", json={"role": "operator"}, headers=_headers(client))
    operator_id = operator.json()["user"]["id"]
    with client.websocket_connect(f"/ws?rooms=ops&user_id={customer_id}") as websocket:
        assert json.loads(websocket.receive_text())["event"] == "connected"
        assert len(manager.user_sockets[operator_id]) == 1
        assert customer_id not in manager.user_sockets


def test_driver_cannot_operate_unassigned_trip(client):
    login = client.post("/api/auth/demo-login", json={"role": "driver"}, headers=_headers(client))
    headers = {"X-CSRF-Token": login.json()["csrf"]}
    driver_id = login.json()["user"]["id"]
    db = SessionLocal()
    trip = db.query(Trip).first()
    original_driver_id = trip.driver_id
    trip.driver_id = None
    db.commit()
    trip_id = trip.id
    assigned_trip_id = (
        db.query(Trip.id)
        .filter(Trip.driver_id == driver_id, Trip.id != trip_id)
        .first()[0]
    )
    db.close()
    try:
        assigned = client.get("/api/operations/my-trips")
        assert assigned.status_code == 200
        assert all(item["driver_id"] != None for item in assigned.json()["trips"])
        assert all(item["id"] != trip_id for item in assigned.json()["trips"])
        advance = client.post(f"/api/trips/{trip_id}/tracking/advance", headers=headers)
        passengers = client.get(f"/api/trips/{trip_id}/passengers")
        tracking = client.get(f"/api/trips/{trip_id}/tracking")
        assert advance.status_code == 403
        assert passengers.status_code == 403
        assert tracking.status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws?rooms=trip:{trip_id}"):
                pass
        with client.websocket_connect(f"/ws?rooms=trip:{assigned_trip_id}") as websocket:
            assert json.loads(websocket.receive_text())["event"] == "connected"
    finally:
        db = SessionLocal()
        db.query(Trip).filter(Trip.id == trip_id).update({"driver_id": original_driver_id})
        db.commit()
        db.close()


def test_production_settings_reject_insecure_values_and_allow_isolated_demo():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            tura_env="production",
            secret_key="change-me-to-a-long-random-string-in-production",
            ticket_hmac_secret="change-me-ticket-signing-secret-32chars",
            session_cookie_secure=True,
            demo_mode=False,
            demo_instance=False,
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            tura_env="production",
            secret_key="V1-secret-key-X8y!A4#zB7$cD2%fG5",
            ticket_hmac_secret="Ticket-HMAC-S9m@K3!nL6#qR2$vT5P8c!",
            session_cookie_secure=True,
            demo_mode=True,
            demo_instance=False,
        )

    settings = Settings(
        _env_file=None,
        tura_env="production",
        secret_key="V1-secret-key-X8y!A4#zB7$cD2%fG5",
        ticket_hmac_secret="Ticket-HMAC-S9m@K3!nL6#qR2$vT5P8c!",
        session_cookie_secure=True,
        demo_mode=True,
        demo_instance=True,
    )
    assert settings.demo_mode and settings.demo_instance


def test_operator_can_publish_bookable_bus_route_and_trip(client):
    login = client.post("/api/auth/demo-login", json={"role": "operator"}, headers=_headers(client))
    headers = {"X-CSRF-Token": login.json()["csrf"]}
    setup = client.get("/api/operations/setup")
    assert setup.status_code == 200
    assert setup.json()["buses"]

    bus = client.post(
        "/api/operations/buses",
        json={"plate": "TEST 900Z", "operator": "Tura Test Coaches", "capacity": 8, "amenities": ["wifi"]},
        headers=headers,
    )
    assert bus.status_code == 201
    route = client.post(
        "/api/operations/routes",
        json={
            "origin": "Testville",
            "destination": "Sampletown",
            "stops": ["Midway"],
            "distance_km": 120,
            "base_fare_ugx": 25000,
            "duration_minutes": 180,
            "image_slug": "default",
        },
        headers=headers,
    )
    assert route.status_code == 201
    trip = client.post(
        "/api/operations/trips",
        json={
            "bus_id": bus.json()["id"],
            "route_id": route.json()["id"],
            "departure": "2099-06-01T08:00:00Z",
            "arrival": "2099-06-01T11:00:00Z",
        },
        headers=headers,
    )
    assert trip.status_code == 201
    assert trip.json()["trip"]["fare_ugx"] == 25000
    results = client.get(
        "/api/trips/search",
        params={"origin": "Testville", "destination": "Sampletown", "date": "2099-06-01"},
    )
    assert any(item["id"] == trip.json()["trip"]["id"] for item in results.json()["trips"])

    overlap = client.post(
        "/api/operations/trips",
        json={
            "bus_id": bus.json()["id"],
            "route_id": route.json()["id"],
            "departure": "2099-06-01T09:00:00Z",
            "arrival": "2099-06-01T12:00:00Z",
        },
        headers=headers,
    )
    assert overlap.status_code == 409

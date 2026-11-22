"""NEXUS local collaboration app static-route checks."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_nexus_workspace_and_assets_are_served():
    page = client.get("/nexus/")
    assert page.status_code == 200
    assert "Using HTML, CSS, JavaScript and Python only" in page.text
    assert "Connect a teammate" in page.text

    for path in (
        "/nexus/app.js",
        "/nexus/styles.css",
        "/nexus/sw.js",
        "/nexus/icon.svg",
    ):
        assert client.get(path).status_code == 200, path


def test_nexus_manifest_has_installable_scope_and_existing_icons():
    response = client.get("/nexus/manifest.webmanifest")
    assert response.status_code == 200
    manifest = json.loads(response.text)
    assert manifest["start_url"] == "/nexus/"
    assert manifest["scope"] == "/nexus/"
    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} >= {"192x192", "512x512"}
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_nexus_service_worker_is_scoped_to_its_shell():
    response = client.get("/nexus/sw.js")
    assert response.status_code == 200
    assert "'/nexus/'" in response.text
    assert "nexus-tura-shell-v1" in response.text
    assert "request.method !== 'GET'" in response.text

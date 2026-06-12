"""GET-only route smoke tests — no conversion required."""

import json

import mireport
from digital_converter_webapp import create_app


class TestHomePage:
    def test_home_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_home_contains_upload_form(self, client):
        resp = client.get("/")
        assert b"<form" in resp.data

    def test_home_contains_file_input(self, client):
        resp = client.get("/")
        assert b'type="file"' in resp.data


class TestConversionsList:
    def test_conversions_list_loads(self, client):
        resp = client.get("/conversions/")
        assert resp.status_code == 200

    def test_unknown_conversion_is_404(self, client):
        resp = client.get("/conversions/does-not-exist")
        assert resp.status_code == 404


class TestLocales:
    def test_locales_json_loads(self, client):
        url = f"/locales/available_{mireport.__version__}.json"
        resp = client.get(url)
        assert resp.status_code == 200

    def test_locales_json_is_list(self, client):
        url = f"/locales/available_{mireport.__version__}.json"
        resp = client.get(url)
        body = json.loads(resp.data)
        assert isinstance(body, list)
        assert len(body) > 0

    def test_locales_json_entries_have_label(self, client):
        url = f"/locales/available_{mireport.__version__}.json"
        resp = client.get(url)
        body = json.loads(resp.data)
        for entry in body:
            assert "label" in entry


class TestBrokenConfig:
    def test_unusable_session_config_yields_broken_app(self):
        # Session backend selection sees test_config: a deployment with no
        # usable SESSION_TYPE must degrade to the 503 brokenApp, not limp on
        app = create_app({"TESTING": True, "DEPLOYMENT": "production"})
        resp = app.test_client().get("/")
        assert resp.status_code == 503


class TestDebugSession:
    def test_not_found_when_debug_off(self, client):
        resp = client.get("/debug_session")
        assert resp.status_code == 404

    def test_available_when_debug_on(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "DEBUG", True)
        resp = client.get("/debug_session")
        assert resp.status_code == 200
        assert resp.is_json


class TestDeploymentHeader:
    def test_response_includes_deployment_header(self, client):
        resp = client.get("/")
        assert "X-Deployment-Datetime" in resp.headers

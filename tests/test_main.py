# POC tests for the Rafay kubeconfig proxy.
#
# The outbound call to Rafay is monkeypatched (httpx.AsyncClient.get) so the
# suite is deterministic and never touches the network. The headline test
# proves a successful proxy call yields a parseable, well-formed Kubernetes
# kubeconfig YAML document.

import os

# Settings require these before app import; set them so tests don't depend
# on a real .env. Use a test-specific log file to avoid clobbering the real one.
os.environ["API_URL"] = "https://rafay.test"
os.environ["API_KEY"] = "test-key"
os.environ["LOG_FILE_NAME"] = "rafay-api-poc-test"

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import app, KUBECONFIG_PATH, settings

client = TestClient(app)

# A representative kubeconfig, shaped like Rafay's real response.
SAMPLE_KUBECONFIG = """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJU
    server: https://n7krp2l.user.kubeapi-proxy.gruve-ctl.paas.dev.rafay-edge.net:443
  name: aifabrik-dev
contexts:
- context:
    cluster: aifabrik-dev
    namespace: default
    user: kg-64aifabrik-46com
  name: aifabrik-dev
current-context: aifabrik-dev
kind: Config
preferences: {}
users:
- name: kg-64aifabrik-46com
"""


class FakeResponse:
    """Minimal stand-in for httpx.Response (only what main.py reads)."""

    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text
        self.content = text.encode()


def _patch_rafay(monkeypatch, *, response=None, exc=None):
    """Patch httpx.AsyncClient.get to return `response` or raise `exc`."""

    async def fake_get(self, url, headers=None):
        if exc is not None:
            raise exc
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


def test_healthz_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_kubeconfig_success_returns_valid_kubeconfig_yaml(monkeypatch):
    """A 200 from Rafay is returned verbatim as a valid kubeconfig YAML."""
    _patch_rafay(monkeypatch, response=FakeResponse(200, SAMPLE_KUBECONFIG))

    r = client.get("/kubeconfig", params={"project": "platform-catalog", "name": "aifabrik-dev"})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/yaml")

    # Body must parse as YAML and satisfy the kubeconfig contract.
    doc = yaml.safe_load(r.text)
    assert doc["apiVersion"] == "v1"
    assert doc["kind"] == "Config"
    assert isinstance(doc["clusters"], list) and doc["clusters"]
    assert isinstance(doc["contexts"], list) and doc["contexts"]
    assert isinstance(doc["users"], list) and doc["users"]
    assert doc["current-context"] == "aifabrik-dev"
    # The named context must reference an existing cluster and user.
    ctx = doc["contexts"][0]["context"]
    cluster_names = {c["name"] for c in doc["clusters"]}
    user_names = {u["name"] for u in doc["users"]}
    assert ctx["cluster"] in cluster_names
    assert ctx["user"] in user_names


def test_kubeconfig_missing_params_returns_422():
    # Both project and name are required query params.
    assert client.get("/kubeconfig").status_code == 422
    assert client.get("/kubeconfig", params={"project": "p"}).status_code == 422


def test_kubeconfig_upstream_error_is_propagated(monkeypatch):
    _patch_rafay(monkeypatch, response=FakeResponse(500, "api key not found"))

    r = client.get("/kubeconfig", params={"project": "p", "name": "c"})

    assert r.status_code == 500
    assert "Rafay returned 500" in r.json()["detail"]


def test_kubeconfig_network_error_returns_502(monkeypatch):
    _patch_rafay(monkeypatch, exc=httpx.ConnectError("boom"))

    r = client.get("/kubeconfig", params={"project": "p", "name": "c"})

    assert r.status_code == 502
    assert "Failed to reach Rafay" in r.json()["detail"]

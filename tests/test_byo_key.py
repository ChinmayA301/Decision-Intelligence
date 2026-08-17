"""Bring-your-own-key handling: provider registry, credential scoping, and the
guarantee that a caller's API key never comes back out in a response.

All tests here are offline — no provider is ever contacted.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import _provider_http_error, app
from src.llm.client import (
    PROVIDERS,
    MissingCredentialError,
    UnknownProviderError,
    build_llm_client,
)

SECRET = "sk-test-secret-value-that-must-never-be-echoed"


class _UpstreamError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(
            # Mimics a real provider auth error, which echoes a masked key.
            f"Incorrect API key provided: {SECRET[:8]}****{SECRET[-4:]}"
        )
        self.status_code = status_code


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_every_provider_has_a_fixed_base_url_or_is_local() -> None:
    """Base URLs must come from the registry. A caller-supplied URL would let an
    attacker redirect the request and harvest the submitted key."""
    for name, spec in PROVIDERS.items():
        assert spec.kind in {"openai_compatible", "anthropic"}
        if name == "ollama":
            assert spec.base_url is None  # resolved from server env, not caller input
        elif spec.kind == "openai_compatible":
            assert spec.base_url and spec.base_url.startswith("https://")


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(UnknownProviderError):
        build_llm_client(provider="not-a-provider", api_key=SECRET)


def test_provider_requiring_key_rejects_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingCredentialError):
        build_llm_client(provider="openai")


def test_caller_key_is_not_persisted_on_app_state(monkeypatch) -> None:
    """A request-scoped client must not write the key onto shared state."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    client = build_llm_client(provider="openai", model="gpt-4o-mini", api_key=SECRET)
    from src import api

    assert client.provider == "openai"
    assert client.model == "gpt-4o-mini"
    assert SECRET not in repr(vars(api.state))


@pytest.mark.parametrize(
    "status,expected",
    [(401, 401), (403, 401), (429, 429), (404, 400), (400, 400), (500, 502), (None, 502)],
)
def test_provider_errors_map_to_clean_statuses(status, expected) -> None:
    exc = _UpstreamError(status) if status is not None else Exception("boom")
    mapped = _provider_http_error(exc, "openai")
    assert isinstance(mapped, HTTPException)
    assert mapped.status_code == expected


def test_provider_error_never_echoes_the_key() -> None:
    """The upstream message embeds a masked key; we must not relay it."""
    mapped = _provider_http_error(_UpstreamError(401), "openai")
    assert SECRET not in mapped.detail
    assert SECRET[:8] not in mapped.detail


def test_providers_endpoint_lists_options_without_key_material(client) -> None:
    payload = client.get("/providers").json()
    ids = {p["id"] for p in payload["providers"]}
    assert {"groq", "anthropic", "openai", "openrouter", "ollama"} <= ids
    assert all("api_key" not in p for p in payload["providers"])


def test_unknown_provider_over_http_does_not_echo_key(client) -> None:
    resp = client.post(
        "/briefs",
        json={"user_input": "Should we enter the European market or focus domestically?"},
        headers={"X-LLM-Provider": "evil-corp", "X-LLM-Api-Key": SECRET},
    )
    assert resp.status_code == 400
    assert SECRET not in resp.text


def test_missing_key_over_http_returns_401(client, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = client.post(
        "/briefs",
        json={"user_input": "Should we enter the European market or focus domestically?"},
        headers={"X-LLM-Provider": "openai"},
    )
    assert resp.status_code == 401
    assert SECRET not in resp.text


def test_health_reports_byo_requirement(client) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "server_model_configured" in body
    assert body["byo_key_required"] is not body["server_model_configured"]

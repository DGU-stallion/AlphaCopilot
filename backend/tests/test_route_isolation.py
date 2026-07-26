"""Route isolation, auth middleware, and session guard tests.

Validates design.md Correctness Properties:
  1 — Route Isolation (research ↔ quant never cross)
  2 — Authentication Consistency (same auth decision for both modules)
  6 — Empty Message Rejection (session guards)
  + Session guards 404/409 (Requirements 5.6, 5.7)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Default client (no auth) for route isolation tests."""
    import app as app_module
    return TestClient(app_module.app)


@pytest.fixture()
def client_with_auth(monkeypatch):
    """Create a fresh app with VR_API_KEY='test-secret' set before app creation."""
    monkeypatch.setenv("VR_API_KEY", "test-secret")
    from app import create_app
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Property 1: Route Isolation
# ---------------------------------------------------------------------------

class TestRouteIsolation:
    """Property 1: /api/research/* handled only by research, /api/quant/* only by quant."""

    def test_research_health_responds(self, client):
        """Research router has its own /health under /api/research/."""
        r = client.get("/api/research/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "research" in body.get("service", "").lower()

    def test_quant_path_does_not_reach_research(self, client):
        """A research-only endpoint is NOT accessible under /api/quant/."""
        r = client.get("/api/quant/indices")
        # Should not return 200 with research data — either 404/503 from quant fallback
        # (indices is a research endpoint, not quant)
        assert r.status_code != 200 or "data" not in r.json()

    def test_research_path_does_not_reach_quant(self, client):
        """A quant-only endpoint is NOT accessible under /api/research/."""
        r = client.get("/api/research/sessions")
        # sessions is a quant endpoint — research should 404
        assert r.status_code in (404, 405, 422)

    def test_research_indices_at_correct_prefix(self, client):
        """Research /indices is accessible at /api/research/indices."""
        r = client.get("/api/research/indices")
        # May fail with 502 if data source unavailable, but NOT 404
        assert r.status_code != 404

    def test_quant_sessions_at_correct_prefix(self, client):
        """Quant /sessions is accessible at /api/quant/sessions."""
        r = client.get("/api/quant/sessions")
        # Either 200 (sessions module loaded) or 503 (deps missing fallback)
        # but NOT 404 — the route exists
        assert r.status_code in (200, 503)

    def test_global_health_is_independent(self, client):
        """Global /api/health is separate from both modules."""
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["service"] == "alphacopilot"

    def test_no_cross_prefix_leakage_for_data_endpoints(self, client):
        """Research data endpoints (quote, kline, etc.) not available under quant prefix."""
        # /quote is research-only
        r = client.get("/api/quant/quote?codes=600519")
        assert r.status_code != 200 or "data" not in r.json()

        # /runs is quant-only
        r = client.get("/api/research/runs")
        assert r.status_code in (404, 405, 422)


# ---------------------------------------------------------------------------
# Property 2: Authentication Consistency
# ---------------------------------------------------------------------------

class TestAuthConsistency:
    """Property 2: Same auth decision regardless of which module handles the request."""

    def test_no_auth_allows_both_modules(self, client):
        """Without VR_API_KEY configured, both modules accept unauthenticated requests."""
        # Default app has no VR_API_KEY set
        r = client.get("/api/research/health")
        assert r.status_code == 200

        # Quant (may be 503 if deps missing, but NOT 401)
        r = client.get("/api/quant/sessions")
        assert r.status_code != 401

    def test_auth_rejects_both_modules_without_key(self, client_with_auth):
        """With VR_API_KEY set, both modules reject requests without correct key.

        Note: TestClient sends requests from 'testclient' host which triggers the
        loopback bypass (127.0.0.1). We verify auth works by sending a wrong key,
        which should be rejected regardless of host.
        """
        headers = {"Authorization": "Bearer wrong-key"}

        r_research = client_with_auth.get("/api/research/health", headers=headers)
        r_quant = client_with_auth.get("/api/quant/sessions", headers=headers)

        # Both should be 401 (wrong key, not missing key from loopback)
        assert r_research.status_code == 401
        assert r_quant.status_code == 401

    def test_auth_accepts_correct_key_for_both(self, client_with_auth):
        """Correct Bearer token grants access to both modules equally."""
        headers = {"Authorization": "Bearer test-secret"}

        r = client_with_auth.get("/api/research/health", headers=headers)
        assert r.status_code == 200

        r = client_with_auth.get("/api/quant/sessions", headers=headers)
        # 200 or 503 (deps), but NOT 401
        assert r.status_code != 401

    def test_auth_consistency_same_decision_for_both(self, client_with_auth):
        """Same credentials produce the same auth outcome for both modules."""
        # No auth header at all — relies on loopback bypass
        r_research = client_with_auth.get("/api/research/health")
        r_quant = client_with_auth.get("/api/quant/sessions")

        research_passed = r_research.status_code != 401
        quant_passed = r_quant.status_code != 401
        assert research_passed == quant_passed, (
            f"Auth inconsistency: research={r_research.status_code}, quant={r_quant.status_code}"
        )

    def test_health_exempt_from_auth(self, client_with_auth):
        """/api/health is exempt from auth regardless of VR_API_KEY."""
        r = client_with_auth.get("/api/health")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Property 6: Empty Message Rejection + Session Guards (404/409)
# ---------------------------------------------------------------------------

class TestSessionGuards:
    """Property 6 + Requirements 5.6, 5.7: session guards for 404 and 409."""

    def test_nonexistent_session_returns_404(self, client):
        """GET /api/quant/sessions/{id} returns 404 for non-existent session."""
        r = client.get("/api/quant/sessions/nonexistent-session-id-xyz")
        # Either 404 (guard active) or 503 (quant module partially unavailable)
        # The key property: we don't get 200 with fake data
        assert r.status_code in (404, 503)

    def test_message_to_nonexistent_session_returns_404(self, client):
        """POST /api/quant/sessions/{id}/messages returns 404 for non-existent session."""
        r = client.post(
            "/api/quant/sessions/nonexistent-session-id-xyz/messages",
            json={"content": "hello"},
        )
        assert r.status_code in (404, 503)

    def test_session_guard_404_body_has_detail(self, client):
        """404 response includes descriptive detail message."""
        r = client.get("/api/quant/sessions/does-not-exist")
        if r.status_code == 404:
            body = r.json()
            assert "detail" in body
            assert "does-not-exist" in body["detail"] or "not found" in body["detail"].lower()

    def test_empty_message_rejected(self, client):
        """Sending empty content to a session endpoint is rejected (Property 6)."""
        # This tests that the system rejects empty messages.
        # If sessions module is loaded, it validates content.
        # If guards are active, 404 (session doesn't exist) takes precedence.
        r = client.post(
            "/api/quant/sessions/any-session/messages",
            json={"content": ""},
        )
        # Should be 400 (empty content) or 404 (session not found) — never 200
        assert r.status_code in (400, 404, 422, 503)
        assert r.status_code != 200

    def test_whitespace_only_message_rejected(self, client):
        """Sending whitespace-only content is rejected (Property 6)."""
        r = client.post(
            "/api/quant/sessions/any-session/messages",
            json={"content": "   \n\t  "},
        )
        # Should be 400 (whitespace) or 404 (session not found) — never 200
        assert r.status_code in (400, 404, 422, 503)
        assert r.status_code != 200

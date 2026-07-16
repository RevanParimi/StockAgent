"""AUD-100c: the SPA catch-all served index.html with HTTP 200 for ANY path,
masking phantom API routes (rl-data.jsx shipped against 5 nonexistent routes
for a month). Unknown API-namespace paths must 404 loudly."""
from fastapi.testclient import TestClient

from services.api.server import app

c = TestClient(app, raise_server_exceptions=False)


def test_unknown_api_paths_404():
    for path in ("/ui/rl/nope", "/ui/nope", "/api/nope", "/scheduler/nope",
                 "/analytics/nope", "/portfolio/nope/nope", "/delivery/nope",
                 "/discovery/nope", "/history/x/y/z/nope", "/ws/nope"):
        r = c.get(path)
        assert r.status_code == 404, f"{path} -> {r.status_code} (should be 404)"
        assert "text/html" not in r.headers.get("content-type", ""), path


def test_root_and_real_files_still_served():
    assert c.get("/").status_code == 200
    assert "text/html" in c.get("/").headers["content-type"]
    assert c.get("/rl-data.jsx").status_code == 200
    assert c.get("/manifest.json").status_code == 200


def test_registered_api_routes_unaffected():
    assert c.get("/health").status_code == 200
    assert c.get("/ui/rl/tickers").status_code == 200  # real route, not catch-all

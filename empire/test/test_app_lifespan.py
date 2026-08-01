from fastapi.testclient import TestClient
from starlette import status

from empire.server.api.app import create_app


def test_get_main_returns_503_before_lifespan_startup(admin_auth_header):
    """A request arriving before the lifespan populates app.state.main should
    get a clean 503, not an AttributeError/500.

    Using a bare TestClient (no `with` block) deliberately skips the lifespan,
    so app.state.main stays None — the pre-startup window get_main guards.
    """
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v2/listeners/", headers=admin_auth_header)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "not initialized" in response.json()["detail"].lower()

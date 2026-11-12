from fastapi.testclient import TestClient

from shortlinks.config import Settings
from shortlinks.main import create_app
from shortlinks.store import MemoryStore


def test_health_reports_env_and_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "env": "test", "version": "abc1234"}


def test_create_follow_and_count(client: TestClient) -> None:
    created = client.post("/links", json={"url": "https://docs.gitlab.com/ci/"})
    assert created.status_code == 201
    body = created.json()
    assert len(body["code"]) == 7
    assert body["short_url"].endswith("/" + body["code"])
    assert body["hits"] == 0

    followed = client.get("/" + body["code"])
    assert followed.status_code == 307
    assert followed.headers["location"] == "https://docs.gitlab.com/ci/"

    stats = client.get("/links/" + body["code"])
    assert stats.status_code == 200
    assert stats.json()["hits"] == 1


def test_rejects_urls_that_are_not_http(client: TestClient) -> None:
    for url in ["javascript:alert(1)", "ftp://example.com/file", "not a url", ""]:
        assert client.post("/links", json={"url": url}).status_code == 422


def test_rejects_very_long_urls(client: TestClient) -> None:
    url = "https://example.com/" + "a" * 2100
    assert client.post("/links", json={"url": url}).status_code == 422


def test_unknown_and_malformed_codes_are_404(client: TestClient) -> None:
    for path in ["/AAAAAAA", "/links/AAAAAAA", "/bad", "/links/bad!code", "/links"]:
        assert client.get(path).status_code == 404, path


def test_gives_up_when_every_code_is_taken(settings: Settings) -> None:
    class FullStore(MemoryStore):
        def add(self, code: str, url: str) -> None:
            return None

    client = TestClient(create_app(settings, FullStore()))
    assert client.post("/links", json={"url": "https://example.com"}).status_code == 503


def test_docs_only_outside_production() -> None:
    staging = TestClient(create_app(Settings("staging", "v", None), MemoryStore()))
    production = TestClient(create_app(Settings("production", "v", None), MemoryStore()))
    assert staging.get("/openapi.json").status_code == 200
    assert production.get("/openapi.json").status_code == 404
    assert production.get("/docs").status_code == 404

"""HTTP API. Runs unchanged under uvicorn on a laptop and in Lambda (via the Lambda Web Adapter)."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

from shortlinks.codes import is_valid_code, new_code
from shortlinks.config import Settings, load_settings
from shortlinks.store import DynamoStore, LinkStore, MemoryStore

MAX_ATTEMPTS = 5


class NewLink(BaseModel):
    url: HttpUrl  # http(s) only, at most 2083 characters


class LinkOut(BaseModel):
    code: str
    url: str
    short_url: str
    hits: int
    created_at: str


def create_app(settings: Settings | None = None, store: LinkStore | None = None) -> FastAPI:
    settings = settings or load_settings()
    if store is None:
        store = DynamoStore(settings.table_name) if settings.table_name else MemoryStore()
    links: LinkStore = store

    # No interactive docs in production: the API surface stays what the routes below define.
    docs = not settings.is_production
    app = FastAPI(
        title="shortlinks",
        version=settings.app_version,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    def get_store() -> LinkStore:
        return links

    StoreDep = Annotated[LinkStore, Depends(get_store)]

    def out(request: Request, code: str, url: str, hits: int, created_at: str) -> LinkOut:
        short_url = str(request.url_for("follow", code=code))
        return LinkOut(code=code, url=url, short_url=short_url, hits=hits, created_at=created_at)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env, "version": settings.app_version}

    @app.post("/links", status_code=status.HTTP_201_CREATED)
    def create_link(body: NewLink, request: Request, store: StoreDep) -> LinkOut:
        for _ in range(MAX_ATTEMPTS):
            link = store.add(new_code(), str(body.url))
            if link is not None:
                return out(request, link.code, link.url, link.hits, link.created_at)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no free code, try again")

    @app.get("/links/{code}")
    def link_stats(code: str, request: Request, store: StoreDep) -> LinkOut:
        link = store.get(code) if is_valid_code(code) else None
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown code")
        return out(request, link.code, link.url, link.hits, link.created_at)

    @app.delete("/links/{code}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_link(code: str, store: StoreDep) -> None:
        if not is_valid_code(code) or not store.delete(code):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown code")

    @app.get("/{code}", name="follow")
    def follow(code: str, store: StoreDep) -> RedirectResponse:
        link = store.hit(code) if is_valid_code(code) else None
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown code")
        return RedirectResponse(link.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return app


app = create_app()

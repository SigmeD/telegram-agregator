"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from api.routers import leads, sources, triggers
from shared.observability.logging import configure_logging


def create_app() -> FastAPI:
    """Build the FastAPI ``app`` used by uvicorn / tests."""

    configure_logging()
    application = FastAPI(
        title="Telegram Lead Aggregator API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    @application.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        """Liveness probe."""

        return {"status": "ok"}

    application.include_router(leads.router)
    application.include_router(sources.router)
    application.include_router(triggers.router)
    return application


app = create_app()


def main() -> None:
    """Console-script entry-point (delegates to uvicorn)."""

    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)  # nosec B104


if __name__ == "__main__":
    main()

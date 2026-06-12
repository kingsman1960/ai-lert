from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.risk import router as risk_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Heilbronn Risk Guide API",
        version="0.1.0",
        description=(
            "A hackathon MVP backend that combines public warnings and river gauge data "
            "into citizen-facing flood awareness guidance for the Heilbronn region."
        ),
    )

    cors_origins = os.getenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in cors_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"message": "Heilbronn Risk Guide API"}

    app.include_router(risk_router)
    return app


app = create_app()

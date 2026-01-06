from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="every-mentor ai api")


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {"message": "ai api is running"}


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}

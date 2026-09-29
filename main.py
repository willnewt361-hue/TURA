"""Convenient local entry point for the TURA FastAPI application."""

import os

import uvicorn

from app.main import app


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))

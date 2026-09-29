"""Convenient local entry point for the TURA FastAPI application."""

import os

import uvicorn

from app.main import app


if __name__ == "__main__":
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    uvicorn.run(app, host=host, port=int(os.environ.get("PORT", "8000")))

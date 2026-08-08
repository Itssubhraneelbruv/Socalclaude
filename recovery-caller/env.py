"""Locate and load .env.local regardless of where you run from.

A bare load_dotenv(".env.local") resolves against the current working directory,
so it silently loads nothing when you start uvicorn from a different folder - and
you then get a confusing "missing key" error instead of "wrong directory". This
walks up the tree from this file instead.
"""

from pathlib import Path

from dotenv import load_dotenv

ENV_FILENAME = ".env.local"


def load_env() -> Path | None:
    """Load the nearest .env.local at or above this file. Returns the path used."""
    for directory in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            load_dotenv(candidate)
            return candidate
    return None

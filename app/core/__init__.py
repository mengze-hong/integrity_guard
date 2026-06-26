"""Headless / library-mode entry points (no FastAPI required)."""

from app.core.check import check_folder, default_gates

__all__ = ["check_folder", "default_gates"]

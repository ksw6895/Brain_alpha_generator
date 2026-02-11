"""Server package for live event bridge."""

try:  # pragma: no cover - optional dependency boundary
    from .app import app, create_app
except ModuleNotFoundError as import_error:  # pragma: no cover
    if import_error.name not in {"fastapi"}:
        raise
    _IMPORT_ERROR = import_error
    app = None  # type: ignore[assignment]

    def create_app(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError(
            "FastAPI server dependencies are missing. Install requirements.txt first."
        ) from _IMPORT_ERROR

__all__ = ["app", "create_app"]

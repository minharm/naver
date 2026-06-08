from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
PROJECTS_DIR = BASE_DIR / "projects"
UPLOAD_IMAGE_DIR = BASE_DIR / "uploads" / "images"
UPLOAD_VIDEO_DIR = BASE_DIR / "uploads" / "videos"
PROCESSED_IMAGE_DIR = OUTPUT_DIR / "processed_images"
ANALYSIS_IMAGE_DIR = OUTPUT_DIR / "analysis_images"

for p in [DATA_DIR, OUTPUT_DIR, PROJECTS_DIR, UPLOAD_IMAGE_DIR, UPLOAD_VIDEO_DIR, PROCESSED_IMAGE_DIR, ANALYSIS_IMAGE_DIR]:
    p.mkdir(parents=True, exist_ok=True)


def to_relative_path(path: str | Path | None) -> str:
    """Return path relative to project root when possible.

    Saved JSON should not contain private absolute paths such as
    D:/.../NAVER/uploads/images/...
    """
    if not path:
        return ""
    p = Path(path)
    try:
        return p.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except Exception:
        return str(path).replace("\\", "/")


def resolve_path(path: str | Path | None) -> Path:
    """Resolve either an absolute path or a project-relative path."""
    if not path:
        return BASE_DIR
    p = Path(path)
    if p.is_absolute():
        return p
    return BASE_DIR / p


def _json_safe(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _json_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_json_safe(v) for v in data]
    if isinstance(data, Path):
        return to_relative_path(data)
    if isinstance(data, str):
        # Normalize known local paths to relative paths where possible.
        try:
            return to_relative_path(Path(data))
        except Exception:
            return data
    return data


def save_json(filename: str, data: Any) -> Path:
    path = DATA_DIR / filename
    path.write_text(json.dumps(_json_safe(data), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_json(filename: str, default: Any = None) -> Any:
    path = DATA_DIR / filename
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_text(filename: str, text: str) -> Path:
    path = OUTPUT_DIR / filename
    path.write_text(text, encoding="utf-8")
    return path


def save_uploaded_file(uploaded_file, folder: Path) -> Path:
    safe_name = uploaded_file.name.replace("/", "_").replace("\\", "_")
    path = folder / safe_name
    path.write_bytes(uploaded_file.getbuffer())
    return path


def copy_file_if_exists(src: str | Path | None, dst_dir: Path) -> str:
    """Copy file into dst_dir and return new relative path. Empty string if not found."""
    if not src:
        return ""
    source_path = resolve_path(src)
    if not source_path.exists() or not source_path.is_file():
        return ""
    dst_dir.mkdir(parents=True, exist_ok=True)
    target = dst_dir / source_path.name
    if source_path.resolve() != target.resolve():
        shutil.copy2(source_path, target)
    return to_relative_path(target)

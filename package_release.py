from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "v0_5_6"
OUT = ROOT / f"blog_writer_ai_{VERSION}_clean_release.zip"

ALLOW_FILES = {
    "app.py",
    "requirements.txt",
    "README.md",
    ".env.example",
    ".gitignore",
    "package_release.py",
    "run_localhost_5173.bat",
    "cleanup_sensitive_files.bat",
    ".streamlit/config.toml",
    ".github/workflows/test.yml",
}

ALLOW_DIRS = {"modules", "tests"}

BLOCK_FILES = {
    "run_naver_uploader.py",
}

BLOCK_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "output",
    "uploads",
    "data",
    "projects",
    ".git",
}

BLOCK_SUFFIXES = {".pyc", ".zip"}


def allowed(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = set(rel.parts)
    if parts & BLOCK_DIRS:
        return False
    if path.name in BLOCK_FILES:
        return False
    if path.suffix.lower() in BLOCK_SUFFIXES:
        return False
    if str(rel).replace("\\", "/") in ALLOW_FILES:
        return True
    if rel.parts and rel.parts[0] in ALLOW_DIRS:
        return True
    return False


def main() -> None:
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for path in ROOT.rglob("*"):
            if path.is_file() and allowed(path):
                z.write(path, path.relative_to(ROOT))
    print(f"Created: {OUT}")
    print(f"Size: {OUT.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .storage import BASE_DIR, PROJECTS_DIR, copy_file_if_exists, resolve_path, to_relative_path


PROJECT_KEYS = [
    "samples",
    "style_profile",
    "business_info",
    "business_research",
    "business_analysis",
    "image_analysis",
    "video_analysis",
    "generated_post",
    "generated_package_zip",
    "generated_package_dir",
]


def safe_project_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        name = datetime.now().strftime("%Y%m%d_%H%M%S_새프로젝트")
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", "_", name)
    return name[:80]


def project_dir(name: str) -> Path:
    return PROJECTS_DIR / safe_project_name(name)


def list_projects() -> list[str]:
    if not PROJECTS_DIR.exists():
        return []
    return sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()], reverse=True)


def _normalize_media_paths(items: list[dict[str, Any]], media_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items or []:
        copied = dict(item)
        saved = copied.get("saved_path")
        if saved:
            new_path = copy_file_if_exists(saved, media_dir)
            if new_path:
                copied["saved_path"] = new_path

        processed = (copied.get("processed_info") or {}).get("processed_image")
        if processed:
            processed_info = dict(copied.get("processed_info") or {})
            new_path = copy_file_if_exists(processed, media_dir)
            if new_path:
                processed_info["processed_image"] = new_path
            src = processed_info.get("source_image")
            if src:
                rel_src = copy_file_if_exists(src, media_dir)
                if rel_src:
                    processed_info["source_image"] = rel_src
            copied["processed_info"] = processed_info
        out.append(copied)
    return out


def save_project_snapshot(name: str, state: dict[str, Any]) -> Path:
    pdir = project_dir(name)
    media_dir = pdir / "media"
    pdir.mkdir(parents=True, exist_ok=True)

    data = {key: state.get(key) for key in PROJECT_KEYS}
    data["image_analysis"] = _normalize_media_paths(data.get("image_analysis") or [], media_dir)
    data["video_analysis"] = _normalize_media_paths(data.get("video_analysis") or [], media_dir)
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    data["project_name"] = pdir.name

    project_file = pdir / "project.json"
    project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return project_file


def load_project_snapshot(name: str) -> dict[str, Any]:
    project_file = project_dir(name) / "project.json"
    if not project_file.exists():
        raise FileNotFoundError(f"프로젝트 파일이 없습니다: {project_file}")
    return json.loads(project_file.read_text(encoding="utf-8"))


def delete_project(name: str) -> None:
    pdir = project_dir(name)
    if pdir.exists():
        shutil.rmtree(pdir)


def rename_project(old_name: str, new_name: str) -> str:
    old_dir = project_dir(old_name)
    new_dir = project_dir(new_name)
    if not old_dir.exists():
        raise FileNotFoundError(f"프로젝트가 없습니다: {old_name}")
    if new_dir.exists():
        raise FileExistsError(f"이미 같은 이름의 프로젝트가 있습니다: {new_name}")
    old_dir.rename(new_dir)
    return new_dir.name


def duplicate_project(name: str, new_name: str | None = None) -> str:
    src = project_dir(name)
    if not src.exists():
        raise FileNotFoundError(f"프로젝트가 없습니다: {name}")
    target_name = safe_project_name(new_name or f"{name}_복사본")
    target = project_dir(target_name)
    counter = 1
    while target.exists():
        target_name = safe_project_name(f"{name}_복사본_{counter}")
        target = project_dir(target_name)
        counter += 1
    shutil.copytree(src, target)
    return target.name

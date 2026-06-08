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
    "user_experience_note",
    "quality_report",
    "current_step",
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


def _copy_to_project(src: str | Path | None, dst_dir: Path) -> str:
    return copy_file_if_exists(src, dst_dir)


def _normalize_media_paths(items: list[dict[str, Any]], media_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items or []:
        copied = dict(item)
        saved = copied.get("saved_path")
        if saved:
            new_path = _copy_to_project(saved, media_dir)
            if new_path:
                copied["saved_path"] = new_path

        # Backward compatibility for older projects that had processed images.
        processed = (copied.get("processed_info") or {}).get("processed_image")
        if processed:
            processed_info = dict(copied.get("processed_info") or {})
            new_path = _copy_to_project(processed, media_dir)
            if new_path:
                processed_info["processed_image"] = new_path
            src = processed_info.get("source_image")
            if src:
                rel_src = _copy_to_project(src, media_dir)
                if rel_src:
                    processed_info["source_image"] = rel_src
            copied["processed_info"] = processed_info
        out.append(copied)
    return out


def _copy_package_outputs(data: dict[str, Any], pdir: Path) -> None:
    package_dir = pdir / "upload_package"
    package_zip_dir = pdir / "package_zip"

    raw_zip = data.get("generated_package_zip")
    if raw_zip:
        copied_zip = _copy_to_project(raw_zip, package_zip_dir)
        if copied_zip:
            data["generated_package_zip"] = copied_zip

    raw_dir = data.get("generated_package_dir")
    if raw_dir:
        source_dir = resolve_path(raw_dir)
        if source_dir.exists() and source_dir.is_dir():
            if package_dir.exists():
                shutil.rmtree(package_dir)
            shutil.copytree(source_dir, package_dir)
            data["generated_package_dir"] = to_relative_path(package_dir)


def _write_project_sidecar_files(data: dict[str, Any], pdir: Path) -> None:
    generated_post = str(data.get("generated_post") or "")
    if generated_post.strip():
        (pdir / "generated_post.txt").write_text(generated_post, encoding="utf-8")

    quality_report = data.get("quality_report")
    if quality_report:
        (pdir / "quality_report.json").write_text(json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")


def build_project_status(data: dict[str, Any]) -> dict[str, Any]:
    images = data.get("image_analysis") or []
    videos = data.get("video_analysis") or []
    package_zip = data.get("generated_package_zip")
    package_dir = data.get("generated_package_dir")

    return {
        "has_style_profile": bool(data.get("style_profile")),
        "has_business_analysis": bool(data.get("business_analysis")),
        "has_media_analysis": bool(images or videos),
        "has_generated_post": bool(str(data.get("generated_post") or "").strip()),
        "has_quality_report": bool(data.get("quality_report")),
        "image_count": len(images),
        "video_count": len(videos),
        "has_upload_package_zip": bool(package_zip and resolve_path(package_zip).exists()),
        "has_upload_package_dir": bool(package_dir and resolve_path(package_dir).exists()),
        "last_step": data.get("current_step") or "",
    }


def validate_project_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    missing_media: list[str] = []
    for item in data.get("image_analysis") or []:
        raw = item.get("saved_path")
        if raw and not resolve_path(raw).exists():
            missing_media.append(str(raw))
    for item in data.get("video_analysis") or []:
        raw = item.get("saved_path")
        if raw and not resolve_path(raw).exists():
            missing_media.append(str(raw))

    package_zip = data.get("generated_package_zip")
    package_dir = data.get("generated_package_dir")

    return {
        "status": build_project_status(data),
        "missing_media": missing_media,
        "missing_media_count": len(missing_media),
        "package_zip_exists": bool(package_zip and resolve_path(package_zip).exists()),
        "package_dir_exists": bool(package_dir and resolve_path(package_dir).exists()),
    }


def save_project_snapshot(name: str, state: dict[str, Any]) -> Path:
    pdir = project_dir(name)
    media_dir = pdir / "media"
    pdir.mkdir(parents=True, exist_ok=True)

    data = {key: state.get(key) for key in PROJECT_KEYS}
    data["image_analysis"] = _normalize_media_paths(data.get("image_analysis") or [], media_dir)
    data["video_analysis"] = _normalize_media_paths(data.get("video_analysis") or [], media_dir)
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    data["project_name"] = pdir.name

    _copy_package_outputs(data, pdir)
    _write_project_sidecar_files(data, pdir)

    data["project_status"] = build_project_status(data)
    data["project_health"] = validate_project_snapshot(data)

    project_file = pdir / "project.json"
    project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (pdir / "project_manifest.json").write_text(
        json.dumps(
            {
                "project_name": pdir.name,
                "saved_at": data["saved_at"],
                "status": data["project_status"],
                "health": data["project_health"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return project_file


def load_project_snapshot(name: str) -> dict[str, Any]:
    pdir = project_dir(name)
    project_file = pdir / "project.json"
    if not project_file.exists():
        raise FileNotFoundError(f"프로젝트 파일이 없습니다: {project_file}")

    data = json.loads(project_file.read_text(encoding="utf-8"))

    post_file = pdir / "generated_post.txt"
    if not data.get("generated_post") and post_file.exists():
        data["generated_post"] = post_file.read_text(encoding="utf-8")

    quality_file = pdir / "quality_report.json"
    if not data.get("quality_report") and quality_file.exists():
        data["quality_report"] = json.loads(quality_file.read_text(encoding="utf-8"))

    data["project_health"] = validate_project_snapshot(data)
    return data


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

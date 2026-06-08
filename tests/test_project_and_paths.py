import json
from pathlib import Path

from modules.storage import BASE_DIR, resolve_path, to_relative_path
from modules.project_manager import load_project_snapshot, save_project_snapshot, delete_project


def test_relative_path_roundtrip(tmp_path):
    # Use a file under the project root so to_relative_path should strip the absolute part.
    target = BASE_DIR / "uploads" / "images" / "unit_test_image.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("dummy", encoding="utf-8")

    rel = to_relative_path(target)
    assert not Path(rel).is_absolute()
    assert resolve_path(rel).exists()

    target.unlink()


def test_project_save_load_copies_media_and_uses_relative_path(tmp_path):
    source = BASE_DIR / "uploads" / "images" / "project_test_image.jpg"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"fake image")

    project_name = "unit_test_project"
    state = {
        "style_profile": {"tone": "test"},
        "image_analysis": [{"saved_path": str(source), "analysis": {"blog_caption": "caption"}}],
        "video_analysis": [],
    }
    try:
        project_file = save_project_snapshot(project_name, state)
        data = load_project_snapshot(project_name)
        saved_path = data["image_analysis"][0]["saved_path"]
        assert not Path(saved_path).is_absolute()
        assert resolve_path(saved_path).exists()
        assert project_file.exists()
    finally:
        delete_project(project_name)
        if source.exists():
            source.unlink()

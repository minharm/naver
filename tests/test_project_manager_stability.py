from pathlib import Path

from modules.project_manager import (
    delete_project,
    load_project_snapshot,
    save_project_snapshot,
    validate_project_snapshot,
)
from modules.storage import BASE_DIR, OUTPUT_DIR, resolve_path, to_relative_path


def test_project_save_load_preserves_media_quality_and_package(tmp_path):
    image = BASE_DIR / "uploads" / "images" / "project_stable_image.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"fake image")

    package_dir = OUTPUT_DIR / "unit_upload_package"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "upload_guide.txt").write_text("guide", encoding="utf-8")

    package_zip = OUTPUT_DIR / "unit_upload_package.zip"
    package_zip.write_bytes(b"fake zip")

    project_name = "unit_project_stable"
    state = {
        "style_profile": {"tone": "test"},
        "business_info": {"업체명": "테스트"},
        "business_analysis": {"summary": "ok"},
        "image_analysis": [{"filename": image.name, "saved_path": to_relative_path(image), "analysis": {"image_type": "외관"}}],
        "video_analysis": [],
        "generated_post": "생성글 본문",
        "quality_report": {"scores": {"overall": 88}},
        "generated_package_zip": to_relative_path(package_zip),
        "generated_package_dir": to_relative_path(package_dir),
        "user_experience_note": "",
        "current_step": "STEP 4. 블로그 글 생성",
    }

    try:
        project_file = save_project_snapshot(project_name, state)
        assert project_file.exists()
        loaded = load_project_snapshot(project_name)

        assert loaded["generated_post"] == "생성글 본문"
        assert loaded["quality_report"]["scores"]["overall"] == 88
        assert loaded["image_analysis"]
        assert resolve_path(loaded["image_analysis"][0]["saved_path"]).exists()
        assert resolve_path(loaded["generated_package_zip"]).exists()
        assert resolve_path(loaded["generated_package_dir"]).exists()

        health = validate_project_snapshot(loaded)
        assert health["missing_media_count"] == 0
        assert health["status"]["has_quality_report"] is True
        assert health["status"]["has_generated_post"] is True
        assert health["status"]["has_upload_package_zip"] is True
    finally:
        delete_project(project_name)
        if image.exists():
            image.unlink()
        if package_zip.exists():
            package_zip.unlink()
        if package_dir.exists():
            import shutil
            shutil.rmtree(package_dir)


def test_project_validate_reports_missing_media():
    data = {"image_analysis": [{"saved_path": "uploads/images/not_exists.jpg"}], "video_analysis": []}
    health = validate_project_snapshot(data)
    assert health["missing_media_count"] == 1

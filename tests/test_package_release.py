from pathlib import Path

import package_release


def test_package_release_excludes_sensitive_paths():
    assert not package_release.allowed(package_release.ROOT / ".venv" / "x.py")
    assert not package_release.allowed(package_release.ROOT / "output" / "x.json")
    assert not package_release.allowed(package_release.ROOT / "uploads" / "image.jpg")
    assert not package_release.allowed(package_release.ROOT / "data" / "style_profile.json")
    assert not package_release.allowed(package_release.ROOT / "projects" / "abc" / "project.json")
    assert not package_release.allowed(package_release.ROOT / "run_naver_uploader.py")


def test_package_release_includes_ci_and_core_files():
    assert package_release.allowed(package_release.ROOT / "app.py")
    assert package_release.allowed(package_release.ROOT / ".github" / "workflows" / "test.yml")
    assert package_release.allowed(package_release.ROOT / "modules" / "blog_generator.py")

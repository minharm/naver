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


def test_package_release_actual_zip_excludes_sensitive_dirs():
    import zipfile

    package_release.main()
    assert package_release.OUT.exists()
    with zipfile.ZipFile(package_release.OUT) as z:
        names = z.namelist()
    blocked_prefixes = (".venv/", "output/", "uploads/", "data/", "projects/")
    assert not any(name.startswith(blocked_prefixes) for name in names)
    assert not any("__pycache__" in name for name in names)
    assert not any(name.endswith(".pyc") for name in names)
    assert ".github/workflows/test.yml" in names

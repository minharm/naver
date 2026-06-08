from pathlib import Path


def test_app_has_no_token_save_mode_ui():
    text = Path("app.py").read_text(encoding="utf-8")
    assert "토큰 절약 모드" not in text
    assert "TOKEN_SAVE_MODE" not in text
    assert "make_metadata_only_image_analysis" not in text


def test_app_keeps_1024_resize_for_image_analysis():
    text = Path("app.py").read_text(encoding="utf-8")
    assert "resize_for_analysis=True" in text
    assert "max_long_side=1024" in text


def test_blog_generator_no_cost_control_import():
    text = Path("modules/blog_generator.py").read_text(encoding="utf-8")
    assert "cost_control" not in text
    assert "token_save_mode" not in text

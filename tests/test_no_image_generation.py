from pathlib import Path


def test_app_has_no_image_generation_ui():
    text = Path("app.py").read_text(encoding="utf-8")
    assert "이미지 가공 실행" not in text
    assert "이미지 자막/라벨 넣기" not in text
    assert "OPENAI_IMAGE_MODEL" not in text
    assert "process_image_for_blog" not in text


def test_modules_have_no_openai_image_edit_calls():
    llm = Path("modules/llm_client.py").read_text(encoding="utf-8")
    media = Path("modules/media_analyzer.py").read_text(encoding="utf-8")
    assert "client.images.edit" not in llm
    assert "edit_image_with_ai" not in llm
    assert "edit_image_with_ai" not in media
    assert "def process_image_for_blog" not in media
    assert "def plan_image_processing" not in media

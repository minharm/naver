from pathlib import Path

from modules.post_exporter import create_blog_upload_package
from modules.storage import OUTPUT_DIR, resolve_path, to_relative_path


def test_create_blog_upload_package_with_relative_media(tmp_path):
    img = OUTPUT_DIR / "unit_test_source.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"fake jpg")

    try:
        info = create_blog_upload_package(
            title_block="1. 테스트 제목",
            body="본문입니다.\n\n[사진 1 삽입]\n\n마무리입니다.",
            tags="#테스트",
            full_post="전체 글",
            images=[{"saved_path": to_relative_path(img), "analysis": {"blog_caption": "사진 설명"}}],
            videos=[],
            map_query="후이후이 경기 수원시 영통구 덕영대로 1566",
            map_url="https://map.naver.com/",
        )
        zip_path = Path(info["zip_path"])
        package_dir = Path(info["package_dir"])
        assert zip_path.exists()
        assert (package_dir / "media" / "01_image.jpg").exists()
        assert (package_dir / "place_attachment_guide.txt").exists()
    finally:
        if img.exists():
            img.unlink()

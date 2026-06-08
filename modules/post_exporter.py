from __future__ import annotations

import html
import json
import mimetypes
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .storage import OUTPUT_DIR, resolve_path, to_relative_path


PLACEHOLDER_RE = re.compile(r"\[(사진|영상)\s+([0-9,\-\~\s]+)\s*삽입\]")


def select_image_path(item: dict[str, Any]) -> Path | None:
    processed = ((item or {}).get("processed_info") or {}).get("processed_image")
    saved = (item or {}).get("saved_path")
    for raw in [processed, saved]:
        if raw:
            p = resolve_path(raw)
            if p.exists():
                return p
    return None


def select_video_path(item: dict[str, Any]) -> Path | None:
    saved = (item or {}).get("saved_path")
    if saved:
        p = resolve_path(saved)
        if p.exists():
            return p
    return None


def parse_index_spec(spec: str) -> list[int]:
    spec = (spec or "").strip()
    if not spec:
        return []
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    result: list[int] = []
    for part in parts:
        if "-" in part or "~" in part:
            sep = "-" if "-" in part else "~"
            try:
                start_s, end_s = [x.strip() for x in part.split(sep, 1)]
                start_i = int(start_s)
                end_i = int(end_s)
                if start_i <= end_i:
                    result.extend(list(range(start_i, end_i + 1)))
                else:
                    result.extend(list(range(end_i, start_i + 1)))
            except Exception:
                continue
        else:
            try:
                result.append(int(part))
            except Exception:
                continue
    # preserve order, unique
    out: list[int] = []
    seen: set[int] = set()
    for x in result:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def parse_body_segments(body: str) -> list[dict[str, Any]]:
    body = (body or "").strip()
    body = re.sub(r"\n?\s*\[\s*네이버\s*지도\s*첨부\s*\]\s*\n?", "\n\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    segments: list[dict[str, Any]] = []
    cursor = 0
    for match in PLACEHOLDER_RE.finditer(body):
        start, end = match.span()
        media_type = match.group(1)
        spec = match.group(2)
        if start > cursor:
            text_part = body[cursor:start].strip()
            if text_part:
                segments.append({"type": "text", "content": text_part})
        segments.append(
            {
                "type": "photo" if media_type == "사진" else "video",
                "placeholder": match.group(0),
                "indices": parse_index_spec(spec),
            }
        )
        cursor = end
    if cursor < len(body):
        tail = body[cursor:].strip()
        if tail:
            segments.append({"type": "text", "content": tail})
    return segments


def collect_media_usage(body: str) -> dict[str, list[int]]:
    segments = parse_body_segments(body)
    photos: list[int] = []
    videos: list[int] = []
    for seg in segments:
        if seg["type"] == "photo":
            photos.extend(seg["indices"])
        elif seg["type"] == "video":
            videos.extend(seg["indices"])
    # unique preserve order
    def uniq(items: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out
    return {"photos": uniq(photos), "videos": uniq(videos)}


def _copy_media_files(
    images: list[dict[str, Any]],
    videos: list[dict[str, Any]],
    media_dir: Path,
) -> dict[str, dict[int, str]]:
    media_dir.mkdir(parents=True, exist_ok=True)
    image_map: dict[int, str] = {}
    video_map: dict[int, str] = {}

    for idx, item in enumerate(images, start=1):
        src = select_image_path(item)
        if not src:
            continue
        ext = src.suffix.lower() or ".jpg"
        dst_name = f"{idx:02d}_image{ext}"
        shutil.copy2(src, media_dir / dst_name)
        image_map[idx] = dst_name

    for idx, item in enumerate(videos, start=1):
        src = select_video_path(item)
        if not src:
            continue
        ext = src.suffix.lower() or ".mp4"
        dst_name = f"{idx:02d}_video{ext}"
        shutil.copy2(src, media_dir / dst_name)
        video_map[idx] = dst_name

    return {"images": image_map, "videos": video_map}


def build_html_preview(
    title_block: str,
    body: str,
    tags: str,
    image_files: dict[int, str],
    video_files: dict[int, str],
    map_query: str = "",
    map_url: str = "",
) -> str:
    title_lines = [html.escape(x.strip()) for x in title_block.splitlines() if x.strip()]
    segments = parse_body_segments(body)
    body_parts: list[str] = []

    for seg in segments:
        if seg["type"] == "text":
            paragraphs = [p.strip() for p in re.split(r"\n{2,}", seg["content"]) if p.strip()]
            for p in paragraphs:
                safe = html.escape(p).replace("\n", "<br>")
                body_parts.append(f"<p>{safe}</p>")
        elif seg["type"] == "photo":
            body_parts.append('<div class="media-block photo-group">')
            body_parts.append(f'<div class="media-placeholder">{html.escape(seg.get("placeholder", ""))}</div>')
            for idx in seg["indices"]:
                file_name = image_files.get(idx)
                if file_name:
                    body_parts.append(
                        f'<figure><img src="media/{html.escape(file_name)}" alt=""></figure>'
                    )
            body_parts.append("</div>")
        elif seg["type"] == "video":
            body_parts.append('<div class="media-block video-group">')
            body_parts.append(f'<div class="media-placeholder">{html.escape(seg.get("placeholder", ""))}</div>')
            for idx in seg["indices"]:
                file_name = video_files.get(idx)
                if file_name:
                    body_parts.append(
                        f'<figure><video controls preload="metadata" src="media/{html.escape(file_name)}"></video></figure>'
                    )
            body_parts.append("</div>")

    tags_safe = html.escape(tags).replace("\n", "<br>")

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>네이버 블로그 업로드 패키지 미리보기</title>
<style>
body {{
  font-family: Arial, Apple SD Gothic Neo, Malgun Gothic, sans-serif;
  margin: 24px auto;
  max-width: 430px;
  line-height: 1.95;
  color: #222;
}}
h1, h2 {{ color: #222; }}
.title-box, .tag-box, .guide-box {{
  background: #f7f7f7; border: 1px solid #ddd; padding: 16px; border-radius: 10px; margin-bottom: 20px;
}}
.media-block {{ margin: 18px 0; }}
.media-placeholder {{ color: #888; font-size: 14px; margin-bottom: 8px; }}
figure {{ margin: 0 0 18px 0; }}
img, video {{ max-width: 100%; border-radius: 12px; display: block; }}
figcaption {{ color: #666; font-size: 13px; margin-top: 6px; }}
p {{ margin: 0 0 20px 0; font-size: 16px; letter-spacing: -0.2px; }}
</style>
</head>
<body>
<h1>네이버 블로그 업로드 패키지</h1>
<div class="guide-box">
  <strong>사용 방법</strong><br>
  1) media 폴더의 이미지/영상을 번호 순서대로 업로드<br>
  2) 아래 본문 흐름과 동일하게 배치<br>
  3) tags 내용은 마지막에 태그로 사용
</div>
<div class="title-box">
  <h2>제목 후보</h2>
  {"<br>".join(title_lines) if title_lines else "제목 없음"}
</div>
<h2>본문 미리보기</h2>
{''.join(body_parts)}
<div class="tag-box">
  <h2>위치정보</h2>
  {f'<iframe src="{html.escape(map_url)}" style="width:100%;height:380px;border:1px solid #ddd;border-radius:8px;"></iframe>' if map_url else ""}
  <div style="padding-top:10px;">
    <strong>{html.escape(map_query.split()[0]) if map_query else "업체명"}</strong><br>
    <span style="color:#667085;">{html.escape(map_query) if map_query else "장소 검색어 없음"}</span>
  </div>
  <div style="font-size:13px;color:#03c75a;margin-top:8px;">네이버 블로그 발행 시에는 에디터의 장소 버튼으로 실제 지도 카드를 첨부하세요.</div>
</div>
<div class="tag-box">
  <h2>태그</h2>
  {tags_safe}
</div>
</body>
</html>"""


def build_upload_guide(body: str, images: list[dict[str, Any]], videos: list[dict[str, Any]], file_maps: dict[str, dict[int, str]]) -> str:
    usage = collect_media_usage(body)
    lines = [
        "[업로드 가이드]",
        "아래 순서대로 네이버 블로그 편집기에 이미지/영상을 업로드하면 됩니다.",
        "",
        "[이미지 업로드 순서]",
    ]
    if usage["photos"]:
        for idx in usage["photos"]:
            file_name = file_maps["images"].get(idx, "(파일 없음)")
            label = images[idx - 1].get("filename", f"사진 {idx}") if 0 < idx <= len(images) else f"사진 {idx}"
            lines.append(f"- 사진 {idx}: {file_name} (원본: {label})")
    else:
        lines.append("- 본문에 명시된 사진 삽입 지시가 없습니다.")

    lines += ["", "[영상 업로드 순서]"]
    if usage["videos"]:
        for idx in usage["videos"]:
            file_name = file_maps["videos"].get(idx, "(파일 없음)")
            label = videos[idx - 1].get("filename", f"영상 {idx}") if 0 < idx <= len(videos) else f"영상 {idx}"
            lines.append(f"- 영상 {idx}: {file_name} (원본: {label})")
    else:
        lines.append("- 본문에 명시된 영상 삽입 지시가 없습니다.")
    lines += ["", "[장소 첨부]", "- 네이버 블로그 에디터의 장소 버튼을 누르고 업체명/주소로 검색해 글 맨 아래에 실제 지도 카드를 첨부하세요."]
    return "\n".join(lines)


def create_blog_upload_package(
    title_block: str,
    body: str,
    tags: str,
    full_post: str,
    images: list[dict[str, Any]],
    videos: list[dict[str, Any]],
    map_query: str = "",
    map_url: str = "",
) -> dict[str, str]:
    package_dir = OUTPUT_DIR / "blog_upload_package"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    media_dir = package_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    file_maps = _copy_media_files(images, videos, media_dir)
    html_preview = build_html_preview(title_block, body, tags, file_maps["images"], file_maps["videos"], map_query=map_query, map_url=map_url)
    usage = collect_media_usage(body)
    upload_guide = build_upload_guide(body, images, videos, file_maps)

    (package_dir / "blog_post.txt").write_text(full_post, encoding="utf-8")
    (package_dir / "title_candidates.txt").write_text(title_block, encoding="utf-8")
    (package_dir / "body_only.txt").write_text(body, encoding="utf-8")
    (package_dir / "tags.txt").write_text(tags, encoding="utf-8")
    (package_dir / "place_attachment_guide.txt").write_text(
        f"네이버 블로그 에디터 상단의 장소 버튼을 누르고 아래 문구로 검색해 실제 지도 카드를 첨부하세요.\n\n검색어: {map_query}\n미리보기 URL: {map_url}".strip(),
        encoding="utf-8",
    )
    (package_dir / "upload_guide.txt").write_text(upload_guide, encoding="utf-8")
    (package_dir / "blog_post_with_media.html").write_text(html_preview, encoding="utf-8")
    (package_dir / "manifest.json").write_text(
        json.dumps(
            {
                "photo_usage_order": usage["photos"],
                "video_usage_order": usage["videos"],
                "image_files": file_maps["images"],
                "video_files": file_maps["videos"],
                "place_search_query": map_query,
                "map_preview_url": map_url,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    zip_path = OUTPUT_DIR / "blog_upload_package.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in package_dir.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(package_dir.parent))

    return {"package_dir": str(package_dir), "zip_path": str(zip_path)}

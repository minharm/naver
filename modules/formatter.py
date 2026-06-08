from __future__ import annotations

from typing import Any


def build_media_block(images: list[dict[str, Any]], videos: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    if images:
        lines.append("[사진 자료]")
        for idx, item in enumerate(images, start=1):
            name = item.get("filename") or item.get("file_name") or f"사진{idx}"
            desc = item.get("description", "")
            analysis = item.get("analysis") or item
            caption = analysis.get("blog_caption", "") if isinstance(analysis, dict) else ""
            position = analysis.get("recommended_position", "") if isinstance(analysis, dict) else ""
            processed = item.get("processed_info", {}) or {}
            overlay_caption = processed.get("overlay_caption", "")
            lines.append(f"- 사진 {idx}: {name}")
            if desc:
                lines.append(f"  - 사용자 설명: {desc}")
            if caption:
                lines.append(f"  - AI 사진 분석: {caption}")
            if position:
                lines.append(f"  - 추천 위치: {position}")
            if processed.get("processed_image"):
                lines.append(f"  - 가공 이미지 사용 가능: {processed.get('processed_image')}")
            if item.get("is_reference_generated"):
                lines.append("  - 보완 이미지: 업로드에 없던 장면을 공개 자료 참고로 추가 생성")
            if overlay_caption:
                lines.append(f"  - 이미지 자막/라벨: {overlay_caption}")
    if videos:
        lines.append("\n[영상 자료]")
        for idx, item in enumerate(videos, start=1):
            name = item.get("filename") or item.get("file_name") or f"영상{idx}"
            desc = item.get("description", "")
            analysis = item.get("analysis") or item
            summary = analysis.get("video_summary", "") if isinstance(analysis, dict) else ""
            position = analysis.get("recommended_position", "") if isinstance(analysis, dict) else ""
            caption_plan = item.get("caption_plan", {}) or {}
            lines.append(f"- 영상 {idx}: {name}")
            if desc:
                lines.append(f"  - 사용자 설명: {desc}")
            if summary:
                lines.append(f"  - AI 영상 분석: {summary}")
            if position:
                lines.append(f"  - 추천 위치: {position}")
            if caption_plan.get("subtitle_lines"):
                lines.append(f"  - 추천 자막: {' / '.join(caption_plan.get('subtitle_lines', [])[:3])}")
            if caption_plan.get("thumbnail_text"):
                lines.append(f"  - 썸네일 문구: {caption_plan.get('thumbnail_text', '')}")
    return "\n".join(lines).strip()


def format_final_output(title_block: str, body: str, tags: str) -> str:
    return f"""
[제목 후보]
{title_block.strip()}


[네이버 블로그 본문]
{body.strip()}


[태그]
{tags.strip()}
""".strip()


def style_profile_to_markdown(profile: dict[str, Any]) -> str:
    lines = []
    for key, value in profile.items():
        if isinstance(value, list):
            lines.append(f"### {key}")
            for item in value:
                lines.append(f"- {item}")
        else:
            lines.append(f"### {key}\n{value}")
        lines.append("")
    return "\n".join(lines).strip()


def dict_to_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        lines.append(f"### {key}")
        if isinstance(value, list):
            if value:
                for item in value:
                    lines.append(f"- {item}")
            else:
                lines.append("- 없음")
        elif isinstance(value, dict):
            if not value:
                lines.append("- 없음")
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, list):
                    lines.append(f"- {sub_key}: {', '.join(str(x) for x in sub_value) if sub_value else '없음'}")
                else:
                    lines.append(f"- {sub_key}: {sub_value}")
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines).strip()

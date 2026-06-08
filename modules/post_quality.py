from __future__ import annotations

import re
from typing import Any

from .fact_guard import find_risky_claims, has_direct_experience_note, sanitize_unverified_experience_claims
from .post_exporter import parse_body_segments


HTML_RE = re.compile(r"<[^>]+>")
TAG_RE = re.compile(r"#[0-9A-Za-z가-힣_]+")
PLACEHOLDER_RE = re.compile(r"\[(사진|영상)\s+([0-9,\-\~\s]+)\s*삽입\]")


def _clamp(value: int | float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def _split_paragraphs(body: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body or "") if p.strip()]


def _risky_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped and find_risky_claims(stripped):
            lines.append(stripped)
    return lines


def _count_long_paragraphs(paragraphs: list[str], limit: int = 180) -> int:
    return sum(1 for p in paragraphs if len(p) > limit)


def _count_very_long_lines(body: str, limit: int = 120) -> int:
    return sum(1 for line in (body or "").splitlines() if len(line.strip()) > limit)


def _media_placeholder_counts(body: str) -> dict[str, int]:
    photo = 0
    video = 0
    for match in PLACEHOLDER_RE.finditer(body or ""):
        if match.group(1) == "사진":
            photo += 1
        else:
            video += 1
    return {"photo_placeholders": photo, "video_placeholders": video}


def evaluate_blog_post(
    *,
    title_block: str,
    body: str,
    tags: str,
    full_post: str = "",
    business_analysis: dict[str, Any] | None = None,
    business_research: dict[str, Any] | None = None,
    images: list[dict[str, Any]] | None = None,
    videos: list[dict[str, Any]] | None = None,
    user_experience_note: str = "",
) -> dict[str, Any]:
    """Deterministic post-quality evaluation before Naver upload.

    Scores are advisory. They are meant to catch obvious upload/readability/factuality
    risks without spending extra LLM tokens.
    """
    business_analysis = business_analysis or {}
    business_research = business_research or {}
    images = images or []
    videos = videos or []
    full_text = full_post or f"{title_block}\n\n{body}\n\n{tags}"

    paragraphs = _split_paragraphs(body)
    long_paragraphs = _count_long_paragraphs(paragraphs)
    long_lines = _count_very_long_lines(body)
    risky = _risky_lines(body)
    has_direct_note = has_direct_experience_note(user_experience_note)

    source_results = business_analysis.get("source_results") or []
    verified_facts = business_analysis.get("verified_facts") or []
    valid_result_count = int(business_research.get("valid_result_count") or 0)
    fact_usable_count = int(business_research.get("fact_usable_result_count") or 0)
    avg_quality = float(business_research.get("average_quality_score") or 0)

    # Factuality: source strength + verified facts + risky claim penalty.
    factuality = 55
    if source_results:
        factuality += min(20, len(source_results) * 5)
    if fact_usable_count:
        factuality += min(15, fact_usable_count * 8)
    elif valid_result_count >= 2 and avg_quality >= 45:
        factuality += 8
    if verified_facts:
        factuality += min(15, len(verified_facts) * 3)
    if not source_results and valid_result_count < 2:
        factuality -= 25
    if risky and not has_direct_note:
        factuality -= min(35, len(risky) * 8)

    # Safety score: inverse of unverified review risk.
    safety = 100
    if risky and not has_direct_note:
        safety -= min(60, len(risky) * 12)
    if "다녀왔" in body and not has_direct_note:
        safety -= 15
    if "맛있" in body and not has_direct_note:
        safety -= 10
    if "친절" in body and not has_direct_note:
        safety -= 10

    # Style/mobile readability.
    readability = 100
    readability -= min(35, long_paragraphs * 7)
    readability -= min(25, long_lines * 4)
    if len(paragraphs) < 4:
        readability -= 10
    if len(body) < 500:
        readability -= 5

    # Naver upload suitability.
    naver = 100
    if HTML_RE.search(full_text):
        naver -= 25
    tag_count = len(TAG_RE.findall(tags or ""))
    if tag_count == 0:
        naver -= 20
    elif tag_count < 3:
        naver -= 8
    if "[네이버 지도 첨부]" in full_text:
        naver -= 10

    # Media placement.
    counts = _media_placeholder_counts(body)
    used_media_slots = counts["photo_placeholders"] + counts["video_placeholders"]
    media_score = 80
    if images and counts["photo_placeholders"] == 0:
        media_score -= 25
    if videos and counts["video_placeholders"] == 0:
        media_score -= 15
    if used_media_slots:
        media_score += 15
    if used_media_slots > len(images) + len(videos) + 2:
        media_score -= 15

    # Style reflection is approximate without another LLM call.
    style_score = 80
    if paragraphs and sum(len(p) for p in paragraphs) / max(1, len(paragraphs)) <= 170:
        style_score += 10
    if tag_count >= 3:
        style_score += 5
    if risky and not has_direct_note:
        style_score -= 5

    scores = {
        "overall": _clamp(
            factuality * 0.28
            + safety * 0.22
            + readability * 0.18
            + media_score * 0.12
            + naver * 0.12
            + style_score * 0.08
        ),
        "factuality": _clamp(factuality),
        "safety": _clamp(safety),
        "mobile_readability": _clamp(readability),
        "media_placement": _clamp(media_score),
        "naver_upload_fit": _clamp(naver),
        "style_fit": _clamp(style_score),
    }

    cleaned_preview, softened_lines = sanitize_unverified_experience_claims(body, user_experience_note)

    warnings: list[str] = []
    suggestions: list[str] = []

    if risky and not has_direct_note:
        warnings.append("직접 경험 메모 없이 실제 방문/맛/친절/가성비처럼 보이는 표현이 남아 있습니다.")
        suggestions.append("위험 문장은 '사진상으로는', '방문 전 확인하면 좋다', '실제 후기를 참고하면 좋다' 방식으로 완화하세요.")
    if not source_results and valid_result_count < 2:
        warnings.append("업체 분석 출처가 부족합니다. 발행 전 업체명/주소/영업정보를 직접 확인하세요.")
        suggestions.append("STEP 2 업체 조사를 다시 실행하거나 업체명/주소를 더 정확히 입력하세요.")
    if fact_usable_count == 0 and not source_results:
        warnings.append("본문 사실 근거로 사용할 고신뢰 출처가 없습니다.")
    if long_paragraphs:
        warnings.append(f"모바일 기준으로 긴 문단이 {long_paragraphs}개 있습니다.")
        suggestions.append("긴 문단은 1~3문장 단위로 나누세요.")
    if long_lines:
        warnings.append(f"긴 줄이 {long_lines}개 있습니다. 모바일 화면에서 답답해 보일 수 있습니다.")
    if images and counts["photo_placeholders"] == 0:
        warnings.append("업로드 이미지가 있지만 본문에 사진 삽입 위치가 없습니다.")
        suggestions.append("[사진 1 삽입]처럼 사진 위치를 본문 흐름에 넣으세요.")
    if tag_count == 0:
        warnings.append("태그가 없습니다.")
        suggestions.append("업체명, 지역명, 업종 키워드 중심으로 태그를 3~8개 추가하세요.")
    if HTML_RE.search(full_text):
        warnings.append("HTML 태그가 포함되어 있습니다. 네이버 복사용 텍스트에서는 제거하는 것이 안전합니다.")

    if not warnings:
        suggestions.append("현재 기준으로 큰 위험 요소는 적습니다. 발행 전 업체 정보와 사진 순서만 최종 확인하세요.")

    return {
        "scores": scores,
        "grade": _grade(scores["overall"]),
        "metrics": {
            "paragraph_count": len(paragraphs),
            "long_paragraph_count": long_paragraphs,
            "long_line_count": long_lines,
            "tag_count": tag_count,
            "risky_line_count": len(risky),
            "photo_placeholder_count": counts["photo_placeholders"],
            "video_placeholder_count": counts["video_placeholders"],
            "image_count": len(images),
            "video_count": len(videos),
            "valid_result_count": valid_result_count,
            "fact_usable_result_count": fact_usable_count,
            "source_result_count": len(source_results),
            "verified_fact_count": len(verified_facts),
        },
        "risky_lines": risky,
        "softened_preview": cleaned_preview if softened_lines else "",
        "softened_lines": softened_lines,
        "warnings": warnings,
        "suggestions": suggestions,
    }


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "E"


def quality_report_to_markdown(report: dict[str, Any]) -> str:
    scores = report.get("scores", {})
    lines = [
        f"## 최종 글 품질 평가: {scores.get('overall', 0)}점 / {report.get('grade', '-')}",
        "",
        "### 세부 점수",
        f"- 사실성: {scores.get('factuality', 0)}점",
        f"- 허위 후기 안전성: {scores.get('safety', 0)}점",
        f"- 모바일 가독성: {scores.get('mobile_readability', 0)}점",
        f"- 사진/영상 배치: {scores.get('media_placement', 0)}점",
        f"- 네이버 업로드 적합도: {scores.get('naver_upload_fit', 0)}점",
        f"- 문체 반영 추정: {scores.get('style_fit', 0)}점",
        "",
        "### 주의사항",
    ]
    warnings = report.get("warnings") or []
    lines.extend([f"- {x}" for x in warnings] if warnings else ["- 큰 위험 요소 없음"])
    lines += ["", "### 수정 제안"]
    suggestions = report.get("suggestions") or []
    lines.extend([f"- {x}" for x in suggestions] if suggestions else ["- 별도 제안 없음"])

    risky = report.get("risky_lines") or []
    if risky:
        lines += ["", "### 위험 문장"]
        lines.extend([f"- {x}" for x in risky[:20]])

    return "\n".join(lines)

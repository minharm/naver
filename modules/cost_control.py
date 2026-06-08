from __future__ import annotations

import os
from typing import Any


FALSE_VALUES = {"0", "false", "False", "FALSE", "no", "NO", "off", "OFF", "아니오"}


def env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() not in FALSE_VALUES


def get_cost_settings(token_save_mode: bool | None = None) -> dict[str, Any]:
    enabled = env_bool("TOKEN_SAVE_MODE", True) if token_save_mode is None else bool(token_save_mode)

    if enabled:
        return {
            "token_save_mode": True,
            "max_research_sources_for_generation": int(os.getenv("TOKEN_SAVE_MAX_RESEARCH_SOURCES", "5")),
            "max_source_excerpt_chars": int(os.getenv("TOKEN_SAVE_SOURCE_EXCERPT_CHARS", "450")),
            "max_style_items": int(os.getenv("TOKEN_SAVE_MAX_STYLE_ITEMS", "5")),
            "max_style_text_chars": int(os.getenv("TOKEN_SAVE_STYLE_TEXT_CHARS", "700")),
            "max_image_analysis": int(os.getenv("TOKEN_SAVE_MAX_IMAGE_ANALYSIS", "6")),
            "max_media_context_items": int(os.getenv("TOKEN_SAVE_MAX_MEDIA_CONTEXT_ITEMS", "12")),
            "resize_images_for_analysis": True,
            "analysis_image_max_long_side": int(os.getenv("TOKEN_SAVE_ANALYSIS_IMAGE_MAX_LONG_SIDE", "1024")),
        }

    return {
        "token_save_mode": False,
        "max_research_sources_for_generation": int(os.getenv("NORMAL_MAX_RESEARCH_SOURCES", "10")),
        "max_source_excerpt_chars": int(os.getenv("NORMAL_SOURCE_EXCERPT_CHARS", "900")),
        "max_style_items": int(os.getenv("NORMAL_MAX_STYLE_ITEMS", "10")),
        "max_style_text_chars": int(os.getenv("NORMAL_STYLE_TEXT_CHARS", "1400")),
        "max_image_analysis": int(os.getenv("NORMAL_MAX_IMAGE_ANALYSIS", "15")),
        "max_media_context_items": int(os.getenv("NORMAL_MAX_MEDIA_CONTEXT_ITEMS", "24")),
        "resize_images_for_analysis": True,
        "analysis_image_max_long_side": int(os.getenv("NORMAL_ANALYSIS_IMAGE_MAX_LONG_SIDE", "1280")),
    }


def trim_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def compact_style_profile(profile: dict[str, Any] | None, *, max_items: int = 5, max_text_chars: int = 700) -> dict[str, Any]:
    profile = profile or {}
    compact: dict[str, Any] = {}

    preferred_keys = [
        "tone",
        "문체",
        "style",
        "paragraph_style",
        "문단",
        "자주 쓰는 표현",
        "common_phrases",
        "금지 표현",
        "avoid",
        "writing_rules",
        "작성 규칙",
    ]

    for key in preferred_keys:
        if key not in profile:
            continue
        value = profile[key]
        if isinstance(value, list):
            compact[key] = [trim_text(x, 120) for x in value[:max_items]]
        elif isinstance(value, dict):
            compact[key] = {k: trim_text(v, 160) for k, v in list(value.items())[:max_items]}
        else:
            compact[key] = trim_text(value, max_text_chars)

    if not compact:
        for key, value in list(profile.items())[:max_items]:
            if isinstance(value, list):
                compact[key] = [trim_text(x, 120) for x in value[:max_items]]
            elif isinstance(value, dict):
                compact[key] = {k: trim_text(v, 160) for k, v in list(value.items())[:max_items]}
            else:
                compact[key] = trim_text(value, max_text_chars)

    compact["_compact_profile"] = True
    return compact


def compact_research_analysis(analysis: dict[str, Any] | None, *, max_list_items: int = 8, max_text_chars: int = 900) -> dict[str, Any]:
    analysis = analysis or {}
    keep_keys = [
        "business_profile",
        "verified_facts",
        "likely_facts_needing_check",
        "review_insights",
        "seo_keywords",
        "summary",
    ]

    out: dict[str, Any] = {}
    for key in keep_keys:
        value = analysis.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            out[key] = [trim_text(x, 180) for x in value[:max_list_items]]
        elif isinstance(value, dict):
            compact_dict: dict[str, Any] = {}
            for k, v in value.items():
                if isinstance(v, list):
                    compact_dict[k] = [trim_text(x, 120) for x in v[:max_list_items]]
                else:
                    compact_dict[k] = trim_text(v, 220)
            out[key] = compact_dict
        else:
            out[key] = trim_text(value, max_text_chars)

    source_results = analysis.get("source_results") or []
    if isinstance(source_results, list):
        out["source_results"] = source_results[: min(5, max_list_items)]

    out["_compact_analysis"] = True
    return out


def select_research_sources_for_prompt(
    sources: list[dict[str, Any]] | None,
    *,
    max_sources: int = 5,
    max_excerpt_chars: int = 450,
) -> list[dict[str, Any]]:
    sources = sources or []
    tier_rank = {"high": 0, "medium": 1, "low": 2, "excluded": 3, "": 4}

    def score_key(item: dict[str, Any]) -> tuple[int, int]:
        tier = str(item.get("trust_tier", ""))
        q = int(item.get("quality_score") or 0)
        if item.get("use_for_facts"):
            tier = "high"
        return (tier_rank.get(tier, 4), -q)

    selected = sorted(sources, key=score_key)[:max_sources]
    compacted: list[dict[str, Any]] = []
    for item in selected:
        compacted.append(
            {
                "title": trim_text(item.get("title", ""), 120),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "domain_type": item.get("domain_type", ""),
                "trust_tier": item.get("trust_tier", ""),
                "use_for_facts": bool(item.get("use_for_facts", False)),
                "quality_score": item.get("quality_score", 0),
                "snippet": trim_text(item.get("snippet", ""), max_excerpt_chars),
                "text_excerpt": trim_text(item.get("text_excerpt", ""), max_excerpt_chars),
            }
        )
    return compacted


def limit_media_context(items: list[dict[str, Any]] | None, max_items: int) -> list[dict[str, Any]]:
    return list(items or [])[:max_items]


def make_metadata_only_image_analysis(
    filename: str,
    description: str = "",
    reason: str = "토큰 절약 모드로 AI 이미지 분석 생략",
) -> dict[str, Any]:
    caption = description.strip() or "업로드된 참고 이미지입니다. 세부 내용은 원본 사진 확인이 필요합니다."
    return {
        "file_name": filename,
        "image_type": "기타",
        "visible_elements": [],
        "blog_caption": caption,
        "recommended_position": "중간",
        "cautions": [reason, "이미지 AI 분석을 생략했으므로 본문에서 세부 장면을 단정하지 마세요."],
        "analysis_skipped": True,
        "skip_reason": reason,
    }

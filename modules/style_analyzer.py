from __future__ import annotations

import json
import re
from typing import Any

from .llm_client import ask_ai


def _samples_to_prompt(samples: list[dict]) -> str:
    compact_items = []
    for i, sample in enumerate(samples, start=1):
        compact_items.append(
            f"""
[샘플 {i}]
URL: {sample.get('url', '')}
제목: {sample.get('title', '')}
태그: {', '.join(sample.get('tags', []))}
이미지 수: {sample.get('image_count', 0)} / 영상 수: {sample.get('video_count', 0)}
본문:
{sample.get('body', '')[:5000]}
""".strip()
        )
    return "\n\n---\n\n".join(compact_items)


def _strip_markdown_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _find_json_object(text: str) -> str:
    text = _strip_markdown_fence(text)
    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI 응답에서 JSON 객체를 찾지 못했습니다.")
    return text[start : end + 1]


def _extract_json(text: str) -> dict[str, Any]:
    candidate = _find_json_object(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        # 사용자에게 Python 원문 오류만 보이지 않도록 한국어 메시지로 변환
        raise ValueError(
            f"AI 응답 JSON 형식 오류입니다. 줄 {exc.lineno}, 열 {exc.colno}: {exc.msg}"
        ) from exc


def _repair_json_response(
    broken_text: str,
    error_message: str,
    schema_hint: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Ask the model once to repair malformed JSON, then parse again."""
    repair_prompt = f"""
아래 텍스트는 JSON 형식이 깨진 AI 응답이다.
오류 메시지를 참고해서 올바른 JSON 객체로만 고쳐라.

규칙:
- 설명, 마크다운, 코드블록 없이 JSON만 출력한다.
- 모든 key와 string value는 큰따옴표를 사용한다.
- 문자열 안에 큰따옴표가 필요하면 제거하거나 작은따옴표 느낌의 일반 문장으로 바꾼다.
- 마지막 쉼표 trailing comma를 제거한다.
- 아래 스키마의 key를 유지한다.
- 내용은 한국어로 유지하되, 원문 장문 복사는 피한다.

오류:
{error_message}

스키마:
{schema_hint}

깨진 응답:
{broken_text[:6000]}
""".strip()
    fixed = ask_ai(repair_prompt, model=model, temperature=0)
    return _extract_json(fixed)


def analyze_style(samples: list[dict], model: str | None = None) -> dict[str, Any]:
    if not samples:
        raise ValueError("분석할 블로그 샘플이 없습니다.")

    schema_hint = """
{
  "tone": "",
  "title_patterns": [],
  "opening_patterns": [],
  "paragraph_style": "",
  "photo_flow": "",
  "video_flow": "",
  "body_structure": [],
  "selling_points_style": "",
  "closing_patterns": [],
  "tag_patterns": [],
  "do_rules": [],
  "avoid_rules": [],
  "sample_phrases": []
}
""".strip()

    prompt = f"""
너는 네이버 블로그 글 스타일 분석가다.
아래 사용자의 기존 블로그 글 샘플을 분석해서, 다음에 새 글을 작성할 때 재현할 수 있는 '스타일 프로필'을 만들어라.

주의:
- 본문 내용을 그대로 복사하지 말고 문체/구성/흐름만 분석한다.
- 결과는 반드시 JSON 객체 하나만 출력한다.
- 마크다운 코드블록을 쓰지 않는다.
- JSON 문자열 안에서 큰따옴표를 남발하지 않는다. 필요한 경우 따옴표 없는 일반 문장으로 바꾼다.
- sample_phrases는 원문 문장을 길게 복사하지 말고 짧은 분위기 표현만 넣는다.
- 한국어로 작성한다.

분석해야 할 항목:
1. tone: 말투와 분위기
2. title_patterns: 제목 패턴 5개
3. opening_patterns: 시작 방식
4. paragraph_style: 문단 길이와 줄바꿈 방식
5. photo_flow: 사진 전후 설명 방식
6. video_flow: 영상 삽입 시 자연스러운 설명 방식
7. body_structure: 글 전체 구성 순서
8. selling_points_style: 장점/특징을 강조하는 방식
9. closing_patterns: 마무리 방식
10. tag_patterns: 태그 생성 방식
11. do_rules: 새 글 작성 시 반드시 지킬 규칙
12. avoid_rules: 피해야 할 표현/구성
13. sample_phrases: 사용자의 글에서 자주 보이는 느낌의 표현. 단, 원문 장문 복사는 금지.

출력 JSON 스키마:
{schema_hint}

블로그 샘플:
{_samples_to_prompt(samples)}
""".strip()

    result = ask_ai(prompt, model=model, temperature=0.2)
    try:
        return _extract_json(result)
    except ValueError as first_error:
        try:
            return _repair_json_response(result, str(first_error), schema_hint, model=model)
        except Exception as second_error:  # noqa: BLE001
            raise RuntimeError(
                "스타일 분석 결과를 JSON으로 변환하지 못했습니다. "
                "API 키 문제가 아니라 AI 응답 형식 문제입니다. 다시 스타일 분석을 누르거나 샘플 URL 수를 줄여서 시도하세요."
            ) from second_error

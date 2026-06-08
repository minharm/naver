from __future__ import annotations

import json
import re
from typing import Any

from .formatter import build_media_block
from .fact_guard import sanitize_unverified_experience_claims
from .llm_client import ask_ai


def generate_blog_post(
    style_profile: dict,
    business_info: dict,
    images: list[dict[str, Any]],
    videos: list[dict[str, Any]],
    research_analysis: dict | None = None,
    research_sources: list[dict[str, Any]] | None = None,
    user_experience_note: str = "",
    model: str | None = None,
) -> str:
    media_block = build_media_block(images, videos)
    research_analysis = research_analysis or {}
    research_sources = research_sources or []

    source_lines = []
    for idx, item in enumerate(research_sources[:15], start=1):
        source_lines.append(
            f"{idx}. [{item.get('domain_type', item.get('source', ''))}] {item.get('title', '')} - {item.get('url', '')}\n"
            f"   스니펫: {item.get('snippet', '')[:250]}"
        )

    prompt = f"""
너는 네이버 블로그 글 작성 전문가다.
아래 3가지 자료를 결합해서 새 업체 소개/후기형 블로그 글을 작성하라.

1) 사용자의 기존 블로그 스타일 프로필
2) 웹/블로그/유튜브/플레이스 등 검색 기반 업체 분석 자료
3) 사용자가 업로드한 이미지/영상 AI 분석 자료

핵심 규칙:
- 기존 글을 그대로 베끼지 말고, 문체와 구성만 반영한다.
- 사실은 research_analysis의 business_profile, verified_facts를 최우선으로 따른다.
- 검색 자료에 없는 사실은 지어내지 않는다.
- 주소/연락처/영업시간/가격/주차/예약/배달 정보가 verified_facts 또는 business_profile에 없으면 단정하지 않는다.
- 사용자가 직접 경험 메모에 적지 않은 내용은 '다녀왔다', '먹어봤다', '주문했다', '아이들이 잘 먹었다'처럼 실제 방문 후기인 척 쓰지 않는다.
- 사진만 보고 맛, 친절도, 가격 만족도, 가성비, 대표 메뉴, 직원 응대, 주차 편의성을 단정하지 않는다.
- 사진에서 보이는 내용은 '사진상으로는', '업로드된 사진 기준으로는', '메뉴 사진에서 보이는 구성은'처럼 관찰 기반으로 표현한다.
- 확인 필요 정보는 '방문 전 확인하면 좋다' 수준으로만 쓴다.
- 직접 경험 메모가 비어 있으면 1인칭 체험담이 아니라 '소개/정리형 블로그 글'로 작성한다.
- 네이버 블로그에 복사해서 붙여넣기 좋게 작성한다.
- HTML 코드는 쓰지 않는다.
- PC 화면용 긴 문단이 아니라 모바일 네이버 블로그 기준으로 작성한다.
- 한 문단은 1~3문장 이내로 짧게 쓰고, 문단 사이에는 빈 줄을 넣어 모바일에서 답답하지 않게 한다.
- 줄간격이 넓게 보이도록 너무 긴 문장을 피하고 자연스럽게 끊는다.
- 사진/영상 삽입 위치를 명확히 표시한다.
- 업로드된 사진을 본문 흐름에 맞게 적극 활용한다.
- 사진은 [사진 1 삽입]처럼 표시하고, 바로 아래에 자연스러운 사진 설명을 붙인다.
- 사진 번호는 실제 업로드된 사진 개수 범위 안에서만 사용한다.
- 여러 장을 묶을 때는 [사진 3, 4 삽입] 또는 [사진 6-8 삽입]처럼 표시한다.
- 영상은 [영상 1 삽입]처럼 표시하고, 바로 아래에 자연스러운 영상 설명을 붙인다.
- 영상 번호는 실제 업로드된 영상 개수 범위 안에서만 사용한다.
- 가공 이미지의 자막/라벨 계획이 있으면 본문의 맥락과 어울리게 활용한다.
- 후기/소개 글처럼 자연스럽게 쓰되, 광고성 과장은 피한다.
- 마지막에는 핵심 포인트를 자연스럽게 정리한다.
- 가능하면 본문 전개 속에서 첨부 이미지가 빠지지 않도록 구성한다.
- 네이버 지도/장소는 프로그램 화면에서 별도로 안내하므로 본문 안에는 [네이버 지도 첨부] 같은 문구를 절대 쓰지 않는다.
- 태그는 업체명, 주소지, 업종, 검색 키워드 중심으로 15~25개 생성한다.

출력 형식은 반드시 아래 순서를 지켜라.

[제목 후보]
1. ...
2. ...
3. ...
4. ...
5. ...

[네이버 블로그 본문]
본문 작성

[태그]
#태그 #태그 #태그

사용자 스타일 프로필:
{json.dumps(style_profile, ensure_ascii=False, indent=2)}

최종 사용자 입력:
{json.dumps(business_info, ensure_ascii=False, indent=2)}

사용자 직접 경험 메모:
{user_experience_note.strip() if user_experience_note.strip() else '없음 - 실제 방문/주문/맛/친절도/아이 반응을 단정하지 말 것'}

업체 검색 분석:
{json.dumps(research_analysis, ensure_ascii=False, indent=2)}

검색 출처 요약:
{chr(10).join(source_lines) if source_lines else '검색 출처 없음'}

사진/영상 자료:
{media_block if media_block else '첨부된 사진/영상 자료 없음'}
""".strip()

    text = ask_ai(prompt, model=model, temperature=0.72)
    text = normalize_generated_post(text)
    text, warnings = sanitize_unverified_experience_claims(text, user_experience_note=user_experience_note)
    if warnings:
        text += "\n\n[작성 안전 점검]\n"
        text += "- 직접 경험 메모가 없어 실제 방문/주문/맛/친절도/아이 반응처럼 보이는 표현을 자동 완화했습니다.\n"
    return normalize_generated_post(text)


def normalize_generated_post(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    text = re.sub(r"\n?\s*\[\s*네이버\s*지도\s*첨부\s*\]\s*\n?", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if "[제목 후보]" not in text:
        text = "[제목 후보]\n" + text
    if "[네이버 블로그 본문]" not in text:
        text += "\n\n[네이버 블로그 본문]\n"
    if "[태그]" not in text:
        text += "\n\n[태그]\n"
    return text


def split_generated_post(text: str) -> tuple[str, str, str]:
    title_block = ""
    body = ""
    tags = ""

    if "[제목 후보]" in text and "[네이버 블로그 본문]" in text:
        title_block = text.split("[제목 후보]", 1)[1].split("[네이버 블로그 본문]", 1)[0].strip()
    if "[네이버 블로그 본문]" in text:
        body_part = text.split("[네이버 블로그 본문]", 1)[1]
        if "[태그]" in body_part:
            body, tags = body_part.split("[태그]", 1)
        else:
            body = body_part
    return title_block.strip(), body.strip(), tags.strip()

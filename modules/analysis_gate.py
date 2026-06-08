from __future__ import annotations

from typing import Any


def has_reliable_business_sources(analysis: dict[str, Any] | None, research: dict[str, Any] | None) -> bool:
    analysis = analysis or {}
    research = research or {}

    source_results = analysis.get("source_results") or []
    valid_result_count = int(research.get("valid_result_count") or 0)
    fact_usable_count = int(research.get("fact_usable_result_count") or 0)
    avg_quality = float(research.get("average_quality_score") or 0)

    return len(source_results) >= 2 or fact_usable_count >= 1 or (valid_result_count >= 2 and avg_quality >= 45)


def business_analysis_warning(analysis: dict[str, Any] | None, research: dict[str, Any] | None) -> str:
    """Return a user-facing warning before generation when sources are weak."""
    analysis = analysis or {}
    research = research or {}

    if not analysis:
        return "업체 분석 결과가 없습니다. STEP 2 업체 조사를 먼저 실행하는 것이 안전합니다."

    source_results = analysis.get("source_results") or []
    valid_result_count = int(research.get("valid_result_count") or 0)
    fact_usable_count = int(research.get("fact_usable_result_count") or 0)
    avg_quality = float(research.get("average_quality_score") or 0)

    if fact_usable_count == 0 and not source_results:
        return (
            "출처가 부족합니다. 본문 사실 근거로 사용할 고신뢰 출처가 없습니다. "
            "저신뢰/중신뢰 자료는 분위기 참고만 가능하므로 발행 전 업체명과 주소를 직접 확인하세요."
        )

    if not source_results and valid_result_count < 2:
        return (
            "업체 분석 출처가 부족합니다. source_results가 없고 유효 검색 결과도 부족하므로 "
            "생성 글은 사실 단정 없이 작성되며, 발행 전 수동 확인이 필요합니다."
        )

    if valid_result_count > 0 and avg_quality < 45:
        return (
            f"검색 결과 평균 품질 점수가 낮습니다. 현재 평균 {avg_quality}점입니다. "
            "같은 업체인지 주소/지역을 다시 확인하세요."
        )

    return ""

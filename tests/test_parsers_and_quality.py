import sys
import types

# These parser/quality tests do not call the OpenAI API.
# Provide a tiny fake module so importing modules that reference OpenAI
# does not require a real SDK during lightweight unit tests.
fake_openai = types.ModuleType("openai")
fake_openai.OpenAI = object
sys.modules.setdefault("openai", fake_openai)

from modules.blog_generator import normalize_generated_post, split_generated_post
from modules.post_exporter import parse_index_spec, parse_body_segments
from modules.web_research import SearchResult, _quality_score, analyze_business_research, _trust_tier, _extract_structured_facts


def test_parse_index_spec_ranges_and_unique():
    assert parse_index_spec("1, 3-5, 5, 7~8") == [1, 3, 4, 5, 7, 8]


def test_parse_body_segments_removes_map_placeholder():
    body = "첫 문단\n\n[사진 1, 2 삽입]\n\n설명\n\n[네이버 지도 첨부]"
    segs = parse_body_segments(body)
    assert segs[0]["type"] == "text"
    assert segs[1]["type"] == "photo"
    assert segs[1]["indices"] == [1, 2]
    assert all("[네이버 지도 첨부]" not in str(s) for s in segs)


def test_normalize_generated_post_removes_map_placeholder():
    text = "[제목 후보]\n1. 제목\n\n[네이버 블로그 본문]\n본문\n\n[네이버 지도 첨부]\n\n[태그]\n#태그"
    norm = normalize_generated_post(text)
    assert "[네이버 지도 첨부]" not in norm
    title, body, tags = split_generated_post(norm)
    assert "제목" in title
    assert "본문" in body
    assert "#태그" in tags


def test_quality_score_rejects_naver_menu():
    item = SearchResult(source="네이버", title="NAVER", url="https://www.naver.com", snippet="")
    score, reasons = _quality_score(item, "후이후이", "경기도 수원시 영통구 덕영대로 1566")
    assert score < 0


def test_quality_score_accepts_relevant_blog():
    item = SearchResult(
        source="네이버 블로그",
        title="영통맛집 수원중국집 후이후이",
        url="https://blog.naver.com/example/123",
        snippet="후이후이 경기 수원시 영통구 덕영대로 1566 방문 후기",
        text_excerpt="후이후이 경기 수원시 영통구 덕영대로 1566 " * 10,
    )
    score, reasons = _quality_score(item, "후이후이", "경기도 수원시 영통구 덕영대로 1566")
    assert score >= 25
    assert "business_name_match" in reasons


def test_quality_score_caps_blog_name_only_without_region():
    item = SearchResult(
        source="네이버 블로그",
        title="후이후이 맛집 후기",
        url="https://blog.naver.com/example/456",
        snippet="후이후이 메뉴가 다양하다는 글",
        text_excerpt="후이후이 " * 50,
    )
    score, reasons = _quality_score(item, "후이후이", "경기도 수원시 영통구 덕영대로 1566")
    assert score <= 55
    assert "name_only_score_cap" in reasons or "blog_name_only_score_cap" in reasons


def test_quality_score_penalizes_conflicting_region():
    item = SearchResult(
        source="네이버 블로그",
        title="부산 후이후이 방문 후기",
        url="https://blog.naver.com/example/789",
        snippet="후이후이 부산광역시 해운대구 우동 방문 후기",
        text_excerpt="후이후이 부산광역시 해운대구 우동 " * 10,
    )
    score, reasons = _quality_score(item, "후이후이", "경기도 수원시 영통구 덕영대로 1566")
    assert "conflicting_region_penalty" in reasons
    assert score < 25


def test_analyze_business_research_falls_back_when_web_fails_and_quality_low(monkeypatch):
    import modules.web_research as wr

    def fake_web(*args, **kwargs):
        raise RuntimeError("web failed")

    monkeypatch.setattr(wr, "ask_ai_with_web_search", fake_web)
    result = analyze_business_research(
        {
            "business_name": "후이후이",
            "address": "경기도 수원시 영통구 덕영대로 1566",
            "results": [{"title": "NAVER", "url": "https://www.naver.com"}],
            "valid_result_count": 0,
            "average_quality_score": 0,
        }
    )
    assert "검색 결과가 충분하지 않습니다" in result["summary"]
    assert result["source_results"] == []


def test_trust_tier_thresholds():
    assert _trust_tier(70) == "high"
    assert _trust_tier(45) == "medium"
    assert _trust_tier(25) == "low"
    assert _trust_tier(24) == "excluded"


def test_high_trust_same_source_name_and_address():
    item = SearchResult(
        source="네이버 블로그",
        title="영통 후이후이 후기",
        url="https://blog.naver.com/example/high",
        snippet="후이후이 경기 수원시 영통구 덕영대로 1566",
        text_excerpt="후이후이 경기 수원시 영통구 덕영대로 1566 " * 10,
    )
    score, reasons = _quality_score(item, "후이후이", "경기도 수원시 영통구 덕영대로 1566")
    assert score >= 70
    assert _trust_tier(score) == "high"
    assert "same_source_name_and_strong_address" in reasons or "address_term_match" in reasons


def test_structured_facts_infers_cafe_keywords():
    item = SearchResult(
        source="블로그",
        title="동탄 카페 후기",
        url="https://blog.naver.com/cafe/1",
        snippet="아메리카노 라떼 디저트 케이크가 있는 카페",
        text_excerpt="아메리카노 라떼 디저트 케이크 " * 5,
    )
    facts = _extract_structured_facts(item)
    assert facts["inferred_category"] == "카페"
    assert "아메리카노" in facts["service_or_menu_mentions"]


def test_structured_facts_infers_kids_cafe_keywords():
    item = SearchResult(
        source="블로그",
        title="키즈카페 이용 후기",
        url="https://blog.naver.com/kids/1",
        snippet="입장료 보호자 놀이시설 파티룸 이용시간",
        text_excerpt="입장료 보호자 놀이시설 파티룸 " * 5,
    )
    facts = _extract_structured_facts(item)
    assert facts["inferred_category"] == "키즈카페"
    assert "입장료" in facts["service_or_menu_mentions"]

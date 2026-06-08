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
from modules.web_research import SearchResult, _quality_score


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

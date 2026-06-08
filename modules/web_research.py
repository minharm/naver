from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup

from .llm_client import ask_ai, ask_ai_with_web_search


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


@dataclass
class SearchResult:
    source: str
    title: str
    url: str
    snippet: str = ""
    text_excerpt: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get(url: str, timeout: int = 12) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    if not response.encoding:
        response.encoding = response.apparent_encoding
    return response.text


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    out: list[SearchResult] = []
    for item in results:
        url = _normalize_search_url(item.url)
        key = url.split("#", 1)[0].rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        item.url = url
        out.append(item)
    return out


def _normalize_search_url(url: str) -> str:
    if not url:
        return ""
    url = html.unescape(url).strip()
    if url.startswith("//"):
        url = "https:" + url

    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)

    # DuckDuckGo/Naver/Google redirect wrappers
    for key in ["uddg", "url", "u", "q"]:
        val = qs.get(key, [""])[0]
        if val.startswith(("http://", "https://")):
            return urllib.parse.unquote(val)

    if "google." in parsed.netloc and parsed.path == "/url":
        val = qs.get("q", [""])[0]
        if val.startswith(("http://", "https://")):
            return urllib.parse.unquote(val)

    return url


def _classify_domain(url: str) -> str:
    url_l = url.lower()
    if "blog.naver.com" in url_l or "m.blog.naver.com" in url_l:
        return "네이버 블로그"
    if "youtube.com" in url_l or "youtu.be" in url_l:
        return "유튜브"
    if any(x in url_l for x in ["place.naver.com", "map.naver.com", "place.map.kakao.com", "diningcode.com", "mangoplate.com"]):
        return "지도/맛집/플레이스"
    if any(x in url_l for x in ["instagram.com", "facebook.com", "x.com", "twitter.com"]):
        return "SNS"
    return "웹"


BAD_HOST_KEYWORDS = [
    "shopping.naver.com",
    "dict.naver.com",
    "en.dict.naver.com",
    "kin.naver.com",
    "news.naver.com",
    "section.blog.naver.com",
    "help.naver.com",
    "www.naver.com",
    "m.naver.com",
    "adcr.naver.com",
    "terms.naver.com",
]

BAD_TITLE_KEYWORDS = [
    "naver",
    "네이버 메인",
    "쇼핑",
    "어학사전",
    "영어사전",
    "이미지",
    "동영상",
    "지도 검색",
    "검색결과",
    "통합검색",
    "더보기",
    "로그인",
    "고객센터",
]


def _important_address_terms(address: str) -> list[str]:
    terms: list[str] = []
    text = _clean_text(address)
    for pat in [r"([가-힣]+시)", r"([가-힣]+구)", r"([가-힣]+동)", r"([가-힣]+로)\s*(\d+)"]:
        for m in re.finditer(pat, text):
            if len(m.groups()) == 2:
                terms.append(f"{m.group(1)} {m.group(2)}")
                terms.append(m.group(1))
                terms.append(m.group(2))
            else:
                terms.append(m.group(1))
    return list(dict.fromkeys([t for t in terms if t]))


def _is_bad_result(item: SearchResult) -> bool:
    url_l = (item.url or "").lower()
    title_l = (item.title or "").strip().lower()
    host = urllib.parse.urlparse(item.url or "").netloc.lower()
    if any(bad in host for bad in BAD_HOST_KEYWORDS):
        return True
    if host in {"naver.com", "www.naver.com", "m.naver.com"}:
        return True
    # Very short generic anchors from Naver menus
    if title_l in {x.lower() for x in BAD_TITLE_KEYWORDS}:
        return True
    if len(title_l) <= 2:
        return True
    return False


def _target_region_terms(address: str) -> dict[str, set[str]]:
    text = _clean_text(address)
    cities = set(re.findall(r"([가-힣]+시)", text))
    districts = set(re.findall(r"([가-힣]+구)", text))
    dongs = set(re.findall(r"([가-힣]+동)", text))
    roads = set()
    for m in re.finditer(r"([가-힣]+로)\s*(\d+)", text):
        roads.add(m.group(1))
        roads.add(f"{m.group(1)} {m.group(2)}")
    return {"city": cities, "district": districts, "dong": dongs, "road": roads}


def _region_match_level(text: str, address: str) -> tuple[str, list[str]]:
    text_l = _clean_text(text).lower()
    terms = _target_region_terms(address)
    matched: list[str] = []

    road_matches = [x.lower() for x in terms["road"] if x.lower() in text_l]
    district_matches = [x.lower() for x in terms["district"] if x.lower() in text_l]
    city_matches = [x.lower() for x in terms["city"] if x.lower() in text_l]
    dong_matches = [x.lower() for x in terms["dong"] if x.lower() in text_l]

    matched.extend(road_matches + district_matches + city_matches + dong_matches)

    if road_matches and (district_matches or city_matches):
        return "strong", matched
    if road_matches or (district_matches and city_matches):
        return "medium", matched
    if city_matches or district_matches or dong_matches:
        return "weak", matched
    return "none", []


def _has_conflicting_region(text: str, address: str) -> bool:
    """Detect obvious other-region results.

    Conservative: only treat as conflict when the target city is missing and
    another city is explicitly present.
    """
    text_clean = _clean_text(text)
    target = _target_region_terms(address)
    target_cities = target["city"]
    if not target_cities:
        return False
    mentioned_cities = set(re.findall(r"([가-힣]+시)", text_clean))
    if not mentioned_cities:
        return False
    if target_cities & mentioned_cities:
        return False
    return True


MENU_KEYWORDS_BY_CATEGORY = {
    "중식": ["짜장", "짜장면", "짬뽕", "탕수육", "볶음밥", "마라", "냉짬뽕", "유린기", "깐풍기", "멘보샤", "코스", "세트"],
    "카페": ["아메리카노", "라떼", "카푸치노", "에이드", "스무디", "디저트", "케이크", "베이커리", "크로플", "쿠키", "브런치"],
    "고깃집": ["삼겹살", "목살", "갈비", "한우", "등심", "안심", "냉면", "된장찌개", "소고기", "돼지고기", "양념갈비"],
    "키즈카페": ["입장료", "보호자", "놀이시설", "파티룸", "생일파티", "트램폴린", "볼풀", "정글짐", "주차", "이용시간"],
    "병원": ["진료과목", "예약", "접수", "진료시간", "주차", "의사", "검진", "상담", "처방", "치료"],
    "공방": ["원데이클래스", "체험", "예약", "수업", "클래스", "재료비", "작품", "공예", "도자기", "가죽"],
    "숙박": ["객실", "체크인", "체크아웃", "조식", "주차", "예약", "수영장", "바베큐", "펜션", "호텔"],
    "일반": ["예약", "주차", "영업시간", "가격", "서비스", "이용시간"],
}


def _infer_business_category(text: str) -> str:
    text = text or ""
    scores: dict[str, int] = {}
    for category, keywords in MENU_KEYWORDS_BY_CATEGORY.items():
        if category == "일반":
            continue
        scores[category] = sum(1 for keyword in keywords if keyword in text)
    if not scores:
        return "일반"
    category, score = max(scores.items(), key=lambda kv: kv[1])
    return category if score > 0 else "일반"


def _extract_structured_facts(item: SearchResult) -> dict[str, Any]:
    text = f"{item.title}\n{item.snippet}\n{item.text_excerpt}"
    phones = sorted(set(re.findall(r"\b0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}\b", text)))
    hours = sorted(set(re.findall(r"(?:영업시간|운영시간|매일|평일|주말|브레이크타임|진료시간|체크인|체크아웃)[^\\n]{0,70}", text)))

    category = _infer_business_category(text)
    keywords = MENU_KEYWORDS_BY_CATEGORY.get(category, []) + MENU_KEYWORDS_BY_CATEGORY["일반"]
    service_mentions = sorted(set(keyword for keyword in keywords if keyword in text))

    return {
        "inferred_category": category,
        "phone_numbers": phones,
        "hours_mentions": hours,
        "service_or_menu_mentions": service_mentions,
    }



def _quality_score(item: SearchResult, business_name: str, address: str) -> tuple[int, list[str]]:
    reasons: list[str] = []
    if _is_bad_result(item):
        return -100, ["bad_generic_or_naver_menu"]

    combined_text = f"{item.title} {item.snippet} {item.text_excerpt} {item.url}"
    text = combined_text.lower()
    name = business_name.lower().strip()
    address_terms = [t.lower() for t in _important_address_terms(address)]
    region_level, region_matches = _region_match_level(combined_text, address)

    score = 0
    url_l = item.url.lower()

    is_blog = "blog.naver.com" in url_l or "m.blog.naver.com" in url_l
    is_place = "place.naver.com" in url_l or "map.naver.com" in url_l
    is_local_review = any(x in url_l for x in ["diningcode.com", "mangoplate.com", "place.map.kakao.com"])

    if is_place:
        score += 40; reasons.append("place_or_map")
    if is_blog:
        score += 30; reasons.append("naver_blog")
    if is_local_review:
        score += 28; reasons.append("local_review_site")
    if "youtube.com" in url_l or "youtu.be" in url_l:
        score += 15; reasons.append("youtube")

    has_name = bool(name and name in text)
    has_any_address = bool(address_terms and any(t in text for t in address_terms))

    if has_name:
        score += 25; reasons.append("business_name_match")
    if has_any_address:
        score += 25; reasons.append("address_term_match")

    if has_name and region_level == "strong":
        score += 35; reasons.append("same_source_name_and_strong_address")
    elif has_name and region_level == "medium":
        score += 25; reasons.append("same_source_name_and_medium_address")
    elif has_name and region_level == "weak":
        score += 10; reasons.append("same_source_name_and_weak_region")
    elif has_name and region_level == "none":
        score += 0; reasons.append("name_only_no_region")

    if _has_conflicting_region(combined_text, address):
        score -= 80; reasons.append("conflicting_region_penalty")

    if is_blog and has_name and region_level == "none":
        score = min(score, 45); reasons.append("blog_name_only_score_cap")
    if has_name and not has_any_address and region_level == "none":
        score = min(score, 55); reasons.append("name_only_score_cap")
    if not has_name and region_level == "none":
        score -= 30; reasons.append("no_name_no_region_penalty")

    if item.text_excerpt and len(item.text_excerpt) >= 120:
        score += 10; reasons.append("has_excerpt")
    if item.snippet and len(item.snippet) >= 40:
        score += 5; reasons.append("has_snippet")

    structured = _extract_structured_facts(item)
    if structured["phone_numbers"]:
        score += 5; reasons.append("phone_mention")
    if structured["hours_mentions"]:
        score += 5; reasons.append("hours_mention")
    if structured["service_or_menu_mentions"]:
        score += 3; reasons.append("menu_mention")

    generic_title = any(k in (item.title or "").lower() for k in [k.lower() for k in BAD_TITLE_KEYWORDS])
    if generic_title and not (name and name in (item.title or "").lower()):
        score -= 40; reasons.append("generic_title_penalty")

    return score, reasons


def _trust_tier(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    if score >= 25:
        return "low"
    return "excluded"


def _can_use_for_facts(score: int) -> bool:
    return _trust_tier(score) == "high"


def _quality_filter_results(results: list[SearchResult], business_name: str, address: str) -> tuple[list[SearchResult], list[dict[str, Any]]]:
    scored_rows: list[dict[str, Any]] = []
    for item in results:
        score, reasons = _quality_score(item, business_name, address)
        scored_rows.append({
            "item": item,
            "quality_score": score,
            "quality_reasons": reasons,
            "trust_tier": _trust_tier(score),
            "use_for_facts": _can_use_for_facts(score),
        })

    scored_rows.sort(key=lambda r: r["quality_score"], reverse=True)
    # Keep low/medium/high results for review, but only high-trust rows are
    # considered safe enough for direct factual grounding.
    selected = [r for r in scored_rows if r["trust_tier"] in {"high", "medium", "low"}]
    if not selected:
        selected = [r for r in scored_rows if r["quality_score"] > 0]
    return [r["item"] for r in selected], scored_rows


def _looks_useful(href: str) -> bool:
    if not href.startswith(("http://", "https://")):
        return False
    bad_domains = [
        "search.naver.com",
        "m.search.naver.com",
        "help.naver.com",
        "shopping.naver.com",
        "dict.naver.com",
        "en.dict.naver.com",
        "kin.naver.com",
        "news.naver.com",
        "section.blog.naver.com",
        "www.naver.com",
        "m.naver.com",
        "adcr.naver.com",
        "ssl.pstatic.net",
        "nstatic.net",
        "google.com/preferences",
        "accounts.google.com",
    ]
    host = urllib.parse.urlparse(href).netloc.lower()
    return not any(bad in host for bad in bad_domains)


def _generic_extract_results(
    soup: BeautifulSoup,
    source_name: str,
    max_results: int,
    required_terms: list[str] | None = None,
) -> list[SearchResult]:
    """Selector-independent extractor for Naver/Google result pages.

    Naver markup changes often. This intentionally combines known selectors
    with a generic anchor scan, then filters irrelevant links.
    """
    candidates: list[SearchResult] = []
    selectors = [
        "a.title_link",
        "a.api_txt_lines.total_tit",
        "a.total_tit",
        "a.link_tit",
        "a.news_tit",
        "a.name_link",
        "a.tit",
        "a.sub_tit",
        "a",
    ]

    for selector in selectors:
        for link in soup.select(selector):
            title = _clean_text(link.get_text(" ", strip=True))
            href = _normalize_search_url(link.get("href", ""))
            if not title or len(title) < 2 or not _looks_useful(href):
                continue

            parent = link.find_parent()
            snippet = ""
            if parent:
                snippet = _clean_text(parent.get_text(" ", strip=True))[:450]

            text_for_filter = f"{title} {snippet}".lower()
            if required_terms:
                # 하나라도 포함되면 통과. 너무 강하게 걸면 업체명 표기가 HUIHUI처럼 변형될 때 누락됨.
                terms = [t.lower() for t in required_terms if t.strip()]
                if terms and not any(t in text_for_filter for t in terms):
                    # 단, 네이버 블로그/플레이스/맛집 사이트 링크는 후보로 살림
                    if not any(x in href.lower() for x in ["blog.naver.com", "place.naver.com", "diningcode.com", "mangoplate.com", "youtube.com"]):
                        continue

            candidates.append(SearchResult(source=source_name, title=title, url=href, snippet=snippet))
            if len(_dedupe(candidates)) >= max_results:
                return _dedupe(candidates)[:max_results]

    return _dedupe(candidates)[:max_results]


def search_duckduckgo(query: str, max_results: int = 5, source_name: str = "DuckDuckGo") -> list[SearchResult]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        soup = BeautifulSoup(_get(url), "lxml")
    except Exception:
        return []

    results: list[SearchResult] = []
    for node in soup.select(".result"):
        link = node.select_one("a.result__a")
        if not link:
            continue
        title = _clean_text(link.get_text(" ", strip=True))
        href = _normalize_search_url(link.get("href", ""))
        snippet_node = node.select_one(".result__snippet")
        snippet = _clean_text(snippet_node.get_text(" ", strip=True) if snippet_node else "")
        if title and _looks_useful(href):
            results.append(SearchResult(source=source_name, title=title, url=href, snippet=snippet))
        if len(results) >= max_results:
            break
    return _dedupe(results)[:max_results]


def search_google(query: str, max_results: int = 5) -> list[SearchResult]:
    url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query, "hl": "ko", "num": max_results + 5})
    try:
        soup = BeautifulSoup(_get(url), "lxml")
    except Exception:
        return []
    return _generic_extract_results(soup, "Google 검색", max_results, required_terms=[])


def search_naver_pc(query: str, where: str = "nexearch", max_results: int = 5) -> list[SearchResult]:
    url = "https://search.naver.com/search.naver?" + urllib.parse.urlencode({"where": where, "query": query})
    try:
        soup = BeautifulSoup(_get(url), "lxml")
    except Exception:
        return []
    label = {
        "nexearch": "네이버 통합검색",
        "view": "네이버 VIEW",
        "blog": "네이버 블로그",
    }.get(where, f"네이버 {where}")
    return _generic_extract_results(soup, label, max_results, required_terms=[])


def search_naver_mobile(query: str, where: str = "m_view", max_results: int = 5) -> list[SearchResult]:
    # m_view/m_blog가 막힐 때도 m 통합검색이 결과를 주는 경우가 있어 둘 다 활용한다.
    url = "https://m.search.naver.com/search.naver?" + urllib.parse.urlencode({"where": where, "query": query})
    try:
        soup = BeautifulSoup(_get(url), "lxml")
    except Exception:
        return []
    label = {
        "m": "네이버 모바일 통합검색",
        "m_view": "네이버 모바일 VIEW",
        "m_blog": "네이버 모바일 블로그",
    }.get(where, f"네이버 모바일 {where}")
    return _generic_extract_results(soup, label, max_results, required_terms=[])


def search_naver_openapi(query: str, service: str, max_results: int = 5) -> list[SearchResult]:
    """Optional official Naver Search API.

    If NAVER_CLIENT_ID and NAVER_CLIENT_SECRET are not set, returns [].
    service examples: blog, local, webkr
    """
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return []

    endpoint = f"https://openapi.naver.com/v1/search/{service}.json"
    params = {"query": query, "display": max_results, "sort": "sim"}
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "User-Agent": HEADERS["User-Agent"],
    }
    try:
        resp = requests.get(endpoint, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    source_label = {
        "blog": "네이버 검색API 블로그",
        "local": "네이버 검색API 지역",
        "webkr": "네이버 검색API 웹문서",
    }.get(service, f"네이버 검색API {service}")

    out: list[SearchResult] = []
    for item in data.get("items", []):
        title = _clean_text(re.sub(r"<.*?>", "", item.get("title", "")))
        link = item.get("link") or item.get("bloggerlink") or ""
        snippet = _clean_text(re.sub(r"<.*?>", "", item.get("description", "")))
        if service == "local":
            road = _clean_text(item.get("roadAddress", ""))
            tel = _clean_text(item.get("telephone", ""))
            category = _clean_text(item.get("category", ""))
            snippet = " / ".join(x for x in [category, road, tel, snippet] if x)
            link = link or "https://search.naver.com/search.naver?" + urllib.parse.urlencode({"query": query})
        if title:
            out.append(SearchResult(source=source_label, title=title, url=_normalize_search_url(link), snippet=snippet))
    return _dedupe(out)[:max_results]


def search_youtube_rss(query: str, max_results: int = 5) -> list[SearchResult]:
    url = "https://www.youtube.com/feeds/videos.xml?" + urllib.parse.urlencode({"search_query": query})
    try:
        xml_text = _get(url)
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "media": "http://search.yahoo.com/mrss/",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    results: list[SearchResult] = []
    for entry in root.findall("atom:entry", ns):
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        video_id = entry.findtext("yt:videoId", default="", namespaces=ns)
        link = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        desc_node = entry.find("media:group/media:description", ns)
        desc = _clean_text(desc_node.text if desc_node is not None else "")
        if title and link:
            results.append(SearchResult(source="YouTube", title=title, url=link, snippet=desc[:300]))
        if len(results) >= max_results:
            break
    return _dedupe(results)[:max_results]


def fetch_page_excerpt(url: str, max_chars: int = 1800) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return ""
    try:
        soup = BeautifulSoup(_get(url, timeout=10), "lxml")
    except Exception:
        return ""

    # Naver blog iframe canonical page support
    iframe = soup.select_one("iframe#mainFrame")
    if iframe and iframe.get("src") and "blog.naver.com" in url:
        iframe_url = urllib.parse.urljoin(url, iframe.get("src", ""))
        try:
            soup = BeautifulSoup(_get(iframe_url, timeout=10), "lxml")
        except Exception:
            pass

    for noisy in soup.select("script, style, iframe, noscript, svg, header, footer"):
        noisy.decompose()

    candidates = [
        soup.select_one("div.se-main-container"),
        soup.select_one("div#postViewArea"),
        soup.select_one("article"),
        soup.select_one("main"),
        soup.body,
    ]
    for node in candidates:
        if not node:
            continue
        text = _clean_text(node.get_text("\n", strip=True))
        if len(text) > 80:
            return text[:max_chars]
    return ""


def _address_keywords(address: str) -> list[str]:
    text = _clean_text(address)
    if not text:
        return []

    parts: list[str] = []
    # 시/군/구/동/로 + 건물번호 조합
    for pat in [r"([가-힣]+시)", r"([가-힣]+군)", r"([가-힣]+구)", r"([가-힣]+동)", r"([가-힣]+로)\s*(\d+)"]:
        for m in re.finditer(pat, text):
            if len(m.groups()) == 2:
                parts.append(f"{m.group(1)} {m.group(2)}")
            else:
                parts.append(m.group(1))

    # 너무 긴 주소는 검색 정확도가 떨어져 일부만 사용
    tokens = [t for t in re.split(r"\s+", text) if t]
    if len(tokens) >= 2:
        parts.append(" ".join(tokens[:2]))
    if len(tokens) >= 3:
        parts.append(" ".join(tokens[:3]))
    return list(dict.fromkeys(parts))


def _build_query_variants(business_name: str, address: str) -> dict[str, list[str]]:
    name = business_name.strip()
    address = address.strip()
    addr_keys = _address_keywords(address)

    location_queries = []
    for key in addr_keys[:5]:
        location_queries.extend([
            f"{name} {key}",
            f"{name} {key} 후기",
            f"{name} {key} 블로그",
        ])

    return {
        "naver_core": [
            name,
            f"{name} 블로그",
            f"{name} 후기",
            f"{name} 맛집",
            f"{name} 네이버 블로그",
            f"{name} {address}",
            *location_queries,
        ],
        "place": [
            f"{name} {address}",
            f"{name} 네이버 플레이스",
            f"{name} 지도",
            f"{name} 다이닝코드",
        ],
        "web": [
            f"{name} {address}",
            f"{name} 후기 리뷰",
            f"{name} 업체 정보",
            f"{name} 맛집 리뷰",
        ],
        "youtube": [
            f"{name} 후기",
            f"{name} 방문",
            f"{name} 맛집",
        ],
        "api": [
            f"{name} {address}",
            f"{name} 후기",
            f"{name} 맛집",
        ],
    }


def research_business(
    business_name: str,
    address: str = "",
    max_results_per_group: int = 5,
    fetch_excerpts: bool = True,
) -> dict[str, Any]:
    if not business_name.strip():
        raise ValueError("업체명을 입력하세요.")

    queries = _build_query_variants(business_name, address)

    grouped: dict[str, list[SearchResult]] = {
        "naver_api": [],
        "naver_pc": [],
        "naver_mobile": [],
        "google": [],
        "duckduckgo": [],
        "youtube": [],
    }

    # 1) Optional official API first
    for q in queries["api"][:3]:
        grouped["naver_api"].extend(search_naver_openapi(q, "local", max_results_per_group))
        grouped["naver_api"].extend(search_naver_openapi(q, "blog", max_results_per_group))
        grouped["naver_api"].extend(search_naver_openapi(q, "webkr", max_results_per_group))

    # 2) Naver PC/Mobile search. This is the most important path for Korean local businesses.
    for q in queries["naver_core"][:10]:
        grouped["naver_pc"].extend(search_naver_pc(q, "view", max_results_per_group))
        grouped["naver_pc"].extend(search_naver_pc(q, "blog", max_results_per_group))
        grouped["naver_pc"].extend(search_naver_pc(q, "nexearch", max_results_per_group))
        grouped["naver_mobile"].extend(search_naver_mobile(q, "m_view", max_results_per_group))
        grouped["naver_mobile"].extend(search_naver_mobile(q, "m", max_results_per_group))

    # 3) Place/web/review search fallbacks
    for q in queries["place"]:
        grouped["duckduckgo"].extend(search_duckduckgo(q, max_results_per_group, source_name="플레이스/웹 검색"))
        grouped["google"].extend(search_google(q, max_results_per_group))

    for q in queries["web"]:
        grouped["duckduckgo"].extend(search_duckduckgo(q, max_results_per_group, source_name="웹/리뷰 검색"))
        grouped["google"].extend(search_google(q, max_results_per_group))

    for q in queries["youtube"]:
        grouped["youtube"].extend(search_youtube_rss(q, max_results_per_group))

    raw_results = _dedupe([item for items in grouped.values() for item in items])

    # First quality pass before fetching pages; this removes obvious NAVER menu links.
    candidates, raw_scored_rows = _quality_filter_results(raw_results, business_name, address)

    if fetch_excerpts:
        for idx, item in enumerate(candidates[:30]):
            item.text_excerpt = fetch_page_excerpt(item.url)
            if idx < min(len(candidates), 30) - 1:
                time.sleep(0.1)

    # Second quality pass after excerpts.
    valid_results, scored_rows = _quality_filter_results(candidates, business_name, address)
    valid_scores = {r["item"].url: r for r in scored_rows}

    results_as_dicts: list[dict[str, Any]] = []
    for item in valid_results[:40]:
        row = item.to_dict()
        row["domain_type"] = _classify_domain(item.url)
        score_info = valid_scores.get(item.url, {})
        row["quality_score"] = score_info.get("quality_score", 0)
        row["quality_reasons"] = score_info.get("quality_reasons", [])
        row["trust_tier"] = score_info.get("trust_tier", _trust_tier(int(row["quality_score"])))
        row["use_for_facts"] = bool(score_info.get("use_for_facts", _can_use_for_facts(int(row["quality_score"]))))
        row["structured_facts"] = _extract_structured_facts(item)
        results_as_dicts.append(row)

    valid_count = len([r for r in results_as_dicts if int(r.get("quality_score", 0)) >= 25])
    high_trust_count = len([r for r in results_as_dicts if r.get("trust_tier") == "high"])
    medium_trust_count = len([r for r in results_as_dicts if r.get("trust_tier") == "medium"])
    low_trust_count = len([r for r in results_as_dicts if r.get("trust_tier") == "low"])
    fact_usable_count = len([r for r in results_as_dicts if r.get("use_for_facts")])
    avg_quality = round(sum(int(r.get("quality_score", 0)) for r in results_as_dicts) / len(results_as_dicts), 1) if results_as_dicts else 0

    return {
        "business_name": business_name,
        "address": address,
        "queries": queries,
        "raw_result_count": len(raw_results),
        "result_count": len(results_as_dicts),
        "valid_result_count": valid_count,
        "high_trust_result_count": high_trust_count,
        "medium_trust_result_count": medium_trust_count,
        "low_trust_result_count": low_trust_count,
        "fact_usable_result_count": fact_usable_count,
        "average_quality_score": avg_quality,
        "quality_threshold": 25,
        "fact_usable_threshold": 70,
        "results": results_as_dicts,
        "structured_facts_by_source": [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "domain_type": r.get("domain_type", ""),
                "structured_facts": r.get("structured_facts", {}),
            }
            for r in results_as_dicts
            if r.get("structured_facts", {}).get("phone_numbers")
            or r.get("structured_facts", {}).get("hours_mentions")
            or r.get("structured_facts", {}).get("service_or_menu_mentions")
        ],
        "group_counts": {k: len(v) for k, v in grouped.items()},
    }


def _research_to_prompt(research_data: dict[str, Any]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(research_data.get("results", []), start=1):
        lines.append(
            f"""
[검색결과 {idx}]
출처 유형: {item.get('domain_type', '')}
수집 출처: {item.get('source', '')}
신뢰등급: {item.get('trust_tier', '')}
본문 사실 근거 사용 가능: {item.get('use_for_facts', False)}
품질점수: {item.get('quality_score', '')}
품질사유: {item.get('quality_reasons', [])}
제목: {item.get('title', '')}
URL: {item.get('url', '')}
요약/스니펫: {item.get('snippet', '')}
본문 일부:
{item.get('text_excerpt', '')[:1800]}
""".strip()
        )
    return "\n\n---\n\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI 응답에서 JSON을 찾지 못했습니다.")
    return json.loads(text[start:end + 1])


def _build_business_web_search_prompt(research_data: dict[str, Any]) -> str:
    """Prompt for OpenAI web search based business research."""
    business_name = research_data.get("business_name", "")
    address = research_data.get("address", "")
    local_results = _research_to_prompt(research_data) if research_data.get("results") else "로컬 스크래핑 결과 없음"

    return f"""
너는 한국 로컬 업체 리서치 전문가다.
사용자가 입력한 업체명과 주소를 기준으로, 웹 검색 도구를 사용해서 공개 자료를 직접 조사한 뒤 네이버 블로그 글 작성에 필요한 사실 기반 자료를 JSON으로 정리하라.

반드시 조사할 곳/검색 방향:
- 네이버 검색 결과에 노출되는 네이버 블로그 글
- 네이버 VIEW/블로그 후기
- 네이버 플레이스 또는 지도/맛집 정보
- 구글 검색 결과
- 유튜브 결과가 있으면 확인
- 다이닝코드/망고플레이트 등 맛집 정보가 있으면 확인

검색어 예시:
- "{business_name}"
- "{business_name} 블로그"
- "{business_name} 후기"
- "{business_name} 맛집"
- "{business_name} 네이버 블로그"
- "{business_name} {address}"
- "{business_name} 영통"
- "{business_name} 수원"
- "{business_name} 덕영대로"

가장 중요한 규칙:
- 사용자가 입력한 업체명과 주소에 해당하는 업체만 분석한다.
- 검색 결과에 명확히 있는 내용만 verified_facts에 넣는다.
- 단, verified_facts는 반드시 "본문 사실 근거 사용 가능: True"인 고신뢰 출처에서 확인된 내용만 넣는다.
- 중신뢰/저신뢰 결과는 분위기 참고, 후기 소재 참고만 가능하며 사실 단정 근거로 쓰지 않는다.
- 확실하지 않은 내용은 likely_facts_needing_check에 넣는다.
- 주소, 전화번호, 영업시간, 메뉴, 가격은 출처가 있을 때만 적는다.
- 블로그 후기에서 반복적으로 나오는 포인트를 review_insights에 정리한다.
- 네이버 블로그 본문 소재로 쓸 수 있는 관점을 blog_angles에 정리한다.
- 검색 출처 URL을 source_results에 반드시 넣는다.
- 설명, 마크다운 없이 JSON 객체 하나만 출력한다.

출력 JSON 스키마:
{{
  "summary": "업체에 대한 5~8줄 요약",
  "business_profile": {{
    "official_name": "",
    "address": "",
    "phone": "",
    "website": "",
    "social_channels": [],
    "business_type": "",
    "core_services_or_products": [],
    "operating_hours": "",
    "unique_points": []
  }},
  "verified_facts": ["출처에 의해 확인된 사실"],
  "likely_facts_needing_check": ["확인 필요 정보"],
  "review_insights": ["후기에서 반복적으로 보이는 포인트"],
  "blog_angles": ["블로그에서 잡을 수 있는 글감/관점"],
  "video_points": ["영상/쇼츠/썸네일에 활용할 포인트"],
  "seo_keywords": ["검색 노출에 도움되는 키워드"],
  "source_results": [
    {{"source_type": "네이버 블로그/네이버 플레이스/구글/유튜브/기타", "title": "", "url": "", "memo": ""}}
  ],
  "source_notes": ["어떤 종류의 출처에서 어떤 정보가 나왔는지 요약"],
  "cautions": ["글 작성 시 주의할 점"]
}}

입력 정보:
- 업체명: {business_name}
- 주소: {address}

참고용 로컬 스크래핑 결과:
{local_results[:7000]}
""".strip()


def _fallback_empty_analysis(research_data: dict[str, Any], reason: str = "") -> dict[str, Any]:
    msg = "검색 결과가 충분하지 않습니다. 업체명과 주소를 더 정확히 입력해야 합니다."
    if reason:
        msg += f" 원인: {reason}"
    return {
        "summary": msg,
        "business_profile": {},
        "verified_facts": [],
        "likely_facts_needing_check": [],
        "review_insights": [],
        "blog_angles": [],
        "video_points": [],
        "seo_keywords": [],
        "source_results": [],
        "source_notes": [],
        "cautions": ["검색 결과가 부족하므로 사실 확인이 반드시 필요합니다."],
    }


def analyze_business_research(research_data: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    """Analyze business research.

    v0.3.8 핵심 변경:
    - 기존 로컬 스크래핑 결과만 믿지 않고 OpenAI 웹 검색 도구로 업체명+주소를 다시 검색한다.
    - 웹 검색 도구 사용이 실패하면 기존 로컬 스크래핑 결과 기반 분석으로 fallback한다.
    """
    web_prompt = _build_business_web_search_prompt(research_data)
    try:
        web_result = ask_ai_with_web_search(web_prompt, model=model, temperature=0.2)
        analysis = _extract_json(web_result)
        analysis["research_method"] = "openai_web_search"
        return analysis
    except Exception as web_exc:  # noqa: BLE001
        # Fall back to local scraping results only when the local result quality is acceptable.
        if not research_data.get("results"):
            return _fallback_empty_analysis(research_data, reason=str(web_exc))
        if int(research_data.get("valid_result_count") or 0) < 2:
            return _fallback_empty_analysis(
                research_data,
                reason=f"웹검색 실패 및 로컬 유효 검색결과 부족: {web_exc}",
            )

    prompt = f"""
너는 업체 검색 결과를 분석해서 네이버 블로그 글 작성에 쓸 수 있는 자료만 정리하는 리서치 분석가다.
아래 검색 결과는 사용자가 입력한 업체명과 주소를 기반으로 네이버 검색, 네이버 블로그, 네이버 모바일 검색, 구글, 웹, 유튜브에서 수집한 자료다.

가장 중요한 규칙:
- 사실과 추정, 후기 느낌을 반드시 구분한다.
- 검색 결과에 명확히 있는 내용만 verified_facts에 넣는다.
- 단, verified_facts는 반드시 "본문 사실 근거 사용 가능: True"인 고신뢰 출처에서 확인된 내용만 넣는다.
- 중신뢰/저신뢰 결과는 분위기 참고, 후기 소재 참고만 가능하며 사실 단정 근거로 쓰지 않는다.
- 확실하지 않은 내용은 likely_facts_needing_check에 넣는다.
- 주소, 연락처, 영업시간, 서비스/제품명은 출처에 근거할 때만 적는다.
- 블로그 글의 소재와 독자의 관심 포인트를 뽑는다.
- 결과는 반드시 JSON만 출력한다.
- 한국어로 작성한다.

출력 JSON 스키마:
{{
  "summary": "업체에 대한 5~8줄 요약",
  "business_profile": {{
    "official_name": "",
    "address": "",
    "phone": "",
    "website": "",
    "social_channels": [],
    "business_type": "",
    "core_services_or_products": [],
    "operating_hours": "",
    "unique_points": []
  }},
  "verified_facts": ["출처에 의해 확인된 사실"],
  "likely_facts_needing_check": ["확인 필요 정보"],
  "review_insights": ["후기에서 반복적으로 보이는 포인트"],
  "blog_angles": ["블로그에서 잡을 수 있는 글감/관점"],
  "video_points": ["영상/쇼츠/썸네일에 활용할 포인트"],
  "seo_keywords": ["검색 노출에 도움되는 키워드"],
  "source_results": [
    {{"source_type": "네이버 블로그/네이버 플레이스/구글/유튜브/기타", "title": "", "url": "", "memo": ""}}
  ],
  "source_notes": ["어떤 종류의 출처에서 어떤 정보가 나왔는지 요약"],
  "cautions": ["글 작성 시 주의할 점"]
}}

입력 정보:
- 업체명: {research_data.get('business_name', '')}
- 주소: {research_data.get('address', '')}

검색 자료:
{_research_to_prompt(research_data)}
""".strip()
    analysis = _extract_json(ask_ai(prompt, model=model, temperature=0.2))
    analysis["research_method"] = "local_scraping_fallback"
    return analysis

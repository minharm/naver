from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


@dataclass
class BlogSample:
    url: str
    title: str
    body: str
    tags: list[str]
    image_count: int
    video_count: int

    def to_dict(self) -> dict:
        return asdict(self)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get(url: str, timeout: int = 15) -> str:
    res = requests.get(url, headers=HEADERS, timeout=timeout)
    res.raise_for_status()
    return res.text


def _resolve_naver_frame(url: str, html: str) -> tuple[str, str]:
    """Naver Blog frequently wraps the post in mainFrame iframe."""
    soup = BeautifulSoup(html, "lxml")
    frame = soup.select_one("iframe#mainFrame") or soup.select_one("iframe[name=mainFrame]")
    if frame and frame.get("src"):
        frame_url = urljoin("https://blog.naver.com", frame.get("src"))
        return frame_url, _get(frame_url)
    return url, html


def _extract_title(soup: BeautifulSoup) -> str:
    selectors = [
        ".se-title-text",
        ".se_title .pcol1",
        "h3.se_textarea",
        "h3",
        "title",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            title = _clean_text(node.get_text(" ", strip=True))
            if title:
                return title.replace(": 네이버 블로그", "").strip()
    return "제목 없음"


def _extract_body(soup: BeautifulSoup) -> str:
    # SmartEditor ONE / legacy editor body candidates
    containers = [
        soup.select_one("div.se-main-container"),
        soup.select_one("div#postViewArea"),
        soup.select_one("div.post_ct"),
        soup.select_one("div.entry-content"),
    ]
    for container in containers:
        if container:
            # Remove noisy elements
            for noisy in container.select("script, style, iframe"):
                noisy.decompose()
            text = container.get_text("\n", strip=True)
            text = _clean_text(text)
            if len(text) > 50:
                return text

    # fallback
    text = soup.get_text("\n", strip=True)
    return _clean_text(text)


def _extract_tags(soup: BeautifulSoup) -> list[str]:
    tags: list[str] = []
    for node in soup.select(".wrap_tag a, .post_tag a, a[href*='TagName'], .se-hash-tag"):
        tag = _clean_text(node.get_text(" ", strip=True))
        if tag:
            tag = tag if tag.startswith("#") else f"#{tag}"
            if tag not in tags:
                tags.append(tag)
    return tags[:50]


def crawl_blog_url(url: str) -> BlogSample:
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL은 http:// 또는 https:// 로 시작해야 합니다.")

    html = _get(url)
    final_url, final_html = _resolve_naver_frame(url, html)
    soup = BeautifulSoup(final_html, "lxml")

    title = _extract_title(soup)
    body = _extract_body(soup)
    tags = _extract_tags(soup)
    image_count = len(soup.select("img"))
    video_count = len(soup.select("iframe, video"))

    return BlogSample(
        url=final_url,
        title=title,
        body=body[:12000],
        tags=tags,
        image_count=image_count,
        video_count=video_count,
    )


def crawl_many(urls: list[str]) -> tuple[list[BlogSample], list[dict]]:
    samples: list[BlogSample] = []
    errors: list[dict] = []
    for url in urls:
        clean_url = url.strip()
        if not clean_url:
            continue
        try:
            samples.append(crawl_blog_url(clean_url))
        except Exception as exc:  # noqa: BLE001
            errors.append({"url": clean_url, "error": str(exc)})
    return samples, errors

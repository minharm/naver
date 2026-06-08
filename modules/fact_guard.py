from __future__ import annotations

import re


DIRECT_EXPERIENCE_PATTERNS = [
    r"다녀왔(?:습니다|어요|다|는데|더니)?",
    r"방문했(?:습니다|어요|다|는데)?",
    r"먹어봤(?:습니다|어요|다|는데)?",
    r"주문했(?:습니다|어요|다|는데)?",
    r"저희\s*가족은",
    r"아이들이\s*잘\s*먹",
    r"아이들도\s*잘\s*먹",
    r"직원(?:분)?들?도?\s*친절",
    r"사장님(?:이|도)?\s*친절",
    r"친절했(?:습니다|어요|다)?",
    r"또\s*가고\s*싶",
    r"재방문\s*의사",
    r"다시\s*방문(?:하고|할)\s*의사",
    r"입맛에\s*잘\s*맞",
    r"제\s*입맛에\s*맞",
    r"양이\s*푸짐",
    r"푸짐해서\s*만족",
    r"가격\s*대비[^.\n]{0,16}(?:괜찮|좋)",
    r"웨이팅\s*없이\s*편",
    r"기다림\s*없이\s*편",
    r"주차\s*공간이\s*넉넉",
    r"주차(?:도)?\s*편",
    r"가성비(?:가)?[^.\n]{0,16}좋",
    r"대표\s*메뉴",
    r"맛있(?:었습니다|었어요|다|고)",
    r"만족스러(?:웠습니다|웠어요|웠다)",
]

OBSERVATION_PREFIXES = (
    "사진상으로는",
    "업로드된 사진 기준으로는",
    "메뉴 사진에서 보이는 구성은",
    "검색 자료 기준으로는",
    "공개 자료 기준으로는",
    "확인된 자료 기준으로는",
)


def has_direct_experience_note(user_experience_note: str | None) -> bool:
    note = (user_experience_note or "").strip()
    if not note:
        return False
    empty_markers = ["없음", "없다", "무", "x", "X", "모름", "미입력"]
    return note not in empty_markers and len(note) >= 5


def find_risky_claims(text: str) -> list[str]:
    found: list[str] = []
    for pattern in DIRECT_EXPERIENCE_PATTERNS:
        if re.search(pattern, text or ""):
            found.append(pattern)
    return found


def _line_has_safe_context(line: str) -> bool:
    return any(prefix in line for prefix in OBSERVATION_PREFIXES) or "방문 전 확인" in line or "확인하면 좋" in line


def sanitize_unverified_experience_claims(text: str, user_experience_note: str | None = "") -> tuple[str, list[str]]:
    """Remove or soften risky first-person/experience claims when no direct note exists.

    Important:
    - Safe context phrases such as "사진상으로는" or "검색 자료 기준으로는" do not
      automatically bypass high-risk claims anymore.
    - "사진상으로는 먹음직스러워 보인다" is fine.
    - "사진상으로는 맛있었어요" is still softened because it asserts taste.
    """
    text = text or ""
    if has_direct_experience_note(user_experience_note):
        return text, []

    warnings: list[str] = []
    cleaned_lines: list[str] = []

    replacements = [
        (r"저희\s*가족은", "방문객 입장에서는"),
        (r"아이들이\s*잘\s*먹(?:었습니다|었어요|었다|더라고요|더라구요)?", "아이 동반 방문 시에는 메뉴 구성을 확인해보면 좋겠습니다"),
        (r"아이들도\s*잘\s*먹(?:었습니다|었어요|었다|더라고요|더라구요)?", "아이 동반 방문 시에는 메뉴 구성을 확인해보면 좋겠습니다"),
        (r"직원(?:분)?들?도?\s*친절(?:했습니다|했어요|했다|해서)?", "직원 응대는 실제 방문 후기로 확인하면 좋겠습니다"),
        (r"사장님(?:이|도)?\s*친절(?:했습니다|했어요|했다|해서)?", "응대 관련 부분은 실제 방문 후기로 확인하면 좋겠습니다"),
        (r"친절했(?:습니다|어요|다)?", "응대 관련 부분은 실제 방문 후기로 확인하면 좋겠습니다"),
        (r"또\s*가고\s*싶(?:은|다|네요|었습니다|었어요)?", "재방문 만족도는 실제 방문 후기를 확인하면 좋겠습니다"),
        (r"재방문\s*의사(?:가)?\s*(?:있|있음|있습니다|있어요)", "재방문 의사는 실제 방문 후기를 확인하면 좋겠습니다"),
        (r"다시\s*방문(?:하고|할)\s*의사(?:가)?\s*(?:있|있음|있습니다|있어요)", "재방문 의사는 실제 방문 후기를 확인하면 좋겠습니다"),
        (r"(?:제\s*)?입맛에\s*잘\s*맞(?:았습니다|았어요|다|고)?", "맛에 대한 평가는 실제 방문 후기를 참고하면 좋겠습니다"),
        (r"양이\s*푸짐(?:했습니다|했어요|하다|해서)?", "양과 구성은 메뉴 사진과 실제 주문 시점에 따라 확인이 필요합니다"),
        (r"푸짐해서\s*만족(?:했습니다|했어요|했다)?", "양과 만족도는 실제 방문 후기를 참고하면 좋겠습니다"),
        (r"가격\s*대비[^.\n]{0,16}(?:괜찮|좋)(?:았습니다|았어요|다|은)?", "가격 만족도는 메뉴와 방문 시점에 따라 확인이 필요합니다"),
        (r"웨이팅\s*없이\s*편(?:했습니다|했어요|하다|하게)?", "대기 여부는 방문 시간대에 따라 달라질 수 있어 확인이 필요합니다"),
        (r"기다림\s*없이\s*편(?:했습니다|했어요|하다|하게)?", "대기 여부는 방문 시간대에 따라 달라질 수 있어 확인이 필요합니다"),
        (r"주차\s*공간이\s*넉넉(?:했습니다|했어요|하다|해서)?", "주차 가능 여부는 방문 전 확인하면 좋겠습니다"),
        (r"주차(?:도)?\s*편(?:했습니다|했어요|하다|해서)?", "주차 편의성은 방문 전 확인하면 좋겠습니다"),
        (r"가성비(?:가)?[^.\n]{0,16}좋(?:았습니다|았어요|다|은)?", "가격 만족도는 메뉴와 방문 시점에 따라 확인이 필요합니다"),
        (r"대표\s*메뉴(?:인|는|로)?", "검색 자료에서 자주 언급되는 메뉴로"),
        (r"맛있(?:었습니다|었어요|다|고)", "먹음직스러워 보이고"),
        (r"만족스러(?:웠습니다|웠어요|웠다)", "만족도는 실제 방문 후기를 참고하면 좋겠습니다"),
    ]

    for raw_line in text.splitlines():
        line = raw_line
        original = line

        # Safe context with no risky claim remains untouched.
        if _line_has_safe_context(line) and not find_risky_claims(line):
            cleaned_lines.append(line)
            continue

        # Remove first-person visit/order claims entirely when unsupported.
        # This applies even if the line contains a safe context marker.
        if re.search(r"다녀왔(?:습니다|어요|다|는데|더니)?|방문했(?:습니다|어요|다|는데)?|먹어봤(?:습니다|어요|다|는데)?|주문했(?:습니다|어요|다|는데)?", line):
            warnings.append(original.strip())
            continue

        for pattern, replacement in replacements:
            if re.search(pattern, line):
                line = re.sub(pattern, replacement, line)

        if line != original:
            warnings.append(original.strip())
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, warnings


def assert_no_high_risk_claims_without_note(text: str, user_experience_note: str | None = "") -> bool:
    if has_direct_experience_note(user_experience_note):
        return True
    return not bool(find_risky_claims(text))

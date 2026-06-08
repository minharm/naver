from __future__ import annotations

import re
from typing import Iterable


DIRECT_EXPERIENCE_PATTERNS = [
    r"다녀왔(?:습니다|어요|다|는데|더니)?",
    r"방문했(?:습니다|어요|다|는데)?",
    r"먹어봤(?:습니다|어요|다|는데)?",
    r"주문했(?:습니다|어요|다|는데)?",
    r"저희\s*가족은",
    r"아이들이\s*잘\s*먹",
    r"아이들도\s*잘\s*먹",
    r"직원(?:분)?들?도?\s*친절",
    r"친절했(?:습니다|어요|다)?",
    r"주차\s*공간이\s*넉넉",
    r"주차(?:도)?\s*편",
    r"가성비(?:가)?\s*좋",
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
)


def has_direct_experience_note(user_experience_note: str | None) -> bool:
    note = (user_experience_note or "").strip()
    if not note:
        return False
    empty_markers = ["없음", "없다", "무", "x", "X", "모름"]
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

    This is a deterministic post-generation safety net. It does not try to make
    the writing beautiful; it prevents accidental false reviews such as
    "아이들도 잘 먹었어요" when the user never provided that experience.
    """
    text = text or ""
    if has_direct_experience_note(user_experience_note):
        return text, []

    warnings: list[str] = []
    cleaned_lines: list[str] = []

    replacements = [
        (r"저희\s*가족은", "방문객 입장에서는"),
        (r"아이들이\s*잘\s*먹(?:었습니다|었어요|었다|더라고요|더라구요)?", "아이 동반 방문 시에도 메뉴 구성을 확인해보면 좋겠습니다"),
        (r"아이들도\s*잘\s*먹(?:었습니다|었어요|었다|더라고요|더라구요)?", "아이 동반 방문 시에도 메뉴 구성을 확인해보면 좋겠습니다"),
        (r"직원(?:분)?들?도?\s*친절(?:했습니다|했어요|했다|해서)?", "직원 응대는 방문 전후 실제 후기로 확인하면 좋겠습니다"),
        (r"친절했(?:습니다|어요|다)?", "응대 관련 부분은 실제 방문 후기로 확인하면 좋겠습니다"),
        (r"주차\s*공간이\s*넉넉(?:했습니다|했어요|하다|해서)?", "주차 가능 여부는 방문 전 확인하면 좋겠습니다"),
        (r"주차(?:도)?\s*편(?:했습니다|했어요|하다|해서)?", "주차 편의성은 방문 전 확인하면 좋겠습니다"),
        (r"가성비(?:가)?\s*좋(?:았습니다|았어요|다|은)?", "가격 만족도는 메뉴와 방문 시점에 따라 확인이 필요합니다"),
        (r"대표\s*메뉴(?:인|는|로)?", "검색 자료에서 자주 언급되는 메뉴로"),
        (r"맛있(?:었습니다|었어요|다|고)", "사진상으로는 먹음직스러워 보이고"),
        (r"만족스러(?:웠습니다|웠어요|웠다)", "만족도는 실제 방문 후기를 참고하면 좋겠습니다"),
    ]

    for raw_line in text.splitlines():
        line = raw_line
        if _line_has_safe_context(line):
            cleaned_lines.append(line)
            continue

        original = line
        # Remove first-person visit/order claims entirely when they are not supported.
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

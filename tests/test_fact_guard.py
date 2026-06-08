import sys
import types

fake_openai = types.ModuleType("openai")
fake_openai.OpenAI = object
sys.modules.setdefault("openai", fake_openai)

from modules.fact_guard import (
    assert_no_high_risk_claims_without_note,
    find_risky_claims,
    sanitize_unverified_experience_claims,
)


def test_fact_guard_removes_direct_visit_without_note():
    text = "후이후이에 다녀왔어요.\n아이들도 잘 먹었고 직원분들도 친절했어요."
    cleaned, warnings = sanitize_unverified_experience_claims(text, user_experience_note="")
    assert "다녀왔" not in cleaned
    assert "아이들도 잘 먹" not in cleaned
    assert "직원분들도 친절" not in cleaned
    assert warnings


def test_fact_guard_allows_when_direct_note_exists():
    text = "후이후이에 다녀왔어요.\n아이들도 잘 먹었어요."
    cleaned, warnings = sanitize_unverified_experience_claims(text, user_experience_note="직접 방문했고 아이들이 짜장면을 잘 먹음")
    assert cleaned == text
    assert warnings == []


def test_high_risk_detector():
    text = "주차 공간이 넉넉하고 가성비가 좋았어요."
    assert find_risky_claims(text)
    cleaned, warnings = sanitize_unverified_experience_claims(text, "")
    assert assert_no_high_risk_claims_without_note(cleaned, "")

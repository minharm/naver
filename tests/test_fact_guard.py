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


def test_fact_guard_expanded_risky_phrases_without_note():
    text = "\n".join([
        "또 가고 싶은 곳이에요.",
        "재방문 의사 있음.",
        "입맛에 잘 맞았어요.",
        "사장님이 친절했어요.",
        "양이 푸짐해서 만족했어요.",
        "가격 대비 괜찮았어요.",
        "웨이팅 없이 편하게 먹었어요.",
    ])
    cleaned, warnings = sanitize_unverified_experience_claims(text, user_experience_note="")
    assert warnings
    assert "또 가고 싶은" not in cleaned
    assert "재방문 의사 있음" not in cleaned
    assert "입맛에 잘 맞" not in cleaned
    assert "사장님이 친절" not in cleaned
    assert "푸짐해서 만족" not in cleaned
    assert "가격 대비 괜찮" not in cleaned
    assert "웨이팅 없이 편" not in cleaned


def test_fact_guard_does_not_overdelete_with_experience_note():
    text = "사장님이 친절했고 양이 푸짐해서 만족했어요. 재방문 의사 있음."
    cleaned, warnings = sanitize_unverified_experience_claims(
        text,
        user_experience_note="직접 방문했고 사장님 응대와 양에 만족함",
    )
    assert cleaned == text
    assert warnings == []

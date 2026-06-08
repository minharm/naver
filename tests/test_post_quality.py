from modules.post_quality import evaluate_blog_post, quality_report_to_markdown


def test_quality_report_flags_risky_claim_without_experience_note():
    report = evaluate_blog_post(
        title_block="1. 후이후이 후기",
        body="후이후이에 다녀왔어요.\n\n직원분들도 친절했고 맛있었어요.",
        tags="#후이후이 #영통맛집",
        business_analysis={"source_results": []},
        business_research={"valid_result_count": 0, "average_quality_score": 0},
        images=[],
        videos=[],
        user_experience_note="",
    )
    assert report["scores"]["safety"] < 100
    assert report["risky_lines"]
    assert report["warnings"]


def test_quality_report_allows_experience_note():
    report = evaluate_blog_post(
        title_block="1. 후이후이 후기",
        body="후이후이에 다녀왔어요.\n\n직원분들도 친절했고 맛있었어요.",
        tags="#후이후이 #영통맛집 #수원중국집",
        business_analysis={"source_results": [{"title": "a"}, {"title": "b"}], "verified_facts": ["주소 확인"]},
        business_research={"valid_result_count": 2, "average_quality_score": 60, "fact_usable_result_count": 1},
        images=[],
        videos=[],
        user_experience_note="직접 방문했고 직원 응대와 맛이 좋았음",
    )
    assert report["scores"]["safety"] >= 90


def test_quality_report_penalizes_missing_photo_placeholders():
    report = evaluate_blog_post(
        title_block="1. 테스트",
        body="본문입니다.\n\n사진 설명이 없습니다.",
        tags="#테스트 #블로그 #업로드",
        business_analysis={"source_results": [{"title": "a"}]},
        business_research={"valid_result_count": 1, "average_quality_score": 50},
        images=[{"filename": "a.jpg"}],
        videos=[],
        user_experience_note="",
    )
    assert any("사진 삽입 위치" in warning for warning in report["warnings"])


def test_quality_report_to_markdown_contains_scores():
    report = evaluate_blog_post(
        title_block="1. 테스트",
        body="본문입니다.\n\n[사진 1 삽입]\n\n마무리입니다.",
        tags="#테스트 #블로그 #업로드",
        business_analysis={"source_results": [{"title": "a"}]},
        business_research={"valid_result_count": 1, "average_quality_score": 50},
        images=[{"filename": "a.jpg"}],
        videos=[],
        user_experience_note="",
    )
    md = quality_report_to_markdown(report)
    assert "최종 글 품질 평가" in md
    assert "사실성" in md

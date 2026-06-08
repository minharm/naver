from modules.cost_control import (
    compact_research_analysis,
    compact_style_profile,
    get_cost_settings,
    make_metadata_only_image_analysis,
    select_research_sources_for_prompt,
)


def test_token_save_settings_defaults():
    settings = get_cost_settings(True)
    assert settings["token_save_mode"] is True
    assert settings["max_research_sources_for_generation"] <= 5
    assert settings["max_image_analysis"] <= 6


def test_select_research_sources_prefers_high_trust_and_trims():
    sources = [
        {"title": "low", "trust_tier": "low", "quality_score": 30, "snippet": "x" * 1000},
        {"title": "high", "trust_tier": "high", "quality_score": 80, "snippet": "y" * 1000},
        {"title": "medium", "trust_tier": "medium", "quality_score": 55, "snippet": "z" * 1000},
    ]
    selected = select_research_sources_for_prompt(sources, max_sources=2, max_excerpt_chars=50)
    assert [x["title"] for x in selected] == ["high", "medium"]
    assert len(selected[0]["snippet"]) <= 53


def test_compact_style_profile_limits_large_values():
    profile = {
        "tone": "친근함" * 1000,
        "common_phrases": [str(i) * 100 for i in range(10)],
    }
    compact = compact_style_profile(profile, max_items=3, max_text_chars=50)
    assert compact["_compact_profile"] is True
    assert len(compact["tone"]) <= 53
    assert len(compact["common_phrases"]) == 3


def test_compact_research_analysis_keeps_core_keys():
    analysis = {
        "business_profile": {"address": "주소" * 200},
        "verified_facts": [f"fact {i}" for i in range(20)],
        "source_results": [{"title": str(i)} for i in range(20)],
        "unused": "x" * 1000,
    }
    compact = compact_research_analysis(analysis, max_list_items=5, max_text_chars=100)
    assert "unused" not in compact
    assert len(compact["verified_facts"]) == 5
    assert len(compact["source_results"]) == 5


def test_metadata_only_image_analysis_marks_skip():
    item = make_metadata_only_image_analysis("a.jpg", "메뉴판 사진")
    assert item["analysis_skipped"] is True
    assert "메뉴판" in item["blog_caption"]

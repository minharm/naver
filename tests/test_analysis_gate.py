from modules.analysis_gate import business_analysis_warning, has_reliable_business_sources


def test_business_analysis_warning_when_source_results_missing():
    warning = business_analysis_warning(
        {"summary": "분석은 있으나 출처 없음", "source_results": []},
        {"valid_result_count": 0, "average_quality_score": 0},
    )
    assert "출처가 부족" in warning


def test_business_analysis_reliable_with_source_results():
    assert has_reliable_business_sources(
        {"source_results": [{"title": "a"}, {"title": "b"}]},
        {"valid_result_count": 0, "average_quality_score": 0},
    )


def test_business_analysis_warning_when_no_high_trust_fact_source():
    warning = business_analysis_warning(
        {"summary": "분석 있음", "source_results": []},
        {"valid_result_count": 2, "fact_usable_result_count": 0, "average_quality_score": 35},
    )
    assert "고신뢰 출처" in warning

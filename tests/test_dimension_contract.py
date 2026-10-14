from datetime import datetime, timezone

from engines.base import PredictionResult


def test_unavailable_dimension_has_no_score_or_weight():
    result = PredictionResult.unavailable(
        dimension_name="新闻舆情",
        dimension_key="sentiment",
        source_name="东方财富红枣资讯",
        source_url="https://futures.eastmoney.com/a/acj.html",
        reason="上游超时",
    )

    assert result.data_status == "UNAVAILABLE"
    assert result.score is None
    assert result.confidence is None
    assert result.included_in_score is False
    assert result.weight == 0.0


def test_cultural_reference_is_explicitly_excluded_from_score():
    observed_at = datetime(2026, 10, 14, 11, 0, tzinfo=timezone.utc)
    result = PredictionResult.reference(
        dimension_name="易经文化参考",
        dimension_key="iching",
        summary="基于真实时间动态计算",
        recommendation="仅作文化参考",
        observed_at=observed_at,
        key_metrics={"四柱": "丙午 戊戌"},
    )

    assert result.category == "CULTURAL_REFERENCE"
    assert result.data_status == "REFERENCE"
    assert result.score is None
    assert result.included_in_score is False
    assert result.weight == 0.0
    assert result.observed_at == observed_at

from datetime import datetime, timezone

from data.data_feed import KLineBar
from data.history_manager import HistoryManager


def test_save_cache_is_complete_and_leaves_no_temporary_files(tmp_path):
    manager = HistoryManager(cache_dir=tmp_path)
    bars = [
        KLineBar(
            timestamp=datetime(2026, 10, 15, tzinfo=timezone.utc),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1200,
            open_interest=800,
        )
    ]

    manager.save_cache("CJ0", bars, rejected_bars=2)

    metadata = manager.get_metadata("CJ0")
    loaded = manager.get_historical_bars("CJ0")
    assert metadata["validation_rejected_bars"] == 2
    assert loaded == bars
    assert (tmp_path / "CJ0_daily.csv").exists()
    assert not list(tmp_path.glob("*.tmp"))

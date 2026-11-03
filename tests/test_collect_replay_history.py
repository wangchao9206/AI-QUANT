from dataclasses import replace
from datetime import date, datetime

import pytest

from data.data_feed import KLineBar
from data.live_feed import SHANGHAI
from data.tqsdk_backtest import (
    FuturesContractSpec, IncompleteDeliveryData, IncompleteRollData, TqSdkBacktestDataset, TqSdkBacktestDataProvider,
    TqSdkBacktestUnavailable,
)
from scripts import collect_replay_history as collection


def dataset(days):
    bars = [KLineBar(datetime.fromisoformat(day).replace(tzinfo=SHANGHAI),
                     100, 110, 90, 105, 1000, 100, 'AG2412') for day in days]
    return TqSdkBacktestDataset(
        'AG0', 'KQ.m@SHFE.ag', 'TQSDK_REAL_DOMINANT_DAILY', datetime.now(SHANGHAI),
        bars, [], {'AG2412': FuturesContractSpec('AG2412', 15, 1, 1000, 3)},
        signal_bars=bars,
    )


@pytest.fixture
def archives(tmp_path, monkeypatch):
    monkeypatch.setenv('HISTORY_CACHE_DIR', str(tmp_path))
    provider = TqSdkBacktestDataProvider()
    old = dataset(['2024-04-25', '2024-04-26'])
    provider._write_cache(provider._cache_path('AG0'), old, 600)
    return provider, old


def test_upgrades_existing_short_archive_instead_of_skipping_it(archives, monkeypatch):
    provider, old = archives
    full = dataset(['2012-05-10', '2024-04-25', '2024-04-26'])
    calls = []

    def download(self, symbol, provider_symbol, n, force_download):
        calls.append((symbol, provider_symbol, n, force_download))
        self._write_cache(self._cache_path(symbol), full, n)
        return full

    monkeypatch.setattr(TqSdkBacktestDataProvider, 'load', download)
    result = collection.collect_symbol('AG0', 10000)
    assert calls == [('AG0', 'KQ.m@SHFE.ag', 10000, True)]
    assert result['status'] == 'READY' and result['startDate'] == '2012-05-10'
    assert provider._read_cache(provider._cache_path('AG0'), 10000).bars == full.bars


@pytest.mark.parametrize('replacement', [
    dataset(['2024-04-26', '2024-04-29']),
    dataset(['2012-05-10', '2024-04-25']),
    dataset(['2012-05-10', '2024-04-26']),
])
def test_shorter_or_gapped_download_preserves_original(archives, monkeypatch, replacement):
    provider, old = archives
    path = provider._cache_path('AG0')
    original = path.read_bytes()

    def download(self, symbol, *args, **kwargs):
        self._write_cache(self._cache_path(symbol), replacement, 10000)

    monkeypatch.setattr(TqSdkBacktestDataProvider, 'load', download)
    assert collection.collect_symbol('AG0', 10000)['status'] == 'PRESERVED'
    assert path.read_bytes() == original


@pytest.mark.parametrize('failure', ['network', 'validation'])
def test_failed_collection_preserves_original(archives, monkeypatch, failure):
    provider, old = archives
    path = provider._cache_path('AG0')
    original = path.read_bytes()

    def download(self, symbol, *args, **kwargs):
        if failure == 'network':
            raise TqSdkBacktestUnavailable('unavailable')
        self._write_cache(self._cache_path(symbol), replace(old, complete=False), 10000)

    monkeypatch.setattr(TqSdkBacktestDataProvider, 'load', download)
    with pytest.raises((TqSdkBacktestUnavailable, ValueError)):
        collection.collect_symbol('AG0', 10000)
    assert path.read_bytes() == original


def test_current_full_depth_archive_can_be_reused(archives, monkeypatch):
    provider, old = archives
    provider._write_cache(provider._cache_path('AG0'), old, 10000)
    monkeypatch.setattr(TqSdkBacktestDataProvider, 'load', lambda *a, **k: pytest.fail('must reuse current full archive'))
    assert collection.collect_symbol('AG0', 10000)['status'] == 'EXISTING'


def test_missing_early_rolls_publish_an_explicit_window_without_claiming_full_history(archives, monkeypatch):
    provider, old = archives
    original = provider._cache_path('AG0').read_bytes()
    suffix = dataset(['2018-01-02', '2024-04-25', '2024-04-26'])
    calls = []

    def download(self, symbol, provider_symbol, n, force_download, start_date=None):
        calls.append(start_date)
        if start_date is None:
            raise IncompleteRollData('missing legs', missing_dates=[date(2016, 1, 18), date(2018, 1, 2)])
        self._write_cache(self._cache_path(symbol, start_date), suffix, n)

    monkeypatch.setattr(TqSdkBacktestDataProvider, 'load', download)
    result = collection.collect_symbol('AG0', 10000)
    assert calls == [None, date(2018, 1, 2)]
    assert result['status'] == 'READY_WITH_GAPS'
    assert result['missingRollDates'] == ['2016-01-18', '2018-01-02']
    assert result['startDate'] == '2018-01-02'
    assert provider._cache_path('AG0').read_bytes() == original
    assert provider.cached_replay('AG0').bars == suffix.bars


def test_missing_execution_day_starts_suffix_after_the_gap(archives, monkeypatch):
    provider, old = archives
    suffix = dataset(['2018-01-03', '2024-04-25', '2024-04-26'])
    calls = []

    def download(self, symbol, provider_symbol, n, force_download, start_date=None):
        calls.append(start_date)
        if start_date is None:
            raise IncompleteDeliveryData('missing execution', [date(2018, 1, 2)], [date(2017, 1, 2)])
        self._write_cache(self._cache_path(symbol, start_date), suffix, n)

    monkeypatch.setattr(TqSdkBacktestDataProvider, 'load', download)
    result = collection.collect_symbol('AG0', 10000)
    assert calls == [None, date(2018, 1, 3)]
    assert result['status'] == 'READY_WITH_GAPS'
    assert result['missingDeliveryDates'] == ['2018-01-02']
    assert result['startDate'] == '2018-01-03'

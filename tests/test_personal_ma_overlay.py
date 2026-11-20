from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backtesting import personal_ma_overlay
from data.data_feed import KLineBar


def sample_bars(count=40):
    origin = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [KLineBar(origin + timedelta(days=i), 105, 108, 102, 105, 100, 0, 'X01')
            for i in range(count)]


def confirmation(index, direction, level, breakout=None):
    return {'confirmedIndex': index, 'direction': direction, 'invalidation': level, 'zoneId': breakout}


def substitute_detect(monkeypatch, *, chan=(), retests=()):
    def detect(bars, family):
        events = {'RANGE_RETEST': retests, 'CHAN_PEN_T3': chan}[family]
        return {'events': [event for event in events if event['confirmedIndex'] < len(bars)]}

    monkeypatch.setattr(personal_ma_overlay, 'detect', detect)


def test_wyckoff_mirrors_close_location_and_only_publishes_after_retest(monkeypatch):
    bars = sample_bars()
    bars[22] = replace(bars[22], high=110, low=100, close=108, volume=160)
    bars[28] = replace(bars[28], high=110, low=100, close=101, volume=160)
    substitute_detect(monkeypatch, retests=(confirmation(24, 1, 100, 22), confirmation(30, -1, 110, 28)))
    states = personal_ma_overlay.overlay_tape(bars, bars)
    assert states[22]['wyckoff'] == 0
    assert states[23]['wyckoff'] == 0
    assert states[24]['wyckoff'] == 1
    assert states[28]['wyckoff'] == 0
    assert states[29]['wyckoff'] == 0
    assert states[30]['wyckoff'] == -1
    assert states[:29] == personal_ma_overlay.overlay_tape(bars[:29], bars[:29])


def test_retest_crossing_actual_contract_roll_uses_no_stale_volume(monkeypatch):
    bars = sample_bars()
    bars[22] = replace(bars[22], high=110, low=100, close=108, volume=160)
    substitute_detect(monkeypatch, retests=(confirmation(24, 1, 100, 22),))
    assert personal_ma_overlay.overlay_tape(bars, bars)[24]['wyckoff'] == 1
    raw_bars = [replace(bar, contract_symbol='X02') if i >= 24 else bar for i, bar in enumerate(bars)]
    assert personal_ma_overlay.overlay_tape(bars, raw_bars)[24]['wyckoff'] == 0
    raw_bars = [replace(bar, contract_symbol='X00') if i < 4 else bar for i, bar in enumerate(bars)]
    assert personal_ma_overlay.overlay_tape(bars, raw_bars)[24]['wyckoff'] == 0


def test_chan_resets_on_boundary_touch_expiry_or_roll(monkeypatch):
    bars = sample_bars()
    bars[6] = replace(bars[6], low=101)
    chan = (confirmation(4, 1, 101), confirmation(8, -1, 109), confirmation(15, 1, 101))
    substitute_detect(monkeypatch, chan=chan)
    raw = [replace(bar, open=50, high=52, low=49, close=51, contract_symbol='X02' if i >= 16 else 'X01')
           for i, bar in enumerate(bars)]
    states = personal_ma_overlay.overlay_tape(bars, raw, validity_bars=3)
    assert states[4]['chan'] == 1
    assert states[5]['chan'] == 1
    assert states[6]['chan'] == 0
    assert states[11]['chan'] == -1
    assert states[11]['chanConfirmedIndex'] == 8
    assert states[12]['chan'] == 0
    assert states[15]['chan'] == 1
    assert states[16]['chan'] == 0

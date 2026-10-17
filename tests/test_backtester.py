from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backtesting.backtester import FuturesExecutionLedger, QuantitativeBacktester
from data.data_feed import KLineBar
from data.tqsdk_backtest import FuturesContractSpec, RollEvent


def make_bars(count: int = 30) -> list[KLineBar]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars = []
    for idx in range(count):
        open_price = 100.0 + idx
        if idx == 21:
            open_price = 150.0
        close = open_price + 1.0
        bars.append(
            KLineBar(
                timestamp=start + timedelta(days=idx),
                open=open_price,
                high=close + 1.0,
                low=open_price - 1.0,
                close=close,
                volume=1000 + idx,
                open_interest=500,
            )
        )
    return bars


def test_close_signal_fills_at_next_bar_open():
    result = QuantitativeBacktester().run_backtest(
        make_bars(),
        strategy="BUY_AND_HOLD",
        slippage=1.0,
    )

    opening_trade = next(trade for trade in result.trade_logs if trade.action == "OPEN_BUY")
    assert opening_trade.timestamp == make_bars()[21].timestamp
    assert opening_trade.price == 151.0


def test_final_equity_matches_last_curve_point():
    result = QuantitativeBacktester().run_backtest(
        make_bars(),
        strategy="BUY_AND_HOLD",
        slippage=1.0,
    )

    assert result.daily_equity[-1]["equity"] == result.final_equity
    assert result.daily_equity[-1]["positionPct"] == 0.0


def test_synthetic_roll_model_is_disabled_without_real_roll_events():
    result = QuantitativeBacktester().run_backtest(
        make_bars(100),
        strategy="BUY_AND_HOLD",
        include_roll_cost=True,
    )

    assert result.include_roll_cost is False
    assert result.roll_trades == 0
    assert result.total_roll_yield_pct == 0.0


def test_execution_ledger_uses_integer_lots_tick_slippage_and_real_margin():
    ledger = FuturesExecutionLedger(initial_cash=100_000)
    spec = FuturesContractSpec(
        contract="CJ701",
        volume_multiple=5,
        price_tick=5,
        margin_per_lot=6500,
        commission_per_lot=3,
    )

    fill = ledger.open_position(
        direction=1,
        contract="CJ701",
        market_price=8000,
        spec=spec,
        margin_rate=0.12,
        margin_budget_ratio=0.30,
        target_leverage=2.0,
        slippage_ticks=1,
        fee_rate=0.0,
    )

    assert fill.price == 8005
    assert fill.lots == 4  # floor(30,000 / 6,500), never a fractional contract
    assert fill.fee == 12
    assert ledger.cash == 99_988
    assert ledger.margin_occupied(8005, spec, 0.12) == 26_000


def test_real_roll_resets_basis_without_booking_the_contract_price_gap_as_profit():
    bars = []
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for idx in range(35):
        rolled = idx >= 22
        price = 120.0 if rolled else 100.0
        bars.append(KLineBar(
            timestamp=start + timedelta(days=idx),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000,
            open_interest=500,
            contract_symbol="CJ701" if rolled else "CJ609",
        ))

    roll_date = bars[22].timestamp.date()
    specs = {
        "CJ609": FuturesContractSpec("CJ609", 5, 1, 100, 3),
        "CJ701": FuturesContractSpec("CJ701", 5, 1, 100, 3),
    }
    event = RollEvent(
        execution_date=roll_date,
        from_contract="CJ609",
        to_contract="CJ701",
        old_open=100,
        new_open=120,
        price_gap=20,
        price_gap_pct=20,
    )

    result = QuantitativeBacktester(initial_capital=100_000).run_backtest(
        bars,
        strategy="BUY_AND_HOLD",
        fee_rate=0,
        slippage=0,
        max_pos_ratio=0.10,
        margin_rate=0.10,
        leverage=1.0,
        include_roll_cost=True,
        roll_events=[event],
        contract_specs=specs,
    )

    # The old leg opens with 100 lots. After actual fees reduce available cash,
    # the margin cap only permits 99 new-contract lots at the roll.
    # The 20-point gap is not cash PnL because a futures roll exchanges one
    # cost basis for another rather than buying the new contract's notional.
    assert result.final_equity == pytest.approx(98_806)
    assert result.roll_trades == 1
    assert result.roll_cost_total == pytest.approx(597)
    assert result.total_roll_yield_pct == 0.0
    assert result.roll_price_gap_total == pytest.approx(9_900)
    assert result.benchmark_return_pct == pytest.approx(0.0)
    assert result.include_roll_cost is True
    roll = next(trade for trade in result.trade_logs if trade.action == "ROLL_LONG")
    assert roll.from_contract == "CJ609"
    assert roll.to_contract == "CJ701"
    assert roll.lots == 99
    assert roll.old_price == 100
    assert roll.new_price == 120


def test_missing_real_roll_event_never_activates_roll_accounting():
    bars = make_bars(100)
    for bar in bars:
        bar.contract_symbol = "CJ701"
    specs = {"CJ701": FuturesContractSpec("CJ701", 5, 5, 6500, 3)}

    result = QuantitativeBacktester().run_backtest(
        bars,
        strategy="BUY_AND_HOLD",
        include_roll_cost=True,
        contract_specs=specs,
    )

    assert result.include_roll_cost is False
    assert result.roll_model_status == "NO_OBSERVED_ROLL_EVENTS"


def test_execution_equity_and_benchmark_do_not_use_signal_prices():
    bars = [replace(b, open=100, high=100, low=100, close=100, contract_symbol='CJ701')
            for b in make_bars(35)]
    signals = [replace(b, open=1000, high=1000, low=1000, close=1000, contract_symbol=None) for b in bars]
    result = QuantitativeBacktester().run_backtest(
        bars, strategy='BUY_AND_HOLD', signal_klines=signals, fee_rate=0, slippage=0,
        contract_specs={'CJ701': FuturesContractSpec('CJ701', 5, 5, 100, 0)})
    assert result.trade_logs[0].price == 100
    assert result.final_equity == 1_000_000
    assert result.benchmark_return_pct == 0


@pytest.mark.parametrize('direction', [1, -1])
def test_new_position_checks_initial_stop_on_its_opening_day(direction):
    bars = []
    for i, b in enumerate(make_bars(70)):
        price = 100 + direction * i
        bars.append(replace(b, open=price, close=price, high=price+1, low=price-1))
    # The first signal is at index 60; the opening-day range crosses 2 ATR.
    bars[61] = replace(bars[61], low=bars[61].open-10, high=bars[61].open+10)
    bt = QuantitativeBacktester()
    bt.engine = SimpleNamespace(evaluate_all=lambda ctx: SimpleNamespace(
        composite_score=50*direction, directional_resonance=1.0))
    result = bt.run_backtest(bars, slippage=0, fee_rate=0, leverage=1)
    opening = result.trade_logs[0]
    closing = result.trade_logs[1]
    assert opening.action == ('OPEN_BUY' if direction > 0 else 'OPEN_SHORT')
    assert closing.action == ('FLATTEN_LONG' if direction > 0 else 'FLATTEN_SHORT')
    assert closing.timestamp == opening.timestamp == bars[61].timestamp
    assert closing.hold_bars == 0
    assert closing.pnl < 0


def test_misaligned_signal_dates_are_rejected():
    bars = make_bars()
    with pytest.raises(ValueError, match='identical timestamps'):
        QuantitativeBacktester().run_backtest(bars, signal_klines=bars[1:])


def test_old_contract_intraday_range_cannot_stop_new_roll_position():
    bars = [replace(b, open=100+i+(20 if i>=62 else 0), close=100+i+(20 if i>=62 else 0),
                    high=101+i+(20 if i>=62 else 0), low=99+i+(20 if i>=62 else 0),
                    contract_symbol='CJ701' if i>=62 else 'CJ609') for i,b in enumerate(make_bars(70))]
    event = RollEvent(bars[62].timestamp.date(), 'CJ609', 'CJ701', 162, 182, 20, 20/162*100,
                      old_high=1000, old_low=1, new_high=183, new_low=181)
    bt = QuantitativeBacktester()
    bt.engine = SimpleNamespace(evaluate_all=lambda ctx: SimpleNamespace(composite_score=50, directional_resonance=1))
    result = bt.run_backtest(bars, slippage=0, fee_rate=0, leverage=1, include_roll_cost=True,
        roll_events=[event], contract_specs={k:FuturesContractSpec(k,5,1,100,0) for k in ['CJ609','CJ701']})
    assert any(t.action == 'ROLL_LONG' and t.timestamp == bars[62].timestamp for t in result.trade_logs)
    assert not any('FLATTEN' in t.action and t.timestamp == bars[62].timestamp for t in result.trade_logs)


def test_previous_close_exit_executes_before_next_days_intraday_stop():
    bars = [replace(b, open=100+i, close=100+i, high=101+i, low=99+i) for i,b in enumerate(make_bars(70))]
    bars[62] = replace(bars[62], low=1)
    bt = QuantitativeBacktester()
    bt.engine = SimpleNamespace(evaluate_all=lambda ctx: SimpleNamespace(
        composite_score=50 if ctx['quote'].timestamp <= bars[60].timestamp else -50,
        directional_resonance=1))
    result = bt.run_backtest(bars, slippage=0, fee_rate=0, leverage=1)
    assert result.trade_logs[1].action == 'FLATTEN_LONG'
    assert result.trade_logs[1].timestamp == bars[62].timestamp
    assert result.trade_logs[1].price == bars[62].open

from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from data.data_feed import KLineBar
from backtesting.trend_validation import event

def data():
    start=datetime(2024,1,1,tzinfo=timezone.utc)
    bars=[KLineBar(start+timedelta(days=i),100,101,99,100,1000,1000,'X') for i in range(40)]
    spec=SimpleNamespace(volume_multiple=10,price_tick=.1,commission_per_lot=1)
    return SimpleNamespace(bars=bars,roll_events=[],contract_specs={'X':spec})

def test_entry_is_next_open_and_both_touched_bar_uses_stop_first():
    ds=data();ds.bars[25]=KLineBar(ds.bars[25].timestamp,100,110,95,103,1000,1000,'X')
    r=event(ds,24,1,'ATR2_TARGET4',39)
    assert r['entryIndex']==25 and r['exitReason']=='STOP' and r['exit']==96
    assert r['netPct']<r['grossPct'] and r['stressNetPct']<r['netPct']

def test_gap_loss_is_not_capped_to_stop_and_roll_uses_old_open():
    ds=data();ds.bars[26]=KLineBar(ds.bars[26].timestamp,90,91,89,90,1000,1000,'X')
    assert event(ds,24,1,'ATR2_TARGET4',39)['exit']==90
    ds=data();ds.bars[26]=KLineBar(ds.bars[26].timestamp,200,201,199,200,1000,1000,'Y')
    ds.roll_events=[SimpleNamespace(execution_date=ds.bars[26].timestamp.date(),from_contract='X',old_open=99)]
    r=event(ds,24,1,'FIXED_10',39)
    assert r['exit']==99 and r['exitReason']=='ROLL_OPEN'

def test_zero_volume_refuses_execution_and_ma_exit_waits_for_next_open():
    ds=data();ds.bars[25]=KLineBar(ds.bars[25].timestamp,100,101,99,100,0,1000,'X')
    assert event(ds,24,1,'FIXED_1',39) is None
    ds=data();ds.bars[25]=KLineBar(ds.bars[25].timestamp,100,101,97,98,1000,1000,'X')
    ds.bars[26]=KLineBar(ds.bars[26].timestamp,97,98,96,97,1000,1000,'X')
    r=event(ds,24,1,'MA5_NEXT_OPEN',39)
    assert r['exitIndex']==26 and r['exit']==97 and r['exitReason']=='MA5_NEXT_OPEN'

from datetime import date,datetime,timedelta
import math

import numpy as np
import pandas as pd
import pytest

from scripts.fg701_daily_macd import daily_macd,bind_daily_filter,verify_daily_overlap,current_contract_daily
from scripts.backtest_fg701_intraday import SH,summarize
from scripts.backtest_fg701_ma20_macd import simulate_macd_filtered,verify
from tests.test_fg701_intraday import bar,end,mirror


def daily(closes,start=date(2026,1,1)):
    return [{'id':i,'datetime':int(datetime.combine(start+timedelta(days=i),datetime.min.time(),SH).timestamp()*1e9),
             'close':c,'open':c,'high':c,'low':c,'volume':100} for i,c in enumerate(closes)]


def gated(rows,side=1):
    output=[]
    for b in rows:
        prev=(date.fromisoformat(b['tradingDay'])-timedelta(days=1)).isoformat()
        output.append({**b,'allowedSide':side,'dailySourceDay':prev,'dailyDIF':-1 if side==1 else -3,
                       'dailyDEA':-2,'dailyMACD':2 if side==1 else -2,'dailyAvailableAt':prev+'T15:00:00+08:00'})
    return output


def checked(rows,**kwargs):
    trades,curve,events,rejected=simulate_macd_filtered(rows,**kwargs)
    verify(trades,curve,events,summarize(trades,curve))
    return trades,curve,events,rejected


def test_macd_matches_independent_pandas_recursive_ema():
    closes=[100+math.sin(i/6)*12+i*.1 for i in range(200)]
    result=daily_macd(daily(closes))
    prices=pd.Series(closes)
    dif=prices.ewm(span=12,adjust=False).mean()-prices.ewm(span=26,adjust=False).mean()
    dea=dif.ewm(span=9,adjust=False).mean()
    assert np.allclose([r['dif'] for r in result],dif,rtol=0,atol=1e-12)
    assert np.allclose([r['dea'] for r in result],dea,rtol=0,atol=1e-12)
    assert np.allclose([r['histogram'] for r in result],2*(dif-dea),rtol=0,atol=2e-12)


def test_constant_prices_and_unwarmed_history_open_neither_direction():
    result=daily_macd(daily([100]*60))
    assert all(r['dif']==r['dea']==r['histogram']==0 and r['allowedSide']==0 for r in result)
    assert not result[33]['ready'] and result[34]['ready']
    rising=daily_macd(daily(list(range(100,160))))
    assert all(r['allowedSide']==0 for r in rising[:34])
    assert rising[34]['allowedSide']==1


def test_both_actual_crossovers_and_negative_dif_golden_direction():
    closes=[150-i*.4 for i in range(80)]+[118+i*.8 for i in range(40)]+[150-i for i in range(40)]
    result=daily_macd(daily(closes))
    assert any(r['cross']==1 for r in result) and any(r['cross']==-1 for r in result)
    assert any(r['dif']<0 and r['allowedSide']==1 for r in result)
    last=None
    for r in result:
        if r['cross']:
            last=r['date']
        assert r['lastCrossDate']==last


def test_prefix_macd_is_unchanged_by_future_or_current_daily_prices():
    raw=daily([100+i%13 for i in range(100)])
    a=daily_macd(raw[:70])
    modified=raw[:70]+[{**r,'close':99999} for r in raw[70:]]
    assert daily_macd(raw)[:70]==a==daily_macd(modified)[:70]


def test_listing_seed_and_contiguous_daily_ids_are_required():
    raw=daily([100]*50)
    with pytest.raises(ValueError,match='listing'):
        daily_macd(raw[1:])
    changed=[dict(r) for r in raw];changed[20]['id']=22
    with pytest.raises(ValueError,match='contiguous'):
        daily_macd(changed)


def test_friday_night_belonging_to_monday_uses_friday_closed_daily():
    raw=daily([100+i*.1 for i in range(60)],start=date(2026,9,1))
    raw=[r for r in raw if datetime.fromtimestamp(r['datetime']/1e9,SH).weekday()<5]
    for i,r in enumerate(raw):r['id']=i
    macd=daily_macd(raw)
    rows=[bar(0,110,day='2026-10-19')]
    rows[0]['timestamp']=datetime(2026,10,16,21,tzinfo=SH)
    cld=[{'date':'2026-10-16','trading':True},{'date':'2026-10-17','trading':False},
         {'date':'2026-10-18','trading':False},{'date':'2026-10-19','trading':True}]
    enriched,contexts=bind_daily_filter(rows,macd,cld)
    assert enriched[0]['dailySourceDay']=='2026-10-16'
    assert contexts['2026-10-19']['availableAt']=='2026-10-16T15:00:00+08:00'
    modified=daily_macd([{**r,'close':99999 if datetime.fromtimestamp(r['datetime']/1e9,SH).date()>=date(2026,10,19) else r['close']} for r in raw])
    assert bind_daily_filter(rows,modified,cld)==(enriched,contexts)


def test_same_day_daily_close_does_not_affect_filter():
    raw=daily([100+i%5 for i in range(70)],start=date(2026,9,1))
    macd=daily_macd(raw)
    rows=[bar(0,105,day='2026-10-28')]
    cld=[{'date':'2026-10-27','trading':True},{'date':'2026-10-28','trading':True}]
    a=bind_daily_filter(rows,macd,cld)
    changed=[{**r,'close':99999 if datetime.fromtimestamp(r['datetime']/1e9,SH).date()>=date(2026,10,28) else r['close']} for r in raw]
    assert a==bind_daily_filter(rows,daily_macd(changed),cld)


def test_missing_previous_trading_day_or_unavailable_daily_is_rejected():
    raw=daily([100]*70,start=date(2026,9,1));macd=daily_macd(raw)
    rows=[bar(0,100,day='2026-10-28')];cld=[{'date':'2026-10-27','trading':True},{'date':'2026-10-28','trading':True}]
    with pytest.raises(ValueError,match='missing'):
        bind_daily_filter(rows,[r for r in macd if r['date']!='2026-10-27'],cld)
    rows[0]['timestamp']=datetime(2026,10,27,14,tzinfo=SH)
    with pytest.raises(ValueError,match='available'):
        bind_daily_filter(rows,macd,cld)


def test_direction_gate_rejects_initial_short_then_waits_for_fresh_long_cross():
    rows=gated([bar(0,99),bar(1,98),bar(2,101),bar(3,102),end(105)],side=1)
    trades,_,_,rejected=checked(rows,slippage=0)
    assert len(trades)==1 and trades[0]['side']==1
    assert trades[0]['entryReason']=='CROSS_AFTER_FILTER'
    assert trades[0]['signalTime']==rows[2]['timestamp'].isoformat()
    assert trades[0]['entryTime']==rows[3]['timestamp'].isoformat()
    assert rejected[0]['intendedSide']==-1 and rejected[0]['stage']=='SIGNAL'


def test_after_stop_wrong_direction_cross_is_blocked_and_later_matching_cross_enters():
    rows=gated([bar(0,101),bar(1,105,opening=101,low=90,high=105),bar(2,99),bar(3,98),bar(4,101),bar(5,102),end(105)])
    trades,_,_,rejected=checked(rows,slippage=0)
    assert [t['side'] for t in trades]==[1,1]
    assert trades[1]['entryReason']=='CROSS_AFTER_EXIT'
    assert trades[1]['signalTime']==rows[4]['timestamp'].isoformat()
    assert any(r['intendedSide']==-1 and r['reason']=='CROSS_AFTER_EXIT' for r in rejected)


def test_rejected_cross_cannot_open_later_without_a_new_cross():
    rows=gated([bar(0,101),bar(1,105,opening=101,low=90,high=105),bar(2,99),bar(3,98),bar(4,97),end(97)])
    trades,_,_,rejected=checked(rows,slippage=0)
    assert len(trades)==1 and rejected


def test_filter_does_not_block_mean_exit_or_create_reversal():
    rows=gated([bar(0,101),bar(1,101),bar(2,97),bar(3,96),bar(4,95),end(95)])
    trades,curve,events,_=checked(rows,slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='MEAN_REVERSAL'
    assert events[-1]['kind']=='CLOSE' and events[-1]['buy'] is False
    assert all(c['position']==0 for c in curve[3:])


def test_neutral_filter_opens_no_positions():
    rows=gated([bar(0,101),bar(1,99),bar(2,101),end(105)],side=0)
    for r in rows:r['dailyDIF']=r['dailyDEA']=0;r['dailyMACD']=0
    trades,curve,events,rejected=checked(rows,slippage=0)
    assert not trades and not events and rejected
    assert all(c['position']==0 for c in curve)


def test_filter_is_rechecked_before_pending_entry_fill():
    rows=gated([bar(0,101),bar(1,101),end(105)])
    rows[1]['allowedSide']=-1
    trades,_,events,rejected=simulate_macd_filtered(rows,slippage=0)
    assert not trades and not events
    assert any(r['stage']=='FILL' for r in rejected)


@pytest.mark.parametrize('slip',[0,1,2])
def test_long_short_filter_and_trade_symmetry(slip):
    base=[bar(0,99),bar(1,98),bar(2,101),bar(3,102),end(105)]
    a,_,_,_=checked(gated(base,1),slippage=slip)
    b,_,_,_=checked(gated(mirror(base),-1),slippage=slip,path='LOW_FIRST')
    assert [t['netPnl'] for t in a]==[t['netPnl'] for t in b]
    assert [t['side'] for t in a]==[-t['side'] for t in b]


def test_complete_day_prefix_is_not_changed_by_later_filter_states():
    first=gated([bar(0,101),bar(1,101),end(105)],1)
    second=gated([bar(0,99,day='2026-11-03'),bar(1,98,day='2026-11-03'),end(95,day='2026-11-03')],-1)
    a,ac,ae,ar=checked(first,slippage=0)
    b,bc,be,br=checked(first+second,slippage=0)
    assert b[:len(a)]==a and bc[:len(ac)]==ac and be[:len(ae)]==ae and br[:len(ar)]==ar


def test_daily_source_overlap_compares_completed_ohlcv_only():
    old={'daily':daily([100]*5)}
    new={'symbol':'CZCE.FG701','daily':daily([100]*5)}
    assert verify_daily_overlap(old,new)['overlappingCompletedDailyOHLCVChecks']==5
    new['daily'][2]['close']=101
    with pytest.raises(ValueError,match='mismatch'):
        verify_daily_overlap(old,new)


def test_reused_delivery_code_is_split_and_old_prices_cannot_seed_current_macd():
    old=daily([1200]*60,start=date(2016,1,1))
    new=daily([900+i*.2 for i in range(100)],start=date(2026,1,19))
    for i,r in enumerate(new):r['id']=len(old)+i
    expiry=datetime(2027,1,15,15,tzinfo=SH).timestamp()
    combined=old+new
    current,audit=current_contract_daily(combined,expiry)
    assert current==new and audit['excludedHistoricalCodeReuseBars']==60
    assert audit['firstCurrentDate']=='2026-01-19' and audit['firstCurrentSourceId']==60
    assert daily_macd(current,require_listing=False)[0]['dif']==0
    altered=[{**r,'close':99999} for r in old]+new
    assert daily_macd(current,require_listing=False)==daily_macd(current_contract_daily(altered,expiry)[0],require_listing=False)
    with pytest.raises(ValueError,match='reuse'):
        daily_macd(combined)


def test_history_from_wrong_delivery_maturity_is_rejected():
    expiry=datetime(2027,1,15,15,tzinfo=SH).timestamp()
    with pytest.raises(ValueError,match='maturity'):
        current_contract_daily(daily([1200]*60,start=date(2016,1,1)),expiry)


def test_current_delivery_history_cannot_contain_unexplained_multiweek_gap():
    raw=daily([900]*60,start=date(2026,1,19))
    for r in raw[30:]:r['datetime']+=int(timedelta(days=40).total_seconds()*1e9)
    with pytest.raises(ValueError,match='gap'):
        current_contract_daily(raw,datetime(2027,1,15,15,tzinfo=SH).timestamp())

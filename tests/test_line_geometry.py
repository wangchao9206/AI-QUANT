import copy,math
from datetime import datetime,timedelta,timezone
import pytest
from backtesting.line_geometry import geometry_snapshot


def bars(count=130):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    return [dict(timestamp=(start+timedelta(minutes=15*i)).isoformat(),open=100+i*.1,
                 price=100+i*.1,high=101+i*.1,low=99+i*.1,volume=1000) for i in range(count)]


def test_channel_is_fitted_before_signal_bar_and_crosses_fixed_old_line():
    points=bars(61);points[-1].update(open=120,price=121,high=122,low=119)
    snapshot=geometry_snapshot(points,False)
    assert snapshot['status']=='READY'
    center=next(line for line in snapshot['lines'] if line['kind']=='REGRESSION_CENTER')
    assert center['startPrice']==pytest.approx(100)
    assert center['endPrice']==pytest.approx(106)
    assert center['evidence']['fitEndAt']==points[-2]['timestamp']
    assert snapshot['features']['line.channelUpperCrossUp']==1
    assert center['knownAt']==points[-1]['timestamp']
    # A radically changed evaluated bar cannot tilt or widen its fitted channel.
    altered=copy.deepcopy(points);altered[-1].update(open=200,price=201,high=202,low=199)
    changed=geometry_snapshot(altered,False)
    assert snapshot['lines']==changed['lines']


def test_forming_bar_is_excluded_but_projection_reaches_its_slot():
    points=bars(62);a=geometry_snapshot(points,True)
    points[-1].update(open=1000,price=1000,low=999,high=1001)
    b=geometry_snapshot(points,True)
    assert a==b
    assert a['lines'][0]['endIndex']==61
    assert a['asOf']==points[-2]['timestamp']
    assert a['features']==geometry_snapshot(points[:-1],False)['features']


def test_pivots_wait_for_two_complete_right_candles_and_are_not_backfilled():
    points=bars(125)
    for i,b in enumerate(points):
        p=100+math.sin(i/3)*3+i*.01;b.update(open=p,price=p,low=p-.2,high=p+.2)
    result=geometry_snapshot(points,False)
    trends=[v for v in result['lines'] if v['kind'].startswith('TREND_')]
    assert len(trends)==2
    for line in trends:
        first,last=line['evidence']['anchors']
        assert last['index']-first['index']>=5
        assert last['index']+2<len(points)-1
        assert last['confirmedAt']==points[last['index']+3]['timestamp']
        assert line['knownAt']==last['confirmedAt']
    # A still-forming low cannot invent a newly confirmed support anchor.
    points[-1].update(open=1,price=1,low=.5,high=2)
    changed=geometry_snapshot(points,False)
    assert [v for v in changed['lines'] if v['kind'].startswith('TREND_')]==trends


def test_missing_pivots_are_explicit_and_bad_or_short_data_draws_no_lines():
    result=geometry_snapshot(bars(),False)
    assert result['features']['line.supportKnown']==0
    assert result['features']['line.resistanceKnown']==0
    assert 'line.supportDistanceATR' not in result['features']
    assert geometry_snapshot(bars(60),False)['status']=='WARMING'
    for value in (float('nan'),0,-1):
        points=bars();points[-4]['low']=value
        assert geometry_snapshot(points,False)['status']=='INVALID'
    points=bars();points[-1]['timestamp']=points[-2]['timestamp']
    assert geometry_snapshot(points,False)['status']=='INVALID'


def test_rolling_window_keeps_geometry_values_and_absolute_timestamp_anchors():
    points=bars(150)
    a=geometry_snapshot(points,False);b=geometry_snapshot(points[-121:],False)
    assert a['features']==b['features']
    for left,right in zip(a['lines'],b['lines']):
        assert left['startTimestamp']==right['startTimestamp']
        assert left['startPrice']==right['startPrice']
        assert left['endTimestamp']==right['endTimestamp']


def test_zero_prior_atr_and_extreme_numeric_values_do_not_fabricate_signals():
    points=bars(130)
    for b in points[-16:-1]:b.update(open=100,price=100,low=100,high=100)
    assert geometry_snapshot(points,False)['status']=='WARMING'
    points=bars();points[-2].update(open=1e300,price=1e300,high=1e300,low=1e300)
    assert geometry_snapshot(points,False)['status']=='INVALID'
    points=bars();points[0].clear()  # Outside the immutable 121-bar calculation window.
    assert geometry_snapshot(points,False)['status']=='READY'

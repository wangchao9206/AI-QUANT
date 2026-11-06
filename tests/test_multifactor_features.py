import copy,math
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import numpy as np
from backtesting.multifactor_features import NAMES,aggregate,extended_vector,chan
from scripts.research_multifactor_chan import tree

def bars(count,minutes=15):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    result=[]
    for i in range(count):
        p=100+math.sin(i/4)*2+math.sin(i/21)*3+i*.005
        result.append(dict(timestamp=(start+timedelta(minutes=minutes*i)).isoformat(),
                           open=p-.1,high=p+.3,low=p-.4,price=p,volume=1000+i%13,openInterest=20000+i))
    return result

def test_higher_periods_require_every_source_bar_and_preserve_availability():
    source=bars(8); result=aggregate(source,60)
    assert len(result)==2 and result[0]['volume']==sum(b['volume'] for b in source[:4])
    assert result[0]['availableAt']==datetime(2026,1,1,1,tzinfo=timezone.utc).timestamp()
    assert len(aggregate(source[:3],60))==0
    assert len(aggregate(source[:2]+source[3:],60))==1
    assert len(aggregate(source[:1]+source,60))==1  # Duplicate also invalidates bucket.

def test_feature_extraction_is_past_only_and_snapshots_cannot_repaint():
    minutes=bars(610);days=bars(70,1440)
    prefix=copy.deepcopy(minutes[:600]);before=copy.deepcopy(prefix)
    with patch('backtesting.outcome_features.targets',side_effect=AssertionError('future label in live extraction')):
        result=extended_vector(prefix,days)
    assert result and set(result['values'])==set(NAMES) and prefix==before
    original=copy.deepcopy(result)
    for b in minutes[600:]:b.update(high=10000,price=9999)
    assert extended_vector(minutes[:600],days)==original
    snapshot=chan(prefix[-120:],1);saved=copy.deepcopy(snapshot)
    chan(minutes[-120:],1)
    assert snapshot==saved

def test_search_splits_never_use_validation_outcomes_or_thresholds():
    x=np.arange(2400,dtype=float).reshape(-1,1);y=(x[:,0]>1000).astype(int)
    train=np.arange(1600);a=[];b=[]
    first=tree(x,y,train,('test',),a)
    x[1600:]=1e12;y[1600:]=1-y[1600:]
    second=tree(x,y,train,('test',),b)
    assert a==b
    assert [p for _,p in first]==[p for _,p in second]

def test_short_windows_and_unavailable_larger_context_produce_no_features():
    assert extended_vector(bars(599),bars(70,1440)) is None
    assert extended_vector(bars(600),bars(64,1440)) is None
    sparse=bars(600,30)
    assert extended_vector(sparse,bars(70,1440)) is None

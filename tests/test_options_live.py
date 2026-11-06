from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pandas as pd
import pytest
from data.options_feed import OptionsFeedState
from data.options_live import OptionsLiveState
from data.tqsdk_feed import TqSdkRealtimeFeed

SYMBOL='SHFE.rb2701C3200'

def metadata():return {'symbol':SYMBOL,'name':'螺纹钢认购','expiry':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(),'optionClass':'CALL','strike':3200,'chainId':'first','underlyingSymbol':'SHFE.rb2701'}

class Api:
 def __init__(self):
  self.now=datetime.now(timezone.utc);self.calls=[]
  self.quote={'datetime':self.now.isoformat(),'last_price':100,'bid_price1':99,'ask_price1':100,'bid_volume1':10,'ask_volume1':20}
  self.serial=pd.DataFrame([{'id':1,'datetime':int((self.now-timedelta(seconds=1)).timestamp()*1e9),'last_price':99,'volume':100,'bid_price1':98,'ask_price1':99},
                            {'id':2,'datetime':int(self.now.timestamp()*1e9),'last_price':100,'volume':102,'bid_price1':99,'ask_price1':100}])
 def get_quote_list(self,values):self.calls.append(('quote',values));return [self.quote for _ in values]
 def get_tick_serial(self,symbol,**kwargs):self.calls.append(('ticks',symbol));return self.serial
 def is_changing(self,item):return True

def test_known_option_only_and_live_subscriptions_are_bounded_without_request_thread_sdk_calls():
 state=OptionsFeedState();state.contract_index={SYMBOL:metadata()}
 assert state.live_contract(SYMBOL)['strike']==3200
 with pytest.raises(ValueError):state.live_contract('http://internal/forged')
 assert state.live_mappings()=={SYMBOL:SYMBOL}
 state.live.MAX_SUBSCRIPTIONS=1
 with pytest.raises(ValueError):state.live.request('another')

def test_depth_has_real_ticks_no_invented_levels_and_reuses_subscriptions():
 state=OptionsLiveState();state.request(SYMBOL);api=Api();entities={}
 state.subscribe(api,entities,2048);state.subscribe(api,entities,2048)
 assert len(api.calls)==2
 result=state.snapshot(SYMBOL,True,15)
 assert result['bids'][0]['price']==99 and result['bids'][1]['price'] is None
 assert result['trades'][0]['volume']==2 and result['trades'][0]['side']=='BUY'
 result['bids'][0]['price']=1
 assert state.snapshot(SYMBOL,False,15)['bids'][0]['price']==99
 assert state.snapshot(SYMBOL,False,15)['dataStatus']=='CACHED'
 api.quote['bid_volume1']=30;state.update(api,entities)
 assert state.snapshot(SYMBOL,True,15)['bids'][0]['volume']==30

def test_option_subscription_errors_are_contained_and_backed_off():
 state=OptionsLiveState();state.request(SYMBOL);api=Api()
 api.get_tick_serial=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('no permission'))
 state.subscribe(api,{},2048);state.subscribe(api,{},2048)
 with pytest.raises(ValueError,match='订阅暂不可用'):state.snapshot(SYMBOL,True,15)
 assert len(api.calls)==1

def test_options_match_exact_current_delivery_metadata_and_never_another_maturity():
 feed=TqSdkRealtimeFeed(fallback=SimpleNamespace())
 feed.provider_symbols={'RBM':'KQ.m@SHFE.rb','RB2701':'SHFE.rb2701','RB2705':'SHFE.rb2705'}
 feed.quotes={'RBM':{'underlyingSymbol':'RB2701'}};feed.options.catalog_timestamp=datetime.now(timezone.utc).isoformat()
 feed.options.chains={key:{'id':key,'exchange':'SHFE','underlyingType':'FUTURE','underlyingSymbol':underlying,'expiry':'2027-01-01'} for key,underlying in [('first','SHFE.rb2701'),('other','SHFE.rb2705')]}
 assert [c['id'] for c in feed.linked_options('RBM')['chains']]==['first']
 feed.quotes['RBM']['underlyingSymbol']='RB2705'
 assert [c['id'] for c in feed.linked_options('RBM')['chains']]==['other']
 feed.quotes={}
 assert feed.linked_options('RBM')['chains']==[] and feed.linked_options('RBM')['resolvedFuture'] is None

def test_expired_options_cannot_be_started():
 state=OptionsFeedState();state.contract_index={SYMBOL:{**metadata(),'expiry':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}}
 with pytest.raises(ValueError,match='到期'):state.live_contract(SYMBOL)

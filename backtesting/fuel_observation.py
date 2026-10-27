"""Append-only-source daily shadow replay; no broker connection or production orders.

Replays frozen rules from a prospective start. Removes the research engine's
artificial terminal close so an open position survives subsequent observations.
"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import date,timedelta
import hashlib,json,math,os,tempfile
from pathlib import Path
from backtesting.independent_research import ResearchRisk,causal_prices,planned_lots,simulate,_metrics
from backtesting.strategy_signals import daily_atr
from backtesting.workflow import compile_workflow

ENGINE='fu-daily-shadow-v1'

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def sha(value):return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()

def evidence(dataset,cutoff):
    bars=[{'timestamp':b.timestamp.isoformat(),'contract':b.contract_symbol,'open':b.open,'high':b.high,
       'low':b.low,'close':b.close,'volume':b.volume,'openInterest':b.open_interest}
       for b in dataset.bars if b.timestamp.date()<=cutoff]
    rolls=[{'date':str(e.execution_date),'old':e.from_contract,'new':e.to_contract,
       'oldOpen':e.old_open,'newOpen':e.new_open,'oldHigh':e.old_high,'oldLow':e.old_low,
       'newHigh':e.new_high,'newLow':e.new_low} for e in dataset.roll_events if e.execution_date<=cutoff]
    return {'count':len(bars),'digest':sha({'bars':bars,'rolls':rolls})}

def freeze(dataset,definition,initial_cash=1_000_000):
    signals=causal_prices(dataset);program=compile_workflow(definition)
    if dataset.symbol!='FU0' or initial_cash<=0:raise ValueError('FU-only virtual study required')
    cutoff=dataset.bars[-1].timestamp.date()
    specs={k:{'contract':v.contract,'volume_multiple':v.volume_multiple,'price_tick':v.price_tick,
          'margin_per_lot':v.margin_per_lot,'commission_per_lot':v.commission_per_lot} for k,v in dataset.contract_specs.items()}
    config={'definition':program.definition.model_dump(),'risk':vars(ResearchRisk()),
       'initialCash':initial_cash,'freezeDate':str(cutoff),'engineVersion':ENGINE,
       'symbol':'FU0','signalBasis':'CAUSAL_DELIVERY_ROLL_RATIO'}
    state={'qualification':'EXPLORATORY_DIAGNOSTIC_ONLY','config':config,'configHash':sha(config),
      'initialEvidence':evidence(dataset,cutoff),'lastEvidence':evidence(dataset,cutoff),
      'asOf':str(cutoff),'contractSpecs':specs,'curve':[],'trades':[],'position':None,
      'cash':initial_cash,'equity':initial_cash,'revision':0,'events':[],
      'status':'AWAIT_NEW_COMPLETED_DAILY_DATA','ordersSubmittedToBroker':0}
    state['nextSignal']=_plan(dataset,program,signals,state)
    return state

def _plan(dataset,program,signals,state):
    direction=state['position']['direction'] if state['position'] else 0
    outcome=program.prepare(signals).evaluate(len(signals)-1,direction,symbol='FU0')
    risk=ResearchRisk(**state['config']['risk']);latest=dataset.bars[-1]
    spec=dataset.contract_specs[latest.contract_symbol]
    atr=daily_atr(dataset.bars,contract_aware=True)
    quantity,unit=planned_lots(state['cash'],state['config']['initialCash'],latest.close,atr,
        program.risk['stopLossAtr'],spec,risk)
    return {'signalDate':str(latest.timestamp.date()),'signal':outcome.signal,'reason':outcome.reason,
       'maxPlannedEntryLots':quantity if outcome.signal in ('BUY','SELL') else 0,
       'estimatedRiskPerLot':unit,'atr':atr,'execution':'NEXT_OBSERVED_BAR_OPEN_IF_ELIGIBLE',
       'submittedOrder':False,'nodeTrace':outcome.node_trace}

def snapshot(dataset,definition,initial,start,end,risk):
    result=simulate(dataset,definition,initial,start,end,risk=risk)
    trades=result['trades'];curve=result['curve'];position=None
    fees=result['metrics']['fees'];slippage=result['metrics']['slippageCost']
    last=next(b for b in reversed(dataset.bars) if b.timestamp.date()<=end)
    if trades and trades[-1]['exitReason']=='WINDOW_END_LIQUIDATION':
        terminal=trades[-1];spec=dataset.contract_specs[terminal['contract']]
        # Undo only the artificial reporting liquidation. Real stops/exits remain.
        mark_correction=terminal['direction']*(last.close-terminal['exitPrice'])*spec.volume_multiple*terminal['lots']
        curve[-1]={**curve[-1],'equity':curve[-1]['equity']+mark_correction+terminal['closingFee'],
                   'direction':terminal['direction'],'lots':terminal['lots']}
        fees-=terminal['closingFee']
        slippage-=abs(last.close-terminal['exitPrice'])*spec.volume_multiple*terminal['lots']
        position={k:v for k,v in terminal.items() if k not in
            ('exitDate','exitReason','exitPrice','netPnl','rMultiple','closingFee')}
        trades=trades[:-1]
    cash=initial+sum(t['netPnl'] for t in trades)-(position['openingFee'] if position else 0)
    unrealized=0 if not position else position['direction']*(last.close-position['entryPrice'])*dataset.contract_specs[position['contract']].volume_multiple*position['lots']
    equity=cash+unrealized
    assert abs(equity-(curve[-1]['equity'] if curve else initial))<1e-5
    return {'curve':curve,'trades':trades,'position':position,'cash':cash,'equity':equity,
      'unrealizedPnl':unrealized,'realizedClosedNetPnl':sum(t['netPnl'] for t in trades),
      'metrics':_metrics(curve,trades,initial,fees,slippage,{})}

def _equal(a,b):
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(_equal(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(_equal(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and not isinstance(a,bool) and isinstance(b,(int,float)) and not isinstance(b,bool):
        return math.isclose(a,b,abs_tol=1e-6,rel_tol=0)
    return a==b

def advance(state,dataset):
    # Every source observation is treated as completed only after the caller's cutoff check.
    if state['configHash']!=sha(state['config']):raise ValueError('Frozen strategy or risk configuration changed')
    if state['config']['engineVersion']!=ENGINE or dataset.symbol!='FU0':raise ValueError('Wrong engine or symbol')
    signals=causal_prices(dataset)
    prior=date.fromisoformat(state['asOf']);latest=dataset.bars[-1].timestamp.date()
    if latest<prior:raise ValueError('Cannot move shadow clock backwards')
    if evidence(dataset,prior)!=state['lastEvidence']:raise ValueError('Previously observed market evidence changed; quarantine instead of rewriting')
    if latest==prior:return state
    # Preserve all previously frozen specifications; only append new delivery identities.
    from data.tqsdk_backtest import FuturesContractSpec
    frozen={k:FuturesContractSpec(**v) for k,v in state['contractSpecs'].items()}
    frozen.update({k:v for k,v in dataset.contract_specs.items() if k not in frozen})
    observed=replace(dataset,contract_specs=frozen)
    start=date.fromisoformat(state['config']['freezeDate'])+timedelta(days=1)
    risk=ResearchRisk(**state['config']['risk'])
    result=snapshot(observed,state['config']['definition'],state['config']['initialCash'],start,latest,risk)
    old_curve=[p for p in result['curve'] if p['date']<=state['asOf']]
    old_trades=[t for t in result['trades'] if t['exitDate']<=state['asOf']]
    if not _equal(old_curve,state['curve']) or not _equal(old_trades,state['trades']):raise ValueError('Committed shadow history would change')
    result['curve']=state['curve']+[p for p in result['curve'] if p['date']>state['asOf']]
    result['trades']=state['trades']+[t for t in result['trades'] if t['exitDate']>state['asOf']]
    next_state={**state,**result,'asOf':str(latest),'lastEvidence':evidence(dataset,latest),
        'revision':state['revision']+1,'contractSpecs':{k:vars(v) for k,v in frozen.items()},
        'status':'DAILY_SHADOW_REPLAY_NOT_REAL_FILLS',
        'events':state['events']+[{'from':str(prior),'to':str(latest),
           'newObservedBars':sum(prior<b.timestamp.date()<=latest for b in observed.bars),
           'observationMode':'COMPLETED_DAILY_COUNTERFACTUAL_REPLAY'}]}
    next_state['nextSignal']=_plan(observed,compile_workflow(state['config']['definition']),signals,next_state)
    return next_state

@contextmanager
def state_lock(path):
    lock=Path(str(path)+'.lock')
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        with os.fdopen(descriptor,'w') as stream:stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)

def atomic_save(path,state):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    name=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False,suffix='.tmp') as stream:
            name=stream.name;stream.write(canonical(state));stream.flush();os.fsync(stream.fileno())
        os.replace(name,path);name=None
    finally:
        if name is not None:Path(name).unlink(missing_ok=True)

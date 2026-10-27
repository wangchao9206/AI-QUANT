"""FU research hypotheses and pre-registered diagnostics. No production orders."""
from copy import deepcopy
from dataclasses import replace
import hashlib,json,math,statistics
import numpy as np

from backtesting.workflow import compile_workflow

FAMILIES={
 'CHANNEL_TREND':('顺势20日突破','趋势延续可能覆盖小额试错和成本'),
 'SLOW_CHANNEL':('慢55日突破','更慢的突破减少来回交易，代价是入场滞后'),
 'MA_TREND':('双均线跟随','中短趋势方向一致时跟随，价格越回快线退出'),
 'TIME_MOMENTUM':('定周期动量','超过波动尺度的区间净变化可能延续'),
 'ATR_CHANNEL':('波动通道突破','收盘离开波动通道后可能进入方向性行情'),
 'TREND_PULLBACK':('顺势回撤','大趋势内的短期过度回撤可能回到均线'),
 'BAND_REVERSION':('均值回归','偏离均值后的修复可能补偿交易成本'),
 'RANGE_REVERSION':('区间位置反转','接近近期区间端点后可能回到中部'),
 'SQUEEZE_BREAKOUT':('收敛后突破','前期波动收敛后的突破可能更持久'),
 'VOLUME_BREAKOUT':('放量突破','成交量确认可能过滤价格假突破'),
 'FAILED_BREAKOUT':('假突破反转','前一日越界失败、次日反向确认后可能延续'),
 'GAP_FADE':('跳空失败回归','跳出前日区间后收回可能是过度反应'),
 'INSIDE_BREAKOUT':('内包后突破','内包压缩后的方向突破可能有效'),
 'NARROW_BREAKOUT':('窄幅后突破','低于近期平均幅度的窄幅之后可能扩张'),
 'VOL_EXPANSION':('波动扩张确认','扩张日靠近极端位置收盘可能有延续'),
 'THREE_BAR_TURN':('连跌连涨后转向','连续单向变化后的反向实体可能标记短期修复'),
}
TREND={'CHANNEL_TREND','SLOW_CHANNEL','MA_TREND','TIME_MOMENTUM','ATR_CHANNEL',
       'SQUEEZE_BREAKOUT','VOLUME_BREAKOUT','INSIDE_BREAKOUT','NARROW_BREAKOUT','VOL_EXPANSION'}
SCALES=(.75,1.,1.25)
REPAIRS=('BASE','QUIET_FILTER','PAYOFF_HORIZON')
ENGINE='fu-focused-research-v1'

class Graph:
    def __init__(self):
        self.nodes=[];self.edges=[];self.memo={}
        self.market=self.add('MARKET',{})
        self.price=self.field('close')
    def add(self,kind,params,inputs=()):
        key=(kind,json.dumps(params,sort_keys=True),tuple(inputs))
        if key in self.memo:return self.memo[key]
        id='n'+str(len(self.nodes));self.nodes.append({'id':id,'type':kind,'label':kind+' '+str(params),'params':params})
        self.memo[key]=id
        for port,source,source_port in inputs:
            self.edges.append({'id':'e'+str(len(self.edges)),'source':source,'sourcePort':source_port,'target':id,'targetPort':port})
        return id
    def field(self,field,shift=0):
        return self.add('PRICE',{'field':field,'shift':shift},(('market',self.market,'bars'),))
    def indicator(self,kind,period,field='close',shift=0):
        return self.add('INDICATOR',{'kind':kind,'period':period,'field':field,'shift':shift},(('market',self.market,'bars'),))
    def const(self,value):return self.add('CONSTANT',{'value':value})
    def math(self,op,a,b):return self.add('MATH',{'op':op},(('left',a,'value'),('right',b,'value')))
    def compare(self,op,a,b):return self.add('COMPARE',{'op':op},(('left',a,'value'),('right',b,'value')))
    def all(self,*conditions):
        value=conditions[0]
        for other in conditions[1:]:value=self.add('LOGIC',{'op':'AND'},(('a',value,'result'),('b',other,'result')))
        return value
    def action(self,action,condition,risk):
        self.add('ACTION',{'action':action},(('condition',condition,'result'),('risk',risk,'risk')))
    def finish(self):
        # Memoization shares common inputs. Prune scaffolding not used by any action.
        wanted={n['id'] for n in self.nodes if n['type']=='ACTION'}
        while True:
            expanded=wanted|{e['source'] for e in self.edges if e['target'] in wanted}
            if expanded==wanted:break
            wanted=expanded
        graph={'schemaVersion':1,'nodes':[n for n in self.nodes if n['id'] in wanted],
               'edges':[e for e in self.edges if e['source'] in wanted and e['target'] in wanted]}
        return compile_workflow(graph).definition.model_dump()


def build(family,scale=1.,repair='BASE',direction='BOTH'):
    if family not in FAMILIES or scale not in SCALES or repair not in REPAIRS or direction not in ('BOTH','LONG','SHORT'):
        raise ValueError('Unknown frozen FU configuration')
    g=Graph();p=g.price;period=lambda n:max(2,int(n*scale+.5))
    sma=lambda n,shift=0:g.indicator('SMA',n,shift=shift)
    gt=lambda a,b:g.compare('GT',a,b)
    lt=lambda a,b:g.compare('LT',a,b)
    mul=lambda a,k:g.math('MUL',a,g.const(k))
    sub=lambda a,b:g.math('SUB',a,b)
    add=lambda a,b:g.math('ADD',a,b)
    mean=sma(period(20));close_long=gt(p,mean);close_short=lt(p,mean)
    trend=sma(60);up=gt(p,trend);down=lt(p,trend)
    if family in ('CHANNEL_TREND','SLOW_CHANNEL','VOLUME_BREAKOUT','SQUEEZE_BREAKOUT'):
        n=period(55 if family=='SLOW_CHANNEL' else 20)
        high=g.indicator('HIGHEST',n,'high',1);low=g.indicator('LOWEST',n,'low',1)
        buy,sell=gt(p,high),lt(p,low)
        if family in ('CHANNEL_TREND','SLOW_CHANNEL','VOLUME_BREAKOUT'):
            buy,sell=g.all(buy,up),g.all(sell,down)
        if family=='VOLUME_BREAKOUT':
            gate=gt(g.field('volume'),mul(g.indicator('SMA',period(20),'volume',1),1.2))
            buy,sell=g.all(buy,gate),g.all(sell,gate)
        if family=='SQUEEZE_BREAKOUT':
            gate=lt(g.indicator('STDDEV',period(20),shift=1),mul(g.indicator('STDDEV',60,shift=1),.7))
            buy,sell=g.all(buy,gate),g.all(sell,gate)
        close_long=lt(p,g.indicator('LOWEST',10,'low',1))
        close_short=gt(p,g.indicator('HIGHEST',10,'high',1))
    elif family=='MA_TREND':
        fast,slow=sma(period(10)),sma(period(40))
        buy,sell=g.all(gt(fast,slow),gt(p,fast)),g.all(lt(fast,slow),lt(p,fast))
        close_long,close_short=lt(p,fast),gt(p,fast)
    elif family=='TIME_MOMENTUM':
        previous=g.field('close',period(20));width=mul(g.indicator('ATR',14),.75)
        buy,sell=gt(p,add(previous,width)),lt(p,sub(previous,width))
        close_long,close_short=lt(p,mean),gt(p,mean)
    elif family=='ATR_CHANNEL':
        width=mul(g.indicator('ATR',14),1.5)
        buy,sell=gt(p,add(mean,width)),lt(p,sub(mean,width))
        close_long,close_short=lt(p,mean),gt(p,mean)
    elif family in ('TREND_PULLBACK','BAND_REVERSION'):
        width=mul(g.indicator('STDDEV',period(20)),1.5)
        buy,sell=lt(p,sub(mean,width)),gt(p,add(mean,width))
        if family=='TREND_PULLBACK':buy,sell=g.all(buy,up),g.all(sell,down)
    elif family=='RANGE_REVERSION':
        high=g.indicator('HIGHEST',period(14),'high')
        low=g.indicator('LOWEST',period(14),'low');width=sub(high,low)
        buy,sell=lt(p,add(low,mul(width,.15))),gt(p,add(low,mul(width,.85)))
        mean=sma(period(10));close_long,close_short=gt(p,mean),lt(p,mean)
    elif family=='FAILED_BREAKOUT':
        high=g.indicator('HIGHEST',period(20),'high',2)
        low=g.indicator('LOWEST',period(20),'low',2);prev=g.field('close',1)
        buy=g.all(lt(g.field('low',1),low),gt(prev,low),gt(p,g.field('high',1)))
        sell=g.all(gt(g.field('high',1),high),lt(prev,high),lt(p,g.field('low',1)))
        mean=sma(period(10));close_long,close_short=gt(p,mean),lt(p,mean)
    elif family=='GAP_FADE':
        high,low=g.field('high',1),g.field('low',1);op=g.field('open')
        buy,sell=g.all(lt(op,low),gt(p,low)),g.all(gt(op,high),lt(p,high))
        mean=sma(period(10));close_long,close_short=gt(p,mean),lt(p,mean)
    elif family=='INSIDE_BREAKOUT':
        high,low=g.field('high',1),g.field('low',1)
        inside=g.all(lt(high,g.field('high',2)),gt(low,g.field('low',2)))
        buy,sell=g.all(inside,gt(p,high)),g.all(inside,lt(p,low))
        mean=sma(period(10));close_long,close_short=lt(p,mean),gt(p,mean)
    elif family=='NARROW_BREAKOUT':
        high,low=g.field('high',1),g.field('low',1)
        avg=sub(g.indicator('SMA',period(20),'high',1),g.indicator('SMA',period(20),'low',1))
        narrow=lt(sub(high,low),mul(avg,.6))
        buy,sell=g.all(narrow,gt(p,high)),g.all(narrow,lt(p,low))
        mean=sma(period(10));close_long,close_short=lt(p,mean),gt(p,mean)
    elif family=='VOL_EXPANSION':
        high,low=g.field('high'),g.field('low');width=sub(high,low)
        expand=gt(width,mul(g.indicator('ATR',14,shift=1),1.4))
        buy=g.all(expand,gt(p,add(low,mul(width,.75))))
        sell=g.all(expand,lt(p,add(low,mul(width,.25))))
        mean=sma(period(10));close_long,close_short=lt(p,mean),gt(p,mean)
    else:
        a,b,c=g.field('close',1),g.field('close',2),g.field('close',3);op=g.field('open')
        buy=g.all(lt(a,b),lt(b,c),gt(p,op),gt(p,a))
        sell=g.all(gt(a,b),gt(b,c),lt(p,op),lt(p,a))
        mean=sma(period(5));close_long,close_short=gt(p,mean),lt(p,mean)
    if repair=='QUIET_FILTER':
        gate=g.compare('LTE',g.indicator('ATR',14),mul(g.indicator('ATR',60),1.25))
        buy,sell=g.all(buy,gate),g.all(sell,gate)
    target=4 if repair!='PAYOFF_HORIZON' else 8 if family in TREND else 2
    risk=g.add('RISK',{'lots':1,'stopLossAtr':2,'takeProfitAtr':target})
    if direction!='SHORT':
        g.action('BUY',buy,risk);g.action('CLOSE_LONG',close_long,risk)
    if direction!='LONG':
        g.action('SELL',sell,risk);g.action('CLOSE_SHORT',close_short,risk)
    return g.finish()


def digest(graph):
    return hashlib.sha256(json.dumps(graph,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def delayed_signals(signals):
    return [replace(signals[max(0,i-1)],timestamp=b.timestamp) for i,b in enumerate(signals)]


def segments(curve,initial,parts=3):
    if not curve:return []
    result=[];prior=initial
    for j in range(parts):
        lo=len(curve)*j//parts;hi=len(curve)*(j+1)//parts;chunk=curve[lo:hi]
        if not chunk:continue
        equity=[prior]+[p['equity'] for p in chunk]
        returns=[equity[i]/equity[i-1]-1 for i in range(1,len(equity))]
        sd=statistics.pstdev(returns)
        result.append({'first':chunk[0]['date'],'last':chunk[-1]['date'],
            'returnPct':(equity[-1]/prior-1)*100,
            'sharpe':statistics.mean(returns)/sd*math.sqrt(250) if sd else 0})
        prior=equity[-1]
    return result


def adjusted_sharpe_p(curves,initial,indices,*,iterations=1000,seed=20261027,block=10):
    """Joint centered circular block bootstrap of maximum Sharpe, conditional approximation."""
    names=list(curves);lengths={len(curves[n]) for n in names}
    if len(lengths)!=1 or next(iter(lengths),0)<20:raise ValueError('Aligned development curves required')
    dates=[p['date'] for p in curves[names[0]]]
    if any([p['date'] for p in curves[n]]!=dates for n in names):raise ValueError('Different bootstrap clocks')
    equity=np.asarray([[initial]+[p['equity'] for p in curves[n]] for n in names],dtype=float)
    returns=equity[:,1:]/equity[:,:-1]-1
    sd=returns.std(axis=1);observed=np.divide(returns.mean(axis=1),sd,out=np.zeros_like(sd),where=sd>0)*math.sqrt(250)
    centered=returns-returns.mean(axis=1,keepdims=True)
    rng=np.random.default_rng(seed);maxima=[]
    n=returns.shape[1]
    for _ in range(iterations):
        starts=rng.integers(0,n,size=math.ceil(n/block))
        take=((starts[:,None]+np.arange(block))%n).ravel()[:n]
        sample=centered[:,take];std=sample.std(axis=1)
        sharpe=np.divide(sample.mean(axis=1),std,out=np.zeros_like(std),where=std>0)*math.sqrt(250)
        maxima.append(float(sharpe.max()))
    return {'iterations':iterations,'blockDays':block,'seed':seed,'configurations':len(names),
        'method':'joint centered circular-block max-Sharpe bootstrap; conditional approximation',
        'selected':{name:{'developmentSharpe':float(observed[names.index(name)]),
              'adjustedP':float((1+sum(v>=observed[names.index(name)] for v in maxima))/(iterations+1))}
             for name in indices}}


def choose_candidates(development):
    """Development-only stable center choice. Validation never enters this function."""
    if any(r.get('stage') not in (None,'DEVELOPMENT') for r in development):raise ValueError('Selection only accepts development evidence')
    by={(r['family'],r['repair'],r['scale'],r['cost']):r for r in development if r['direction']=='BOTH'}
    chosen=[]
    def eligible(r):
        m=r['metrics'];return m['closedTrades']>=20 and m['netPnl']>0
    def rank(r):
        folds=r['segments']
        return (statistics.median(s['sharpe'] for s in folds),min(s['returnPct'] for s in folds),r['metrics']['netPnl'])
    for family in FAMILIES:
        base=by[(family,'BASE',1.,1)]
        positive=lambda r:sum(s['returnPct']>0 for s in r['segments'])
        allowed=[base]
        for repair in REPAIRS[1:]:
            r=by[(family,repair,1.,1)];stress=by[(family,repair,1.,2)]
            if eligible(r) and stress['metrics']['netPnl']>0 and positive(r)>=positive(base) and rank(r)[0]>=rank(base)[0]+.1:
                allowed.append(r)
        selected=max(allowed,key=rank)
        neighbor=sum(by[(family,selected['repair'],scale,2)]['metrics']['netPnl']>0 for scale in SCALES)
        chosen.append({'family':family,'repair':selected['repair'],'graphHash':selected['graphHash'],
            'score':rank(selected),'developmentQualified':selected['metrics']['closedTrades']>=30 and positive(selected)>=2 and neighbor>=2,
            'positiveDevelopmentSegments':positive(selected),'positiveStressNeighbors':neighbor})
    # Eligibility ranks before score; if none pass, still preserve and diagnose top three.
    chosen.sort(key=lambda x:(x['developmentQualified'],*x['score']),reverse=True)
    return chosen[:3],chosen

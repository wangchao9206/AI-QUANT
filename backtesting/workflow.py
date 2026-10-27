"""Bounded causal strategy graphs. No user code, network nodes or expression eval."""
from dataclasses import dataclass
from typing import Literal
import math

from pydantic import BaseModel, ConfigDict, Field
from data.data_feed import KLineBar

ENGINE_VERSION = 'workflow-daily-v1'
PRESETS = {'HOLISTIC_14D', 'MOMENTUM_BREAKOUT', 'BOLLINGER_REVERSAL',
           'DUAL_THRUST', 'ADAPTIVE_CTA', 'BUY_AND_HOLD'}
FIELDS = {'open', 'high', 'low', 'close', 'volume'}


class Node(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    type: Literal['MARKET','PRICE','INDICATOR','CONSTANT','POSITION','MATH','COMPARE','LOGIC','PRESET','RISK','ACTION']
    label: str = Field(default='', max_length=80)
    params: dict = Field(default_factory=dict)
    x: float = Field(default=100, ge=-4000, le=8000, allow_inf_nan=False)
    y: float = Field(default=100, ge=-4000, le=8000, allow_inf_nan=False)


class Edge(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    source: str
    target: str
    sourcePort: str
    targetPort: str


class Definition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schemaVersion: Literal[1] = 1
    nodes: list[Node] = Field(min_length=1, max_length=40)
    edges: list[Edge] = Field(max_length=120)


DEFAULTS = {
    'MARKET': {}, 'PRICE': {'field':'close','shift':0},
    'INDICATOR': {'kind':'SMA','field':'close','period':20,'shift':0},
    'CONSTANT': {'value':0}, 'POSITION': {}, 'MATH': {'op':'MUL'},
    'COMPARE': {'op':'GT'}, 'LOGIC': {'op':'AND'},
    'PRESET': {'strategy':'MOMENTUM_BREAKOUT'},
    'RISK': {'lots':1,'stopLossAtr':2,'takeProfitAtr':3}, 'ACTION': {'action':'BUY'},
}


def ports(node: Node):
    inputs = {'MARKET':{},'PRICE':{'market':'SERIES'},'INDICATOR':{'market':'SERIES'},
              'CONSTANT':{},'POSITION':{},'MATH':{'left':'NUMBER','right':'NUMBER'},
              'COMPARE':{'left':'NUMBER','right':'NUMBER'},
              'LOGIC':{'a':'BOOLEAN', **({} if node.params.get('op')=='NOT' else {'b':'BOOLEAN'})},
              'PRESET':{'market':'SERIES'},'RISK':{},'ACTION':{'condition':'BOOLEAN','risk':'RISK'}}
    outputs = {'MARKET':{'bars':'SERIES'},'PRICE':{'value':'NUMBER'},'INDICATOR':{'value':'NUMBER'},
               'CONSTANT':{'value':'NUMBER'},'POSITION':{'value':'NUMBER'},'MATH':{'value':'NUMBER'},
               'COMPARE':{'result':'BOOLEAN'},'LOGIC':{'result':'BOOLEAN'},
               'PRESET':{'buy':'BOOLEAN','sell':'BOOLEAN','close':'BOOLEAN'},'RISK':{'risk':'RISK'},'ACTION':{}}
    return inputs[node.type], outputs[node.type]


def _number(value, lo, hi, label, integer=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) \
       or not lo <= value <= hi or integer and int(value)!=value:
        raise ValueError(f'{label}必须在{lo}至{hi}之间'+('且为整数' if integer else ''))


def compile_workflow(raw) -> 'Program':
    graph = raw if isinstance(raw,Definition) else Definition.model_validate(raw)
    graph = graph.model_copy(deep=True)
    nodes = {n.id:n for n in graph.nodes}
    if len(nodes)!=len(graph.nodes): raise ValueError('节点编号不能重复')
    if len({e.id for e in graph.edges})!=len(graph.edges): raise ValueError('连线编号不能重复')
    required=1
    for n in graph.nodes:
        if set(n.params)-set(DEFAULTS[n.type]): raise ValueError(f'{n.label or n.id}包含不支持的参数')
        n.params={**DEFAULTS[n.type],**n.params}
        p=n.params
        for key, allowed in [('field',FIELDS),('kind',{'SMA','EMA','ATR','HIGHEST','LOWEST','STDDEV'}),
            ('strategy',PRESETS),('action',{'BUY','SELL','CLOSE_LONG','CLOSE_SHORT','FLATTEN'})]:
            if key in p and (not isinstance(p[key],str) or p[key] not in allowed): raise ValueError(f'{n.label or n.id}的{key}参数无效')
        allowed_ops={'MATH':{'ADD','SUB','MUL','DIV'},'COMPARE':{'GT','GTE','LT','LTE','EQ'},'LOGIC':{'AND','OR','NOT'}}
        if n.type in allowed_ops and (not isinstance(p['op'],str) or p['op'] not in allowed_ops[n.type]): raise ValueError(f'{n.label or n.id}的运算无效')
        if 'shift' in p: _number(p['shift'],0,250,'历史偏移',True)
        if 'period' in p: _number(p['period'],2,250,'指标周期',True)
        if 'value' in p: _number(p['value'],-1_000_000_000,1_000_000_000,'常量')
        if n.type=='RISK':
            _number(p['lots'],1,1_000_000,'开仓手数',True)
            _number(p['stopLossAtr'],.1,20,'止损ATR')
            _number(p['takeProfitAtr'],.1,50,'止盈ATR')
            for key in ('stopLossAtr','takeProfitAtr'):
                if abs(p[key]-round(p[key],4))>1e-10:raise ValueError('ATR保护倍数最多支持4位小数')
                p[key]=round(p[key],4)
        if n.type in ('PRICE','INDICATOR'): required=max(required,int(p.get('period',1))+int(p['shift']))
        if n.type=='PRESET': required=max(required,2 if p['strategy']=='BUY_AND_HOLD' else 20 if p['strategy']=='BOLLINGER_REVERSAL' else 61)
    if sum(n.type=='MARKET' for n in graph.nodes)!=1: raise ValueError('工作流需要且只能有一个已完成日线行情节点')
    risks=[n for n in graph.nodes if n.type=='RISK']
    if len(risks)!=1: raise ValueError('工作流需要且只能有一个风控节点')
    actions=[n for n in graph.nodes if n.type=='ACTION']
    if not any(n.params['action'] in ('BUY','SELL') for n in actions): raise ValueError('至少连接一个开多或开空动作')
    incoming={n.id:{} for n in graph.nodes}; outgoing={n.id:[] for n in graph.nodes}
    for e in graph.edges:
        if e.source not in nodes or e.target not in nodes: raise ValueError('连线引用了不存在的节点')
        source_ports=ports(nodes[e.source])[1]; target_ports=ports(nodes[e.target])[0]
        if e.sourcePort not in source_ports or e.targetPort not in target_ports: raise ValueError('连线端口不存在')
        if source_ports[e.sourcePort]!=target_ports[e.targetPort]: raise ValueError('连线类型不符：请连接相同类型的端口')
        if e.targetPort in incoming[e.target]: raise ValueError('一个输入端口只能连接一条线')
        incoming[e.target][e.targetPort]=e;outgoing[e.source].append(e.target)
    for n in graph.nodes:
        missing=set(ports(n)[0])-set(incoming[n.id])
        if missing: raise ValueError(f'{n.label or n.id}缺少输入：'+','.join(sorted(missing)))
    degrees={key:len(value) for key,value in incoming.items()};queue=[key for key,d in degrees.items() if d==0];order=[]
    while queue:
        key=queue.pop(0);order.append(key)
        for target in outgoing[key]:
            degrees[target]-=1
            if degrees[target]==0: queue.append(target)
    if len(order)!=len(nodes): raise ValueError('工作流不能包含循环连线')
    reachable=set()
    def visit(key):
        if key in reachable:return
        reachable.add(key)
        for edge in incoming[key].values():visit(edge.source)
    for n in actions:visit(n.id)
    unused=set(nodes)-reachable
    if unused: raise ValueError('存在未连接到交易动作的节点：'+','.join(sorted(unused)))
    return Program(graph,nodes,incoming,order,required,dict(risks[0].params))


@dataclass
class Outcome:
    signal: str
    reason: str
    required_bars: int
    node_trace: list[dict]


@dataclass
class Program:
    definition: Definition
    nodes: dict
    incoming: dict
    order: list[str]
    required_bars: int
    risk: dict

    def prepare(self,bars: list[KLineBar]) -> 'Prepared':
        if any(a.timestamp>=b.timestamp for a,b in zip(bars,bars[1:])): raise ValueError('工作流日线必须严格按时间排序')
        return Prepared(self,bars)

    def metadata(self):
        return {'definition':self.definition.model_dump(),'engineVersion':ENGINE_VERSION,
                'requiredBars':self.required_bars,'risk':self.risk,'nodeCount':len(self.nodes)}


class Prepared:
    def __init__(self,program:Program,bars:list[KLineBar]):
        self.program,self.bars,self.metrics=program,bars,{}
        for n in program.nodes.values():
            if n.type not in ('PRICE','INDICATOR'):continue
            p=n.params;values=[float(getattr(b,p['field'])) for b in bars]
            if n.type=='PRICE': series=values
            else:
                period=int(p['period']);kind=p['kind'];series=[];ema=values[0] if values else 0
                if kind=='ATR':
                    values=[max(b.high-b.low,abs(b.high-bars[i-1].close),abs(b.low-bars[i-1].close)) if i else b.high-b.low for i,b in enumerate(bars)]
                for i,value in enumerate(values):
                    if kind=='EMA':ema=value if i==0 else value*(2/(period+1))+ema*(1-2/(period+1))
                    window=values[max(0,i-period+1):i+1]
                    if i+1<period:result=None
                    elif kind=='EMA':result=ema
                    elif kind=='HIGHEST':result=max(window)
                    elif kind=='LOWEST':result=min(window)
                    elif kind=='STDDEV':
                        mean=sum(window)/period;result=math.sqrt(sum((v-mean)**2 for v in window)/period)
                    else:result=sum(window)/period
                    series.append(result)
            self.metrics[n.id]=[series[i-int(p['shift'])] if i>=int(p['shift']) else None for i in range(len(series))]

    def evaluate(self,index:int,direction:int=0,*,first_entry=True,symbol='') -> Outcome:
        if direction not in (-1,0,1):raise ValueError('持仓方向必须为-1、0或1')
        if index<0 or index>=len(self.bars):return Outcome('WARMING','暂无已完成日线',self.program.required_bars,[])
        values={};trace=[];candidates=[];warming=index+1<self.program.required_bars
        for key in self.program.order:
            n=self.program.nodes[key];p=n.params
            args={port:values[e.source].get(e.sourcePort) for port,e in self.program.incoming[key].items()}
            status='READY';reason='已计算';output={};value=None
            if n.type=='MARKET':output={'bars':True};value={'bars':index+1,'asOf':self.bars[index].timestamp.isoformat()};reason='仅使用此时点及以前的已完成日线'
            elif n.type in ('PRICE','INDICATOR'):
                value=self.metrics[key][index];output={'value':value}
                if value is None:status,reason='WARMING','历史日线不足，等待指标预热'
            elif n.type=='CONSTANT':value=p['value'];output={'value':value}
            elif n.type=='POSITION':value=direction;output={'value':value};reason='-1为空头，0为空仓，1为多头'
            elif n.type in ('MATH','COMPARE'):
                a,b=args['left'],args['right']
                if a is None or b is None:status,reason='WARMING','上游数值尚未就绪'
                elif n.type=='COMPARE':
                    value={'GT':lambda:a>b,'GTE':lambda:a>=b,'LT':lambda:a<b,'LTE':lambda:a<=b,'EQ':lambda:a==b}[p['op']]()
                    status='PASS' if value else 'BLOCKED';reason='比较条件成立' if value else '比较条件未成立'
                else:
                    if p['op']=='DIV' and b==0:status,reason='ERROR','除数为0，本次不生成交易候选'
                    else:
                        value={'ADD':lambda:a+b,'SUB':lambda:a-b,'MUL':lambda:a*b,'DIV':lambda:a/b}[p['op']]()
                        if not math.isfinite(value) or abs(value)>1e18:value=None;status,reason='ERROR','运算结果超出有效范围'
                output={'result' if n.type=='COMPARE' else 'value':value}
            elif n.type=='LOGIC':
                if any(v is None for v in args.values()):status,reason='WARMING','上游条件尚未就绪'
                else:
                    value=not args['a'] if p['op']=='NOT' else args['a'] and args['b'] if p['op']=='AND' else args['a'] or args['b']
                    status='PASS' if value else 'BLOCKED';reason='逻辑条件成立' if value else '逻辑条件未成立'
                output={'result':value}
            elif n.type=='PRESET':
                from backtesting.strategy_signals import daily_signal
                result=daily_signal(p['strategy'],self.bars[:index+1],direction,symbol,first_entry=first_entry)
                value=result.signal;reason=result.reason
                if result.signal=='WARMING':status='WARMING';output={'buy':None,'sell':None,'close':None}
                else:output={'buy':result.signal=='BUY','sell':result.signal=='SELL','close':result.signal=='FLATTEN'}
            elif n.type=='RISK':value=dict(p);output={'risk':value};reason='固定手数；入场后按实际成交价和交割合约ATR保护'
            elif n.type=='ACTION':
                action=p['action'];eligible=direction==0 if action in ('BUY','SELL') else direction>0 if action=='CLOSE_LONG' else direction<0 if action=='CLOSE_SHORT' else direction!=0
                if warming or args['condition'] is None:status,reason='WARMING','等待完整的已知日线与上游条件'
                elif not eligible:status,reason='SKIPPED','当前持仓状态不适用此动作'
                elif not args['condition']:status,reason='BLOCKED','动作条件未成立'
                else:
                    value=action if action in ('BUY','SELL') else 'FLATTEN';candidates.append((value,n.label or n.id));status,reason='CANDIDATE','产生交易候选，实际成交仍由账本撮合'
            values[key]=output
            trace.append({'nodeId':key,'label':n.label or n.id,'type':n.type,'status':status,'value':value,'reason':reason})
        if warming:return Outcome('WARMING',f'工作流需要{self.program.required_bars}根已完成日线，当前{index+1}根',self.program.required_bars,trace)
        if any(row['status']=='ERROR' for row in trace):return Outcome('HOLD','节点运算不可用，本次未生成委托',self.program.required_bars,trace)
        signals={s for s,label in candidates}
        if 'FLATTEN' in signals:signal='FLATTEN'
        elif {'BUY','SELL'}<=signals:return Outcome('HOLD','多空候选同时成立，本次等待，不生成委托',self.program.required_bars,trace)
        elif signals:signal=next(iter(signals))
        else:return Outcome('HOLD','工作流未产生适合当前持仓的交易候选',self.program.required_bars,trace)
        labels=[label for s,label in candidates if s==signal]
        return Outcome(signal,('工作流候选：'+','.join(labels))[:230],self.program.required_bars,trace)

"""Post-validation FU diagnostic iteration; never treated as new untouched evidence."""
from copy import deepcopy
from backtesting.fuel_research import build
from backtesting.workflow import compile_workflow

MODES=('RANGE_GATE','REGIME_EXIT','SHOCK_PAUSE')
FAMILIES=('RANGE_REVERSION','BAND_REVERSION')

def regime_graph(family,mode,scale=1.):
    if family not in FAMILIES or mode not in MODES:raise ValueError('Unknown exploratory iteration')
    graph=deepcopy(build(family,scale));nodes=graph['nodes'];edges=graph['edges'];serial=0
    market=next(n['id'] for n in nodes if n['type']=='MARKET')
    def add(kind,params,inputs=()):
        nonlocal serial
        id='r'+str(serial);serial+=1
        nodes.append({'id':id,'type':kind,'label':kind+' regime','params':params})
        for port,source,out in inputs:
            edges.append({'id':'re'+str(len(edges)),'source':source,'sourcePort':out,'target':id,'targetPort':port})
        return id
    def indicator(kind,period):
        n=next((n for n in nodes if n['type']=='INDICATOR' and n['params']=={'kind':kind,'period':period,'field':'close','shift':0}),None)
        return n['id'] if n else add('INDICATOR',{'kind':kind,'period':period,'field':'close','shift':0},(('market',market,'bars'),))
    def math(op,a,b):return add('MATH',{'op':op},(('left',a,'value'),('right',b,'value')))
    def compare(op,a,b):return add('COMPARE',{'op':op},(('left',a,'value'),('right',b,'value')))
    def logical(op,a,b=None):
        return add('LOGIC',{'op':op},(('a',a,'result'),) if b is None else (('a',a,'result'),('b',b,'result')))
    atr=indicator('ATR',14);half=add('CONSTANT',{'value':.5})
    distance=math('SUB',indicator('SMA',20),indicator('SMA',60))
    threshold=math('MUL',atr,half)
    gate=compare('LTE',math('MUL',distance,distance),math('MUL',threshold,threshold))
    if mode=='SHOCK_PAUSE':
        cap=math('MUL',indicator('ATR',60),add('CONSTANT',{'value':1.25}))
        gate=logical('AND',gate,compare('LTE',atr,cap))
    invalid=logical('NOT',gate) if mode!='RANGE_GATE' else None
    actions=[n for n in nodes if n['type']=='ACTION']
    for n in actions:
        edge=next(e for e in edges if e['target']==n['id'] and e['targetPort']=='condition')
        old=edge['source']
        if n['params']['action'] in ('BUY','SELL'):
            edge['source']=logical('AND',old,gate)
        elif invalid is not None:
            edge['source']=logical('OR',old,invalid)
    return compile_workflow(graph).definition.model_dump()

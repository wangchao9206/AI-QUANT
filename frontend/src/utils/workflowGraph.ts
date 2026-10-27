import type {FlowGraph,FlowNode,NodeType} from '../services/workflows'
export type PortType='SERIES'|'NUMBER'|'BOOLEAN'|'RISK'
export const presetNames:Record<string,string>={MOMENTUM_BREAKOUT:'放量通道突破',BOLLINGER_REVERSAL:'布林均值回归',DUAL_THRUST:'区间突破',ADAPTIVE_CTA:'自适应趋势',HOLISTIC_14D:'日线融合',BUY_AND_HOLD:'买入持有'}
export interface ParamSpec {key:string;label:string;options?:Record<string,string>;min?:number;max?:number;step?:number}
export const specs:Record<NodeType,{name:string;color:string;hint:string;defaults:Record<string,string|number>;params:ParamSpec[]}> = {
 MARKET:{name:'已完成日线',color:'#4e8a80',hint:'所选品种、当前时点及以前的日线',defaults:{},params:[]},
 PRICE:{name:'价格 / 成交量',color:'#4e8a80',hint:'读取某一根已知日线的字段',defaults:{field:'close',shift:0},params:[]},
 INDICATOR:{name:'技术指标',color:'#5e7ca4',hint:'SMA、EMA、ATR、通道及标准差',defaults:{kind:'SMA',field:'close',period:20,shift:0},params:[]},
 CONSTANT:{name:'数值常量',color:'#89919c',hint:'比较阈值或算术系数',defaults:{value:0},params:[{key:'value',label:'数值',min:-1e9,max:1e9,step:.1}]},
 POSITION:{name:'当前持仓方向',color:'#89919c',hint:'多头 1 · 空仓 0 · 空头 -1',defaults:{},params:[]},
 MATH:{name:'数值运算',color:'#8b78a5',hint:'对两路数值进行加减乘除',defaults:{op:'MUL'},params:[{key:'op',label:'运算',options:{ADD:'加',SUB:'减',MUL:'乘',DIV:'除'}}]},
 COMPARE:{name:'数值比较',color:'#b78b49',hint:'比较左右两路数值，输出成立与否',defaults:{op:'GT'},params:[{key:'op',label:'条件',options:{GT:'左 > 右',GTE:'左 ≥ 右',LT:'左 < 右',LTE:'左 ≤ 右',EQ:'左 = 右'}}]},
 LOGIC:{name:'逻辑条件',color:'#b78b49',hint:'组合多个交易条件',defaults:{op:'AND'},params:[{key:'op',label:'逻辑',options:{AND:'同时成立 AND',OR:'任一成立 OR',NOT:'取反 NOT'}}]},
 PRESET:{name:'现有策略信号',color:'#5e7ca4',hint:'复用六种日线规则，可叠加自定义过滤',defaults:{strategy:'MOMENTUM_BREAKOUT'},params:[{key:'strategy',label:'规则',options:presetNames}]},
 RISK:{name:'仓位与保护',color:'#ac725b',hint:'统一固定手数、入场 ATR 止损止盈',defaults:{lots:1,stopLossAtr:2,takeProfitAtr:3},params:[{key:'lots',label:'开仓手数',min:1,max:1e6,step:1},{key:'stopLossAtr',label:'止损 ATR',min:.1,max:20,step:.1},{key:'takeProfitAtr',label:'止盈 ATR',min:.1,max:50,step:.1}]},
 ACTION:{name:'交易动作',color:'#b26766',hint:'条件成立后提交候选，由模拟账本撮合',defaults:{action:'BUY'},params:[{key:'action',label:'动作',options:{BUY:'开多',SELL:'开空',CLOSE_LONG:'平多',CLOSE_SHORT:'平空',FLATTEN:'平当前持仓'}}]},
}
const field={key:'field',label:'行情字段',options:{close:'收盘价',open:'开盘价',high:'最高价',low:'最低价',volume:'成交量'}}
const shift={key:'shift',label:'向前偏移（日线根数）',min:0,max:250,step:1}
specs.PRICE.params=[field,shift]
specs.INDICATOR.params=[{key:'kind',label:'指标',options:{SMA:'简单均线 SMA',EMA:'指数均线 EMA',ATR:'真实波幅 ATR',HIGHEST:'区间最高值',LOWEST:'区间最低值',STDDEV:'标准差'}},field,{key:'period',label:'周期',min:2,max:250,step:1},shift]
export const portLabels:Record<string,string>={bars:'日线',market:'日线',value:'数值',left:'左值',right:'右值',result:'条件',a:'条件 A',b:'条件 B',buy:'开多',sell:'开空',close:'平仓',condition:'触发条件',risk:'风控'}
export function ports(node:FlowNode):{inputs:Record<string,PortType>;outputs:Record<string,PortType>} {
 const inputs:Partial<Record<NodeType,Record<string,PortType>>>={PRICE:{market:'SERIES'},INDICATOR:{market:'SERIES'},PRESET:{market:'SERIES'},MATH:{left:'NUMBER',right:'NUMBER'},COMPARE:{left:'NUMBER',right:'NUMBER'},LOGIC:node.params.op==='NOT'?{a:'BOOLEAN'}:{a:'BOOLEAN',b:'BOOLEAN'},ACTION:{condition:'BOOLEAN',risk:'RISK'}}
 const outputs:Partial<Record<NodeType,Record<string,PortType>>>={MARKET:{bars:'SERIES'},PRICE:{value:'NUMBER'},INDICATOR:{value:'NUMBER'},CONSTANT:{value:'NUMBER'},POSITION:{value:'NUMBER'},MATH:{value:'NUMBER'},COMPARE:{result:'BOOLEAN'},LOGIC:{result:'BOOLEAN'},PRESET:{buy:'BOOLEAN',sell:'BOOLEAN',close:'BOOLEAN'},RISK:{risk:'RISK'}}
 return {inputs:inputs[node.type]??{},outputs:outputs[node.type]??{}}
}
export const clone=<T>(value:T):T=>JSON.parse(JSON.stringify(value))
let serial=0
export const uniqueId=(prefix='n')=>prefix+'_'+Date.now().toString(36)+'_'+(++serial)
export const makeNode=(type:NodeType,x=100,y=100):FlowNode=>({id:uniqueId(),type,label:specs[type].name,params:{...specs[type].defaults},x,y})
export function template(strategy='MOMENTUM_BREAKOUT'):FlowGraph {
 const market={...makeNode('MARKET',50,100),id:'market'},preset={...makeNode('PRESET',350,100),id:'preset',label:presetNames[strategy]??'策略信号',params:{strategy}},
 risk={...makeNode('RISK',350,420),id:'risk'}
 const actions=['BUY','SELL','FLATTEN'].map((action,i)=>({...makeNode('ACTION',710,30+i*195),id:'action'+i,label:action==='BUY'?'开多':action==='SELL'?'开空':'平仓',params:{action}}))
 return {schemaVersion:1,nodes:[market,preset,risk,...actions],edges:[{id:'e_market',source:'market',sourcePort:'bars',target:'preset',targetPort:'market'},...actions.flatMap((a,i)=>[{id:'e_signal'+i,source:'preset',sourcePort:['buy','sell','close'][i]!,target:a.id,targetPort:'condition'},{id:'e_risk'+i,source:'risk',sourcePort:'risk',target:a.id,targetPort:'risk'}])]}
}
export function customTemplate():FlowGraph {
 const graph=template();graph.nodes=graph.nodes.filter(n=>n.id!=='preset'&&n.id!=='action1'&&n.id!=='action2')
 const price={...makeNode('PRICE',330,50),id:'price'},sma={...makeNode('INDICATOR',330,260),id:'sma'},
 compare={...makeNode('COMPARE',630,130),id:'compare'}
 graph.nodes.find(n=>n.id==='risk')!.x=630;graph.nodes.find(n=>n.id==='risk')!.y=390
 graph.nodes.find(n=>n.id==='action0')!.x=940;graph.nodes.find(n=>n.id==='action0')!.y=150
 graph.nodes.push(price,sma,compare);graph.edges=[
 {id:'e1',source:'market',sourcePort:'bars',target:'price',targetPort:'market'},
 {id:'e2',source:'market',sourcePort:'bars',target:'sma',targetPort:'market'},
 {id:'e3',source:'price',sourcePort:'value',target:'compare',targetPort:'left'},
 {id:'e4',source:'sma',sourcePort:'value',target:'compare',targetPort:'right'},
 {id:'e5',source:'compare',sourcePort:'result',target:'action0',targetPort:'condition'},
 {id:'e6',source:'risk',sourcePort:'risk',target:'action0',targetPort:'risk'}]
 return graph
}
export function connect(graph:FlowGraph,source:string,sourcePort:string,target:string,targetPort:string):FlowGraph {
 const a=graph.nodes.find(n=>n.id===source),b=graph.nodes.find(n=>n.id===target)
 if(!a||!b||source===target)throw new Error('请选择不同节点的输出与输入端口')
 const out=ports(a).outputs[sourcePort],input=ports(b).inputs[targetPort]
 if(!out||out!==input)throw new Error('端口类型不同，请连接相同类型的端口')
 const remaining=graph.edges.filter(e=>!(e.target===target&&e.targetPort===targetPort))
 const seen=new Set<string>();function visit(id:string):boolean {if(id===source)return true;if(seen.has(id))return false;seen.add(id);return remaining.filter(e=>e.source===id).some(e=>visit(e.target))}
 if(visit(target))throw new Error('连线将产生循环，请调整方向')
 return {...graph,edges:[...remaining,{id:uniqueId('e'),source,sourcePort,target,targetPort}]}
}
export const traceValue=(value:unknown)=>value===null||value===undefined?'—':typeof value==='boolean'?(value?'成立':'不成立'):typeof value==='number'?Number(value.toFixed(4)).toString():typeof value==='object'?JSON.stringify(value):String(value)

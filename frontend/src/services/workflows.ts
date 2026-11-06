import {request,type BacktestRequest,type BacktestResult} from './api'
export type NodeType='MARKET'|'PRICE'|'INDICATOR'|'CONSTANT'|'POSITION'|'MATH'|'COMPARE'|'LOGIC'|'PRESET'|'RISK'|'ACTION'|'CHAN_SIGNAL'
export interface FlowNode {id:string;type:NodeType;label:string;params:Record<string,string|number>;x:number;y:number}
export interface FlowEdge {id:string;source:string;target:string;sourcePort:string;targetPort:string}
export interface FlowGraph {schemaVersion:1|2;nodes:FlowNode[];edges:FlowEdge[]}
export interface NodeTrace {nodeId:string;label:string;type:string;status:string;value:unknown;reason:string}
export interface WorkflowVersion {id:string;workflowId:string;version:number;name:string;sourceRevision:number;definition:FlowGraph;engineVersion:string;requiredBars:number;lots:number;stopLossAtr:number;takeProfitAtr:number}
export interface WorkflowSummary {id:string;name:string;description:string;revision:number;publishedVersion:number|null}
export interface WorkflowDraft extends WorkflowSummary {definition:FlowGraph;versions:WorkflowVersion[]}
export interface WorkflowCheck {definition:FlowGraph;engineVersion:string;requiredBars:number;nodeCount:number;risk:{lots:number;stopLossAtr:number;takeProfitAtr:number}}
export interface WorkflowDebug {signal:string;reason:string;historyCount:number;requiredBars:number;signalTime:string|null;nodeTrace:NodeTrace[];source:string;message:string}
export interface FrozenBar {timestamp:string;contract:string|null;open:number;high:number;low:number;close:number;volume:number}
export interface WorkflowEvidence extends WorkflowDebug {symbol:string;inputSnapshot:{signalBars:FrozenBar[]};observationKind:string}
export interface WorkflowShadow extends WorkflowEvidence {id:string;workflowVersionId:string;direction:number;recordedAt:string;inputHash:string;workflowDefinition:FlowGraph}
const base='/api/v1/paper/workflows'
const body=(value:unknown,method='POST')=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(value)})
export const workflowsApi={
 chanProfile:()=>request<Record<string,string>>(base+'/chan-profile'),
 observe:(id:string,value:{clientRequestId:string;symbol:string;asOf:string;direction:number})=>request<WorkflowShadow>(base+'/versions/'+encodeURIComponent(id)+'/shadows',body(value),180000),
 shadows:(id:string)=>request<WorkflowShadow[]>(base+'/versions/'+encodeURIComponent(id)+'/shadows'),
 shadow:(id:string)=>request<WorkflowShadow>(base+'/shadows/'+encodeURIComponent(id)),
 evidence:(session:string,asOf:string)=>request<WorkflowEvidence>('/api/v1/paper/sessions/'+encodeURIComponent(session)+'/strategy-evidence?'+new URLSearchParams({asOf})),
 list:()=>request<WorkflowSummary[]>(base),
 draft:(id:string)=>request<WorkflowDraft>(base+'/'+encodeURIComponent(id)),
 create:(value:{clientRequestId:string;name:string;description:string;definition:FlowGraph})=>request<WorkflowDraft>(base,body(value)),
 save:(id:string,value:{expectedRevision:number;name:string;description:string;definition:FlowGraph})=>request<WorkflowDraft>(base+'/'+encodeURIComponent(id),body(value,'PUT')),
 validate:(definition:FlowGraph)=>request<WorkflowCheck>(base+'/validate',body({definition})),
 publish:(id:string,expectedRevision:number,clientRequestId:string)=>request<WorkflowVersion>(base+'/'+encodeURIComponent(id)+'/publish',body({expectedRevision,clientRequestId})),
 versions:()=>request<WorkflowVersion[]>(base+'/versions'),
 version:(id:string)=>request<WorkflowVersion>(base+'/versions/'+encodeURIComponent(id)),
 debug:(definition:FlowGraph,symbol:string,asOf:string,direction:number)=>request<WorkflowDebug>(base+'/debug',body({definition,symbol,asOf,direction})),
 backtest:(id:string,value:BacktestRequest)=>request<BacktestResult>(base+'/versions/'+encodeURIComponent(id)+'/backtest',body(value),240000),
}

import {request,type BacktestRequest,type BacktestResult} from './api'
export type NodeType='MARKET'|'PRICE'|'INDICATOR'|'CONSTANT'|'POSITION'|'MATH'|'COMPARE'|'LOGIC'|'PRESET'|'RISK'|'ACTION'|'CHAN_SIGNAL'
export interface FlowNode {id:string;type:NodeType;label:string;params:Record<string,string|number>;x:number;y:number}
export interface FlowEdge {id:string;source:string;target:string;sourcePort:string;targetPort:string}
export interface FlowGraph {
  schemaVersion:1|2
  nodes:FlowNode[]
  edges:FlowEdge[]
  draftKind?:'MA_TREND_15M'
  maTrendExecution?:{takeProfitPct:number}
}
export interface NodeTrace {nodeId:string;label:string;type:string;status:string;value:unknown;reason:string}
export interface WorkflowVersion {id:string;workflowId:string;version:number;name:string;sourceRevision:number;definition:FlowGraph;engineVersion:string;requiredBars:number;lots:number;stopLossAtr:number;takeProfitAtr:number}
export interface WorkflowSummary {id:string;name:string;description:string;revision:number;publishedVersion:number|null}
export interface WorkflowDraft extends WorkflowSummary {definition:FlowGraph;versions:WorkflowVersion[]}
export interface WorkflowCheck {definition:FlowGraph;engineVersion:string;requiredBars:number;nodeCount:number;risk:{lots:number;stopLossAtr:number;takeProfitAtr:number}}
export interface MaTrendReviewFrame {
  at:string;openAt:string;tradingDate:string;open:number;high:number;low:number;close:number;volume:number
  equity:number;direction:number;lots:number;averagePrice:number|null;dailyTrigger:string|null;dailySignalDate:string|null
  minuteTrend:number;minuteMa20:number|null;signal:string;signalReason:string;executionIndexes:number[]
  pendingAction?:string|null;minuteMacdCross?:string|null;minuteDkx?:number|null;minuteMadkx?:number|null
}
export interface MaTrendReplay {
  scope:{first:string;last:string;scoreDays:number}
  metrics:{initialCash:number;endingEquity:number;netPnl:number;returnPct:number;maxDrawdownPct:number;entryCount:number;addCount:number;takeProfitCount:number;reversalCount:number;fees:number;slippageCost:number}
  executions:{at:string;signalAt:string|null;action:string;direction:number;lots:number;price:number;fee:number}[]
  assumptions:string[]
  reviewTimeline?:MaTrendReviewFrame[]
  reviewDatasetId?:string
  reviewRunId?:string
}
export interface WorkflowTrial {
  id:string;name:string;workflowVersionId:string;symbol:string;initialCash:number;costMultiplier:1|2;createdAt:string
}
export interface WorkflowTrialDetail {
  trial:WorkflowTrial;version:WorkflowVersion;replay:MaTrendReplay
}
export type CreateWorkflowTrial=Pick<WorkflowTrial,'name'|'workflowVersionId'|'symbol'|'initialCash'|'costMultiplier'> & {clientRequestId:string}
export interface WorkflowDebug {signal:string;reason:string;historyCount:number;requiredBars:number;signalTime:string|null;nodeTrace:NodeTrace[];source:string;message:string}
export interface FrozenBar {timestamp:string;contract:string|null;open:number;high:number;low:number;close:number;volume:number}
export interface WorkflowEvidence extends WorkflowDebug {symbol:string;inputSnapshot:{signalBars:FrozenBar[]};observationKind:string}
export interface WorkflowShadow extends WorkflowEvidence {id:string;workflowVersionId:string;direction:number;recordedAt:string;inputHash:string;workflowDefinition:FlowGraph}
const base='/api/v1/paper/workflows'
const trialsBase='/api/v1/paper/workflow-trials'
const body=(value:unknown,method='POST')=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(value)})
export const workflowTrialsApi={
  list:()=>request<WorkflowTrial[]>(trialsBase),
  get:(id:string)=>request<WorkflowTrialDetail>(trialsBase+'/'+encodeURIComponent(id)),
  create:(value:CreateWorkflowTrial)=>request<WorkflowTrialDetail>(trialsBase,body(value),180000),
}
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
 maTrendVersions:()=>request<WorkflowVersion[]>(base+'/versions/ma-trend'),
 version:(id:string)=>request<WorkflowVersion>(base+'/versions/'+encodeURIComponent(id)),
 debug:(definition:FlowGraph,symbol:string,asOf:string,direction:number)=>request<WorkflowDebug>(base+'/debug',body({definition,symbol,asOf,direction})),
 backtest:(id:string,value:BacktestRequest)=>request<BacktestResult>(base+'/versions/'+encodeURIComponent(id)+'/backtest',body(value),240000),
 maTrendReplay:(id:string,value:{symbol:string;initialCash:number;costMultiplier:1|2;includeTimeline?:boolean})=>request<MaTrendReplay>(base+'/versions/'+encodeURIComponent(id)+'/ma-trend-replay',body(value),180000),
}

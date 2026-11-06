import {request,type HistoryPoint} from './api'

export type LiveFrequency=15|30|60|180|300|900|'DAY'|'WEEK'|'MONTH'
export const LIVE_PERIODS=[{value:15,label:'15 秒'},{value:30,label:'30 秒'},{value:60,label:'1 分钟'},{value:180,label:'3 分钟'},{value:300,label:'5 分钟'},{value:900,label:'15 分钟'},{value:'DAY',label:'日线'},{value:'WEEK',label:'周线'},{value:'MONTH',label:'月线'}] as const
export interface IntradaySnapshot {
  symbol:string;seconds:number;period:string;source:string;dataStatus:'FRESH'|'CACHED'|'DEGRADED';dataTimestamp:string|null
  receivedAt:string;retrievedAt:string;connected:boolean;message:string;lastBarProvisional:boolean;points:HistoryPoint[]
}
export const liveApi={bars:(symbol:string,frequency:LiveFrequency)=>request<IntradaySnapshot>(`/api/v1/market/${encodeURIComponent(symbol)}/intraday?${typeof frequency==='number'?'seconds':'period'}=${frequency}&limit=600`)}

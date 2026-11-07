import type {LocationQuery,LocationQueryRaw} from 'vue-router'
import {LIVE_PERIODS,type LiveFrequency} from '../services/live'
import {validInstrument} from './marketNavigation'
export const contextUuid=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)?v.toLowerCase():''
export function contextPeriod(v:unknown):LiveFrequency|undefined {if(typeof v!=='string')return;return LIVE_PERIODS.find(p=>String(p.value)===v)?.value}
export function tradingQuery(q:LocationQuery,caseInPath=false){
 const errors:string[]=[];const symbol=q.symbol===undefined?'':validInstrument(q.symbol)
 if(q.symbol!==undefined&&!symbol)errors.push('合约参数无效，请重新选择。')
 const period=q.period??q.seconds;const frequency=period===undefined?60:contextPeriod(period)
 if(!frequency||q.period!==undefined&&q.seconds!==undefined&&String(q.period)!==String(q.seconds))errors.push('看盘周期参数无效或冲突，请重新选择。')
 for(const key of ['case','plan','monitor','session'] as const)if(q[key]!==undefined&&!contextUuid(q[key]))errors.push('关联标识参数无效，请核对原链接。')
 if(q.plan!==undefined&&q.case===undefined&&!caseInPath)errors.push('指定计划版本缺少档案标识。')
 if(q.mode!==undefined&&q.mode!=='LIVE'||q.asOf!==undefined)errors.push('当前行情入口不接受历史回放时点，请返回原档案或模拟账本。')
 const tab=q.tab??(q.monitor?'monitors':'futures')
 if(!['futures','options','monitors'].includes(String(tab))||typeof tab!=='string')errors.push('交易台页签参数无效。')
 return {symbol,frequency:frequency??60,tab:tab as 'futures'|'options'|'monitors',errors}
}
/** Changing a contract removes all prior object bindings; chart period changes alone do not. */
export function tradeSelection(q:LocationQuery,symbol:string,frequency:LiveFrequency,tab='futures',previousSymbol?:string):LocationQueryRaw {
 const next:LocationQueryRaw={...q,symbol:validInstrument(symbol),period:String(frequency),tab};delete next.seconds;delete next.mode;delete next.asOf
 const before=previousSymbol??validInstrument(q.symbol)
 if(before&&before!==validInstrument(symbol))for(const key of ['case','plan','decision','session','monitor','view','chain','option','side','lots','rate','dividend'])delete next[key]
 for(const key of ['case','plan','monitor','session'])if(next[key]!==undefined&&!contextUuid(next[key]))delete next[key]
 if(next.plan&&!next.case)delete next.plan
 return next
}
export function instrumentContextPath(path:string,q:LocationQuery,symbol:string,currentSymbol?:string){
 const before=validInstrument(currentSymbol)||validInstrument(q.symbol);const next:LocationQueryRaw={};if(contextPeriod(q.period??q.seconds))next.period=String(contextPeriod(q.period??q.seconds))
 if(before===validInstrument(symbol)){if(contextUuid(q.case))next.case=contextUuid(q.case);if(contextUuid(q.plan)&&next.case)next.plan=contextUuid(q.plan)}
 return {path,query:next}
}

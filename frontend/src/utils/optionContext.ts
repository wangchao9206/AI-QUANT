import type {LocationQuery,LocationQueryRaw} from 'vue-router'
import type {OptionChain} from '../types/options'
import {contextPeriod,contextUuid,tradingQuery} from './tradingContext'

export function optionFuture(chain:OptionChain|undefined):string {
  if(!chain||chain.underlyingType!=='FUTURE')return ''
  const parts=chain.underlyingSymbol.split('.'),symbol=parts.at(-1)?.toUpperCase()??''
  if(parts.length>2||parts.length===2&&parts[0]!==chain.exchange)return ''
  return /^[A-Z]{1,4}\d{3,4}$/.test(symbol)?symbol:''
}
export function optionQuery(q:LocationQuery){
  const base=tradingQuery(q),errors=[...base.errors]
  const identifier=(key:'chain'|'option',pattern:RegExp)=>{
    const value=q[key];if(value===undefined)return ''
    if(typeof value!=='string'||!pattern.test(value)){errors.push('期权链或合约参数无效。');return ''}return value
  }
  const chain=identifier('chain',/^[A-Za-z0-9_.:+-]{1,250}$/),option=identifier('option',/^[A-Za-z0-9_.-]{1,128}$/)
  if(option&&!chain)errors.push('指定期权合约时必须同时指定期权链。')
  if(base.symbol&&!/^[A-Z]{1,4}\d{3,4}$/.test(base.symbol))errors.push('专业期权深链需要实际交割月，请先选择期货月份或直接选择期权链。')
  const numeric=(key:string,fallback:number,min:number,max:number)=>{
    const raw=q[key];if(raw===undefined)return fallback
    if(typeof raw!=='string'||raw.length>32||! /^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw)||!Number.isFinite(Number(raw))||Number(raw)<min||Number(raw)>max){errors.push('期权情景或估值参数无效。');return fallback}return Number(raw)
  }
  const lots=numeric('lots',1,1,10000),rate=numeric('rate',.02,-.1,.5),dividend=numeric('dividend',0,0,.5)
  if(!Number.isInteger(lots))errors.push('期权情景手数必须为整数。')
  const side=q.side??'BUY';if(side!=='BUY'&&side!=='SELL')errors.push('期权情景买卖方向无效。')
  return {...base,chain,option,lots,rate,dividend,side:side==='SELL'?'SELL' as const:'BUY' as const,errors}
}
/** The selected catalog chain, not a product prefix, determines the actual futures month. */
export function optionSelection(q:LocationQuery,chain:OptionChain|undefined,option='',side:'BUY'|'SELL'='BUY',lots=1,rate=.02,dividend=0):LocationQueryRaw {
  const next:LocationQueryRaw={period:String(contextPeriod(q.period??q.seconds)??60),side,lots:String(lots),rate:String(rate),dividend:String(dividend)}
  if(chain){next.chain=chain.id;const symbol=optionFuture(chain);if(symbol){next.symbol=symbol;if(typeof q.symbol==='string'&&q.symbol.toUpperCase()===symbol&&contextUuid(q.case)){next.case=contextUuid(q.case);if(contextUuid(q.plan))next.plan=contextUuid(q.plan)}}}
  if(option&&chain)next.option=option
  return next
}
export function optionReference(q:LocationQuery,symbol:string):LocationQueryRaw {
  const parsed=optionQuery(q)
  if(parsed.errors.length||parsed.symbol!==symbol||!parsed.chain)return {}
  return {chain:parsed.chain,...parsed.option?{option:parsed.option}:{},side:parsed.side,lots:String(parsed.lots),rate:String(parsed.rate),dividend:String(parsed.dividend)}
}

import {request} from '../services/api'
import {currentScope} from './storageScope'

export const TRINITY_NAME = '自研道氏-威科夫-缠论三位一体'
export const TRINITY_STRATEGY_ID = 'PERSONAL_TRINITY'
export const TRINITY_SYMBOLS = [
  {value:'FG701', label:'玻璃 FG701'},
  {value:'SA701', label:'纯碱 SA701'},
  {value:'AP701', label:'苹果 AP701'},
  {value:'CJ701', label:'红枣 CJ701'},
] as const

export interface TrinityConfig {
  fastPeriod:number
  mediumPeriod:number
  slowPeriod:number
  convergenceDays:number
  entryMinutes:15|30|60
  confirmation:'chan'|'wyckoff'|'either'
  addMode:'MINUTE_ADD'|'MA10_ADD'|'NONE'
  waitTradingDays:number
  symbol:typeof TRINITY_SYMBOLS[number]['value']
  costMultiplier:1|2
}

export interface TrinityDraft {id:string;name:string;config:TrinityConfig}
export type TrinityPaperConfig = Omit<TrinityConfig,'symbol'|'costMultiplier'>

export interface TrinityResult {
  symbol:TrinityConfig['symbol']
  scope:{first:string;last:string;scoreDays:number}
  metrics:{netPnl:number;returnPct:number;maxDrawdownPct:number;primaryOpens:number;addOpens:number;closedTrades:number}
  trades:{slot:number;direction:number;entryAt:string;exitAt:string;entryPrice:number;exitPrice:number;netPnl:number;
    exitReason?:string;originTrigger?:string}[]
}

export const TRINITY_DEFAULT:Readonly<TrinityConfig> = Object.freeze({
  fastPeriod:5, mediumPeriod:10, slowPeriod:20, convergenceDays:3,
  entryMinutes:15, confirmation:'either', addMode:'MINUTE_ADD', waitTradingDays:10,
  symbol:'FG701', costMultiplier:2,
})

const STORAGE_KEY = 'aiquant.personal-trinity.v1'
const PAPER_LAUNCH_KEY = 'aiquant.trinity-paper-launch.v1'
const FORMAT = 'aiquant.personal-trinity'
const CONFIG_KEYS = Object.keys(TRINITY_DEFAULT)
const MAX_NAME_LENGTH = 120

function isRecord(value:unknown):value is Record<string,unknown> {
  return typeof value==='object' && value!==null && !Array.isArray(value)
}

function integerBetween(value:unknown, min:number, max:number):value is number {
  return typeof value==='number' && Number.isInteger(value) && value>=min && value<=max
}

export function validateTrinity(value:unknown):string|null {
  if(!isRecord(value) || Object.keys(value).length!==CONFIG_KEYS.length || CONFIG_KEYS.some(key=>!Object.hasOwn(value,key))) {
    return '策略参数不完整或含未知字段。'
  }
  const {fastPeriod,mediumPeriod,slowPeriod,convergenceDays,entryMinutes,confirmation,addMode,waitTradingDays,symbol,costMultiplier}=value
  if(!integerBetween(fastPeriod,2,120)||!integerBetween(mediumPeriod,2,120)||!integerBetween(slowPeriod,2,120)
     ||!(fastPeriod<mediumPeriod&&mediumPeriod<slowPeriod)) return '均线周期须为 2–120 的整数，并且快线小于中线、中线小于慢线。'
  if(!integerBetween(convergenceDays,2,20)) return '收敛天数须为 2–20 的整数。'
  if(!integerBetween(waitTradingDays,1,40)) return '确认等待须为 1–40 个交易日。'
  if(entryMinutes!==15&&entryMinutes!==30&&entryMinutes!==60) return '请选择 15、30 或 60 分钟。'
  if(confirmation!=='chan'&&confirmation!=='wyckoff'&&confirmation!=='either') return '请选择缠论、威科夫或任一确认。'
  if(addMode!=='MINUTE_ADD'&&addMode!=='MA10_ADD'&&addMode!=='NONE') return '请选择有效的加仓规则。'
  if(!TRINITY_SYMBOLS.some(item=>item.value===symbol)) return '请选择已有核验行情的实际交割合约。'
  if(costMultiplier!==1&&costMultiplier!==2) return '请选择基准或双倍成本。'
  return null
}

function draftValue(value:unknown):TrinityDraft {
  if(!isRecord(value) || typeof value.id!=='string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(value.id)
     || typeof value.name!=='string' || !value.name.trim() || value.name.trim().length>MAX_NAME_LENGTH) {
    throw new Error('策略副本须包含有效名称和编号。')
  }
  const error=validateTrinity(value.config)
  if(error) throw new Error(error)
  return {id:value.id,name:value.name.trim(),config:{...value.config as TrinityConfig}}
}

function scopedKey() {
  const scope=currentScope()
  if(!scope) throw new Error('登录后可在本浏览器保存策略副本。')
  return `${STORAGE_KEY}:${scope}`
}

function readDrafts(key:string):TrinityDraft[] {
  const raw=localStorage.getItem(key)
  if(raw===null) return []
  try {
    const parsed:unknown=JSON.parse(raw)
    if(!isRecord(parsed)||parsed.version!==1||!Array.isArray(parsed.drafts)) throw new Error()
    const drafts=parsed.drafts.map(draftValue)
    if(new Set(drafts.map(draft=>draft.id)).size!==drafts.length) throw new Error()
    return drafts
  } catch {
    throw new Error('本浏览器的策略副本读取失败，原记录已保留。')
  }
}

export function loadTrinityDrafts():TrinityDraft[] {
  return currentScope() ? readDrafts(scopedKey()) : []
}

export function persistTrinityDrafts(drafts:TrinityDraft[]) {
  const key=scopedKey()
  readDrafts(key)
  const validated=drafts.map(draftValue)
  if(new Set(validated.map(draft=>draft.id)).size!==validated.length) throw new Error('策略副本编号重复。')
  localStorage.setItem(key,JSON.stringify({version:1,drafts:validated}))
}

export function exportTrinity(draft:TrinityDraft):string {
  return JSON.stringify({format:FORMAT,version:1,draft:draftValue(draft)},null,2)
}

export function importTrinity(raw:string):TrinityDraft {
  let value:unknown
  try { value=JSON.parse(raw) } catch { throw new Error('请选择有效的 JSON 策略文件。') }
  if(!isRecord(value)||value.format!==FORMAT||value.version!==1) throw new Error('策略文件格式或版本不受支持。')
  return draftValue(value.draft)
}

export function isTrinityPaperContract(contract:string):boolean {
  return /^(FG|SA|AP|CJ)\d{3,4}$/.test(contract)
}

export function trinityPaperConfig(config:TrinityConfig):TrinityPaperConfig {
  const {fastPeriod,mediumPeriod,slowPeriod,convergenceDays,entryMinutes,confirmation,addMode,waitTradingDays} = config
  return {fastPeriod,mediumPeriod,slowPeriod,convergenceDays,entryMinutes,confirmation,addMode,waitTradingDays}
}

export function stageTrinityPaperLaunch(draft:TrinityDraft) {
  const scope=currentScope()
  if(!scope) throw new Error('登录后可将当前参数带到模拟盘。')
  const validated=draftValue(draft)
  sessionStorage.setItem(`${PAPER_LAUNCH_KEY}:${scope}`,JSON.stringify(validated))
  return validated.id
}

export function readTrinityPaperLaunch(id:unknown):TrinityDraft|null {
  const scope=currentScope()
  if(!scope||typeof id!=='string')return null
  try {
    const raw=sessionStorage.getItem(`${PAPER_LAUNCH_KEY}:${scope}`)
    if(!raw)return null
    const draft=draftValue(JSON.parse(raw))
    return id===draft.id?draft:null
  } catch {
    return null
  }
}

export function backtestTrinity(config:TrinityConfig):Promise<TrinityResult> {
  const error=validateTrinity(config)
  if(error) return Promise.reject(new Error(error))
  return request<TrinityResult>('/api/v1/research/personal-trinity/backtest',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config),
  },60000)
}

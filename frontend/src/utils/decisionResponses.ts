import type {DecisionCase} from '../services/decisions'
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)
const summary=(v:unknown)=>object(v)&&typeof v.id==='string'&&!!v.id&&typeof v.symbol==='string'&&typeof v.version==='number'&&object(v.origin)&&(typeof v.origin.id==='string'||typeof v.origin.id==='number')&&typeof v.origin.label==='string'

/** Do not commit an API envelope to the detail state before checking its shape. */
export function decisionDetail(value:unknown,id:string):DecisionCase {
 if(!summary(value)||!object(value)||value.id!==id||!Array.isArray(value.plans)||!Array.isArray(value.reviews)||!Array.isArray(value.paper)||!value.plans.every(p=>object(p)&&typeof p.id==='string'&&typeof p.version==='number'&&object(p.fields))||!value.reviews.every(object)||!value.paper.every(object)||value.sources!==undefined&&(!Array.isArray(value.sources)||!value.sources.every(s=>object(s)&&['SERVER_CALC','LOCAL_IMPORT'].includes(String(s.kind))&&object(s.snapshot)&&(s.kind!=='LOCAL_IMPORT'||object(s.snapshot.plan)))))throw new Error('档案详情数据结构异常，请重新载入；原记录不会被覆盖。')
 return value as unknown as DecisionCase
}
export function decisionPage(value:unknown):{items:DecisionCase[];total:number} {
 if(!object(value)||!Array.isArray(value.items)||!value.items.every(summary)||typeof value.total!=='number'||!Number.isSafeInteger(value.total)||value.total<0)throw new Error('档案列表数据结构异常，请重新载入。')
 return {items:value.items as DecisionCase[],total:value.total}
}

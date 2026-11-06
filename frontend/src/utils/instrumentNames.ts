import {reactive} from 'vue'
import observedNames from '../data/instrumentNames.json'

// Observed domestic catalog snapshot, 2026-11-06. New catalog entries update it at runtime.
const preferred:Record<string,string>={RB:'螺纹钢',TA:'精对苯二甲酸',V:'聚氯乙烯',T:'10年期国债',TF:'5年期国债',TS:'2年期国债',TL:'30年期国债',IF:'沪深300股指',IH:'上证50股指',IC:'中证500股指',IM:'中证1000股指',IO:'沪深300股指',HO:'上证50股指',MO:'中证1000股指'}
const roots=reactive<Record<string,string>>({...observedNames,...preferred})
const exact=reactive(new Map<string,string>())
const chinese=(value:unknown):value is string=>typeof value==='string'&&/[\u3400-\u9fff]/.test(value)
const normalize=(symbol:string)=>symbol.trim().replace(/^KQ\.m@[A-Z]+\.([a-z]+)$/i,(_,root:string)=>root+'M').replace(/^[A-Z]+\./i,'').toUpperCase()
const indices:Record<string,string>={'000300':'沪深300指数','000016':'上证50指数','000852':'中证1000指数','399300':'沪深300指数'}

export function productName(root:string,hint?:string):string{
  const key=root.trim().toUpperCase()
  return preferred[key]??(chinese(hint)?hint:roots[key])??'未命名品种'
}

/** Chinese presentation only. Never use this result as a request, route or order identifier. */
export function instrumentName(symbol?:string|null,hint?:string):string{
  if(!symbol)return chinese(hint)?hint:'未选择合约'
  const key=normalize(symbol)
  const registered=exact.get(key)
  if(registered)return registered
  if(indices[key])return indices[key]!
  const option=/^([A-Z]{1,4})(\d{3,4})-?([CP])-?(\d+(?:\.\d+)?)$/.exec(key)
  if(option){
    const [,root,month,side,strike]=option
    const name=roots[root!]??(chinese(hint)?hint:'未命名品种')
    return `${name}${month}${side==='C'?'认购':'认沽'}期权 · 行权价${strike}`
  }
  const future=/^([A-Z]{1,4})(\d{3,4})$/.exec(key)
  if(future)return `${roots[future[1]!]??(chinese(hint)?hint:'未命名品种')}${future[2]}合约`
  const continuous=/^([A-Z]{1,4})(?:M|0)$/.exec(key)
  if(continuous&&roots[continuous[1]!])return `${roots[continuous[1]!]}主连`
  if(roots[key])return roots[key]!
  return chinese(hint)?hint:/-?(?:CALL|PUT|C|P)-?\d/i.test(key)?'未命名期权合约':'未命名合约'
}

export function instrumentLabel(symbol?:string|null,hint?:string):string{
  const name=instrumentName(symbol,hint)
  return symbol?`${name}（${symbol}）`:name
}

export function registerInstrumentCatalog(catalog:{exchanges:{instruments:{rootSymbol:string;name:string}[]}[]}):void{
  for(const group of catalog.exchanges)for(const item of group.instruments){
    const name=productName(item.rootSymbol,item.name)
    if(name!=='未命名品种')roots[item.rootSymbol.toUpperCase()]=name
    item.name=name
  }
}

export function registerOptionNames(data:{chain?:{underlyingSymbol:string};contracts?:{symbol:string;name:string;optionClass:string;strike:number}[]}):void{
  for(const row of data.contracts??[]){
    let name=instrumentName(row.symbol,row.name)
    // Metadata resolves newly listed product roots before a futures catalog refresh.
    if(name.startsWith('未命名品种')&&data.chain){
      name=`${instrumentName(data.chain.underlyingSymbol)}${row.optionClass==='CALL'?'认购':'认沽'}期权 · 行权价${row.strike}`
    }
    exact.set(normalize(row.symbol),name)
  }
}

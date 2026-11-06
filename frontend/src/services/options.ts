import {request,readSnapshot} from './api'
import type {OptionCatalog,OptionChainSnapshot,OptionScenario,OptionChain,OptionContract,OptionQuote} from '../types/options'
import type {MarketMicrostructure} from './api'
import type {IntradaySnapshot,LiveFrequency} from './live'
import {registerOptionNames} from '../utils/instrumentNames'
export interface LinkedOptions extends OptionCatalog {requestedFuture:string;resolvedFuture:string|null}
export interface LiveOptionChain {chain:OptionChain;contracts:Omit<OptionContract,'risk'>[];underlying:OptionQuote;dataStatus:string;message:string;source:string;retrievedAt:string}
export interface OptionDepth extends MarketMicrostructure {contract:Omit<OptionContract,'risk'>;message:string}
const base='/api/v1/options'
export const optionsApi={
  catalog:()=>readSnapshot<OptionCatalog>(`${base}/catalog`),
  linked:(future:string)=>readSnapshot<LinkedOptions>(`${base}/linked?${new URLSearchParams({future})}`),
  contracts:async(chainId:string)=>{const data=await readSnapshot<LiveOptionChain>(`${base}/contracts?${new URLSearchParams({chainId})}`);registerOptionNames(data);return data},
  depth:(symbol:string)=>readSnapshot<OptionDepth>(`${base}/depth?${new URLSearchParams({symbol})}`),
  chart:(symbol:string,frequency:LiveFrequency)=>readSnapshot<IntradaySnapshot>(`${base}/chart?${new URLSearchParams({symbol,[typeof frequency==='number'?'seconds':'period']:String(frequency),limit:'600'})}`),
  chain:async(chainId:string,rate:number,dividend:number)=>{const data=await readSnapshot<OptionChainSnapshot>(`${base}/chain?${new URLSearchParams({chainId,rate:String(rate),dividend:String(dividend)})}`);registerOptionNames(data);return data},
  scenario:(body:{chainId:string;symbol:string;side:'BUY'|'SELL';lots:number})=>request<OptionScenario>(`${base}/scenario`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
}

export type OptionStatus = 'FRESH' | 'CACHED' | 'WARMING' | 'UNAVAILABLE'
export interface OptionChain {
  id:string; exchange:string; underlyingSymbol:string; underlyingType:'FUTURE'|'INDEX'
  expiry:string; product:string; contractCount:number
}
export interface OptionCatalog {source:string;dataStatus:OptionStatus;dataTimestamp:string|null;message:string;chains:OptionChain[]}
export interface OptionQuote {
  lastPrice?:number|null;bidPrice?:number|null;askPrice?:number|null;bidVolume?:number|null;askVolume?:number|null
  volume?:number|null;openInterest?:number|null;dataTimestamp?:string|null;dataStatus:OptionStatus
}
export interface OptionRisk {
  referencePrice:number|null;priceBasis:'MID'|'LAST'|null;priceNote:string|null;spread:number|null
  intrinsicValue:number|null;timeValue:number|null;iv:number|null;delta:number|null;gamma:number|null
  theta:number|null;vega:number|null;model:'BLACK_76'|'BSM';approximation:boolean;valuationTimestamp:string|null
  riskStatus:'AVAILABLE'|'EUROPEAN_APPROXIMATION'|'UNAVAILABLE';riskReason:string
}
export interface OptionContract extends OptionQuote {
  symbol:string;name:string;optionClass:'CALL'|'PUT';strike:number;expiry:string
  exerciseType:'A'|'E'|null;volumeMultiple:number|null;priceTick:number|null;risk:OptionRisk
}
export interface OptionChainSnapshot {
  chain:OptionChain;underlying:OptionQuote;contracts:OptionContract[];source:string;dataStatus:OptionStatus;message:string
  retrievedAt:string;assumptions:{rate:number;dividend:number;yearBasis:string;rateSource:string;greekUnits:string}
}
export interface OptionScenario {
  symbol:string;side:'BUY'|'SELL';lots:number;referencePrice:number;priceBasis:'MID'|'LAST';priceNote:string|null
  volumeMultiple:number;premiumAmount:number;breakeven:number|null;maxLoss:number|null;maxProfit:number|null
  unlimitedLoss:boolean;unlimitedProfit:boolean;points:{underlyingPrice:number;pnl:number}[];note:string
  dataTimestamp:string|null;underlyingTimestamp:string|null;dataStatus:OptionStatus;underlyingStatus:OptionStatus
}

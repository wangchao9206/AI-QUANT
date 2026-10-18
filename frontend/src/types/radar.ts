export interface RadarBase {
  status:'READY'|'PARTIAL'|'DEGRADED'|'UNAVAILABLE'
  source?:string;dataTimestamp:string|null;message?:string
}
export interface MarketRadarItem {
  symbol:string;name:string;exchange:string;sector:string;contract:string|null
  price:number;changePct:number;volume:number;openInterest:number
  dataTimestamp:string;dataStatus:'FRESH'|'CACHED'|'DEGRADED'
}
export interface MarketRadar extends RadarBase {
  catalogCount:number;observedCount:number;missingCount:number;connected:boolean
  breadth:{up:number;down:number;flat:number};items:MarketRadarItem[]
  sectors:{name:string;count:number;up:number;down:number;averageChange:number}[]
}
export interface NewsRadarItem {
  id:string;title:string;summary:string;url:string;publisher:string;publishedAt:string
  relatedSymbols:string[];topic:string;timePrecision?:'MINUTE'|'DAY'
  sourceId?:string;sourceTier?:'PRIMARY'|'SECONDARY';sourceStatus?:string;fetchedAt?:string
  interpretationBasis?:string;verificationStatus?:string;eventTypes?:string[]
  analysis?:{eventType:string;chain:string;conditions:string;checks:string[]}[]
}
export interface NewsSource {id:string;name:string;tier:string;url:string;scope:string;status:string;fetchedAt:string|null;latestPublishedAt?:string;itemCount:number;message:string}
export interface NewsRadar extends RadarBase {items:NewsRadarItem[];sources?:NewsSource[];fetchedAt?:string}
export interface EventSource {title:string;publisher:string;url:string;publishedDate:string;precision:string;role:string;note?:string}
export interface EventCase {
  id:string;title:string;sector:string;eventDate:string;role:string;relatedSymbols:string[]
  facts:string;chain:string;earliestStatus:string;limitation:string;use:string
  checks:string[];sources:EventSource[]
  windows?:{symbol:string;status:string;baselineDate?:string;baselineClose?:number;before20Pct?:number|null;after5Pct?:number|null;after20Pct?:number|null;after5Date?:string|null;after20Date?:string|null}[]
}
export interface EventStudy {scope:string;methodology:string;items:EventCase[];watchSources:{name:string;url:string;scope:string;collection:string}[];generatedAt:string}
export interface StrategyRadarItem {
  id:string;strategy:string;signal:'BUY'|'SELL';symbol:string;name:string;sector:string
  close:number;changePct:number;dataTimestamp:string;source:string;reason:string
  lower:number;upper:number;volumeRatio?:number
}
export interface SignalRadar extends RadarBase {
  scannedCount:number;universeCount:number;missingCount:number;items:StrategyRadarItem[]
  groups:{id:string;name:string;rule:string;matched:number;long:number;short:number}[]
}
export interface OverseasRadarItem {
  symbol:string;name:string;unit:string;sector:string;price:number;changePct:number
  dataTimestamp:string;dataStatus:'FRESH'|'CACHED';relatedSymbols:string[];sourceUrl:string
}
export interface OverseasRadar extends RadarBase {items:OverseasRadarItem[];missing?:string[]}

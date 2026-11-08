/** Synthetic UI/test inputs, never imported by application code or treated as observed market data. */
import type {MultiframeRun,MultiframeFrame} from './multiframe'
export const observationFixtureId='20000000-0000-4000-8000-000000000001'
export const structureFixtureId='a'.repeat(24)
export function observationFixture(symbol='RB2701',id=observationFixtureId):MultiframeRun {
 const frame=(frequency:'MIN30'|'MIN5'):MultiframeFrame=>{
  const step=(frequency==='MIN30'?30:5)*60000,start=Date.parse('2026-10-30T01:00:00Z')
  const bars=Array.from({length:50},(_,i)=>({index:i,providerIndex:i,date:'2026-10-30',timestamp:new Date(start+i*step).toISOString(),sealedByTimestamp:new Date(start+(i+1)*step).toISOString(),contract:symbol,open:3000+i,high:3002+i,low:2999+i,close:3001+i,volume:100}))
  const structure={id:structureFixtureId,type:'BI' as const,startIndex:1,endIndex:20,direction:'UP' as const,startPrice:3000,endPrice:3020,revision:1,engineConfirmed:false,rawFlag:'SYNTHETIC_DYNAMIC',firstObservedDate:bars[21]!.timestamp,engineConfirmedDate:null,eligibleAt:null,pivotStartDate:bars[1]!.timestamp,pivotEndDate:bars[20]!.timestamp,observedAsOfDate:bars[49]!.timestamp,state:'CURRENT'}
  return {frequency,source:{receiptAt:'2026-11-01T12:00:00Z',source:'SYNTHETIC_FIXTURE',status:'CACHED'},analysis:{symbol,frequency,priceBasis:'UNADJUSTED_DELIVERY',profileHash:'fixture-profile',inputHash:'fixture-input',observedBars:50,observedAsOfDate:bars[49]!.timestamp,bars,structures:[structure]},lastSealedBy:bars[49]!.sealedByTimestamp,firstProviderIndex:0,lastProviderIndex:49,sourceWindowBars:51,sourceWindowStart:bars[0]!.timestamp}
 }
 return {id,status:'SUCCEEDED',error:null,createdAt:'2026-11-02T00:00:00Z',request:{clientRequestId:id,symbol,frames:'PAIR',asOf:null},report:{configHash:'fixture-config',capturedAt:'2026-11-01T12:00:00Z',asOf:'2026-10-31T03:00:00Z',config:{symbol,mode:'HISTORICAL_SUCCESSOR_BOUND_RECONSTRUCTION',priceBasis:'UNADJUSTED_DELIVERY'},frames:[frame('MIN30'),frame('MIN5')],executable:false,limitations:['合成测试夹具；历史重建不冒充当时已收到的行情。']}}
}

import {describe,it,expect} from 'vitest'
import {validatePreferences,validatePrivateChart,type PrivateChart} from './workspaceContent'
const chart=():PrivateChart=>({schemaVersion:1,layout:{theme:'dark',mainType:'candle',subChart:'vol',maPeriods:[5,20,180],autoGroups:['TREND']},items:[{id:'line-1',kind:'LINE',anchors:[{timestamp:'2026-11-06T09:00:00+08:00',price:3000},{timestamp:'2026-11-06T09:15:00+08:00',price:3005}]}]})
describe('private chart wire format',()=>{
 it('retains original timestamp offsets and price anchors exactly',()=>{const original=chart();expect(validatePrivateChart(original)).toEqual(original)})
 it('rejects account metadata and unknown preference values',()=>{expect(()=>validatePreferences({schemaVersion:1,experience:'ADMIN'})).toThrow();expect(()=>validatePreferences({schemaVersion:1,experience:'PRO',ownerId:'other'})).toThrow()})
 it('rejects prototype drawing kinds and duplicate IDs',()=>{const value=chart();(value.items[0] as unknown as {kind:string}).kind='toString';expect(()=>validatePrivateChart(value)).toThrow();const duplicate=chart();duplicate.items.push(duplicate.items[0]!);expect(()=>validatePrivateChart(duplicate)).toThrow()})
 it('rejects missing offsets, invalid prices and coincident first two anchors',()=>{for(const change of ['offset','price','time']){const value=chart(),a=value.items[0]!.anchors;if(change==='offset')a[0]!.timestamp='2026-11-06T09:00:00';if(change==='price')a[0]!.price=NaN;if(change==='time')a[1]!.timestamp='2026-11-06T01:00:00Z';expect(()=>validatePrivateChart(value)).toThrow()}})
 it('rejects unsupported or duplicate moving averages and extra layout fields',()=>{const value=chart();value.layout.maPeriods=[5,5];expect(()=>validatePrivateChart(value)).toThrow();expect(()=>validatePrivateChart({...chart(),layout:{...chart().layout,leverage:100}})).toThrow()})
 it('rejects incomplete channels and more than 100 drawings',()=>{const value=chart();value.items[0]!.kind='CHANNEL';expect(()=>validatePrivateChart(value)).toThrow();const many=chart();many.items=Array.from({length:101},(_,i)=>({...chart().items[0]!,id:'line-'+i}));expect(()=>validatePrivateChart(many)).toThrow()})
})

import type {HistoryPoint} from '../services/api'

/** MID=(3C+O+H+L)/6; 20-period linear weights 20..1; signal=SMA(DKX,10). */
export function dkxIndicator(points:readonly HistoryPoint[]){
 const result:{dkx:number|null;madkx:number|null}[]=[]
 const mids:number[]=[]
 let first=0
 for(let i=0;i<points.length;i++){
  const p=points[i]!
  if(i&&p.contract!==points[i-1]!.contract)first=i
  const valid=[p.price,p.open,p.high,p.low].every(v=>typeof v==='number'&&Number.isFinite(v))
  mids.push(valid?(3*p.price+p.open!+p.high!+p.low!)/6:NaN)
  if(!valid)first=i+1
  let dkx:number|null=null,madkx:number|null=null
  if(i-first>=19){let sum=0;for(let j=0;j<20;j++)sum+=(20-j)*mids[i-j]!;dkx=sum/210}
  result.push({dkx,madkx})
  if(i-first>=28){const window=result.slice(i-9,i+1);if(window.every(v=>v.dkx!=null))madkx=window.reduce((sum,v)=>sum+v.dkx!,0)/10}
  result[i]!.madkx=madkx
 }
 return result
}

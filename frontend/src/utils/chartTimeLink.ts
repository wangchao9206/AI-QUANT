export interface TimeWindow {start:string;end:string}
export function lastTimeAtOrBefore<T>(items:readonly T[],timestamp:string,time:(item:T)=>string):number|null {
  const cutoff=Date.parse(timestamp)
  if(!Number.isFinite(cutoff)||!items.length)return null
  let left=0,right=items.length-1,found:number|null=null
  while(left<=right){const middle=(left+right)>>1,value=Date.parse(time(items[middle]!));if(!Number.isFinite(value))return null;if(value<=cutoff){found=middle;left=middle+1}else right=middle-1}
  return found
}
export function timeWindowIndices<T>(items:readonly T[],window:TimeWindow,time:(item:T)=>string):{start:number;end:number}|null {
  const end=lastTimeAtOrBefore(items,window.end,time)
  if(end===null)return null
  const prior=lastTimeAtOrBefore(items,window.start,time)
  const start=Math.min(end,prior??0)
  return {start,end:end+1}
}

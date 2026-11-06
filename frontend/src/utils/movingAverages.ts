export const MA_PERIODS=[5,10,20,60,180] as const
export type MaPeriod=typeof MA_PERIODS[number]
export const MA_COLORS:Record<MaPeriod,string>={5:'#facc15',10:'#38bdf8',20:'#f43f5e',60:'#86d48b',180:'#c4a0ed'}

/** A full window of finite closes is required; unavailable values remain gaps. */
export function movingAverages(prices:readonly number[]){
  const result={} as Record<MaPeriod,(number|null)[]>
  for(const period of MA_PERIODS){
    let sum=0,missing=0
    result[period]=prices.map((price,index)=>{
      if(Number.isFinite(price))sum+=price;else missing++
      if(index>=period){const old=prices[index-period]!;if(Number.isFinite(old))sum-=old;else missing--}
      return index+1>=period&&missing===0?sum/period:null
    })
  }
  return result
}

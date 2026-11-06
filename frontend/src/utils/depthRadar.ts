import type {DepthLevel,MarketMicrostructure,MarketTrade} from '../services/api'

const valid=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)
export function observedDepth(rows:DepthLevel[]){return rows.filter(r=>valid(r.price)&&r.price>0&&valid(r.volume)&&r.volume>=0).sort((a,b)=>a.level-b.level)}
export function recentTicks(snapshot:MarketMicrostructure,seconds=60){
  const end=Date.parse(snapshot.dataTimestamp),unique=new Map<string,MarketTrade>()
  for(const t of snapshot.trades){const stamp=Date.parse(t.timestamp);if(valid(t.price)&&t.price>0&&valid(t.volume)&&t.volume>0&&Number.isFinite(stamp)&&stamp<=end&&stamp>end-seconds*1000)unique.set(t.id+':'+t.timestamp,t)}
  return [...unique.values()].sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp))
}
export function depthRadar(snapshot:MarketMicrostructure|null,now=Date.now()){
  const bids=observedDepth(snapshot?.bids??[]),asks=observedDepth(snapshot?.asks??[])
  const bidLots=bids.length?bids.reduce((n,r)=>n+r.volume,0):null,askLots=asks.length?asks.reduce((n,r)=>n+r.volume,0):null
  const bid=bids.find(r=>r.level===1)?.price,ask=asks.find(r=>r.level===1)?.price
  const spread=bid!=null&&ask!=null&&ask>=bid?ask-bid:null
  const imbalance=spread!==null&&bidLots!==null&&askLots!==null&&bidLots+askLots>0?(bidLots-askLots)/(bidLots+askLots):null
  const ticks=snapshot?recentTicks(snapshot):[]
  const buy=ticks.filter(t=>t.side==='BUY').reduce((n,t)=>n+t.volume,0),sell=ticks.filter(t=>t.side==='SELL').reduce((n,t)=>n+t.volume,0)
  const neutral=ticks.filter(t=>t.side!=='BUY'&&t.side!=='SELL').reduce((n,t)=>n+t.volume,0)
  const buyRatio=buy+sell>0?buy/(buy+sell):null
  const age=snapshot?(now-Date.parse(snapshot.dataTimestamp))/1000:Infinity
  const fresh=snapshot?.dataStatus==='FRESH'&&age>=0&&age<=15
  const maxTick=ticks.length?Math.max(...ticks.map(t=>t.volume)):null
  return {bids,asks,bidLots,askLots,spread,imbalance,ticks,buy,sell,neutral,buyRatio,maxTick,fresh,age,
    bidCoverage:bids.length,askCoverage:asks.length}
}

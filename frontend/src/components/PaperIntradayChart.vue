<script setup lang="ts">
import {computed,ref} from 'vue'
import type {HistoryPoint,PaperFill} from '../services/api'
import {tradeLabel} from '../utils/paperChartTrades'
import {formatNumber,formatTime} from '../utils/format'
import {dkxIndicator} from '../utils/dkx'
const props=defineProps<{points:HistoryPoint[];fills:PaperFill[];asOf:string;showDkx?:boolean;live?:boolean;tradingDay?:string;tradingSessions?:{day?:string[][];night?:string[][]}}>()
const emit=defineEmits<{trade:[fill:PaperFill]}>()
const selected=ref<HistoryPoint|null>(null)
const day=computed(()=>props.tradingDay??known.value.at(-1)?.tradingDate)
const known=computed(()=>props.points.filter(p=>props.live&&p.provisional?Date.parse(p.timestamp)<=Date.parse(props.asOf):Date.parse(p.endTime??p.timestamp)+(!p.endTime?60000:0)<=Date.parse(props.asOf)))
const averages=computed(()=>{
 let sum=0
 const dkx=dkxIndicator(known.value)
 return known.value.map((p,i)=>{sum+=p.price;if(i>=20)sum-=known.value[i-20]!.price;return {...p,...dkx[i]!,ma20:i>=19?sum/20:null}})
})
const rows=computed(()=>averages.value.filter(p=>day.value?p.tradingDate===day.value:true))
const bounds=computed(()=>{const values=[...rows.value.flatMap(p=>[p.price,p.ma20,...(props.showDkx?[p.dkx,p.madkx]:[])].filter((v):v is number=>v!=null)),...markers.value.map(m=>m.fill.fillPrice).filter(Number.isFinite)];const lo=Math.min(...values),hi=Math.max(...values);const pad=Math.max(1,(hi-lo)*.12);return {lo:lo-pad,hi:hi+pad}})
const minute=(text:string)=>{const [h,m]=text.split(':').map(Number);return h!*60+m!}
const timeline=computed(()=>{
 const sessions=props.tradingSessions
 const pairs=sessions?[...(sessions.night??[]),...(sessions.day??[])]:props.live?[['21:00','45:00']]:[['21:00','23:00'],['09:00','10:15'],['10:30','11:30'],['13:30','15:00']]
 const slots:number[]=[],labels:{label:string;index:number}[]=[]
 for(const pair of pairs){if(pair.length<2)continue;const start=minute(pair[0]!),end0=minute(pair[1]!),end=end0<=start?end0+1440:end0
  if(!Number.isFinite(start)||!Number.isFinite(end)||end-start>1440)continue
  labels.push({label:pair[0]!.slice(0,5),index:slots.length})
  for(let m=start;m<end;m++)slots.push(m%1440)
 }
 const last=pairs.at(-1)?.[1];if(slots.length&&last)labels.push({label:String(Math.floor(minute(last)/60)%24).padStart(2,'0')+':'+String(minute(last)%60).padStart(2,'0'),index:slots.length-1})
 return {slots,labels}
})
function slot(stamp:string){const d=new Date(Date.parse(stamp)+8*3600000),m=d.getUTCHours()*60+d.getUTCMinutes();return Math.max(0,timeline.value.slots.indexOf(m))}
const x=(stamp:string)=>58+slot(stamp)/Math.max(1,timeline.value.slots.length-1)*804
const y=(value:number)=>302-(value-bounds.value.lo)/(bounds.value.hi-bounds.value.lo)*264
const priceLine=computed(()=>rows.value.map(p=>`${x(p.timestamp)},${y(p.price)}`).join(' '))
const maLine=computed(()=>rows.value.filter(p=>p.ma20!=null).map(p=>`${x(p.timestamp)},${y(p.ma20!)}`).join(' '))
const dkxPaths=computed(()=>['dkx','madkx'].map(key=>{
 let pen=false
 const d=rows.value.map(p=>{const v=p[key as 'dkx'|'madkx'];if(v==null){pen=false;return ''}const command=pen?'L':'M';pen=true;return `${command}${x(p.timestamp)},${y(v)}`}).join(' ')
 return {key,d}
}))
const volumeMax=computed(()=>Math.max(1,...rows.value.map(p=>p.volume??0)))
const markers=computed(()=>props.fills.flatMap(fill=>{
 const t=Date.parse(fill.marketTime);if(t>Date.parse(props.asOf))return []
 const p=rows.value.find(p=>p.contract===fill.contract&&t>=Date.parse(p.startTime??p.timestamp)&&t<Date.parse(p.endTime??p.timestamp)+(!p.endTime?60000:0))
  ?? (fill.reason?.includes('收盘清仓')?rows.value.find(p=>p.contract===fill.contract&&p.endTime&&t===Date.parse(p.endTime)):undefined)
 return p?[{fill,point:p}]:[]
}))
const latest=computed(()=>rows.value.find(p=>p.timestamp===selected.value?.timestamp)??rows.value.at(-1))
</script>
<template>
 <section class="intraday-chart" aria-label="模拟分时图">
  <header><div><strong>{{day}} · 分时走势</strong><span>价格折线 <i class="price-key" /> · MA20 <i class="ma-key" /></span></div><p v-if="latest">{{formatTime(latest.timestamp)}} <b>{{formatNumber(latest.price,2)}}</b></p></header>
  <div v-if="showDkx" class="dkx-legend" aria-label="DKX指标读数"><span>DKX(20): {{formatNumber(latest?.dkx)}} </span><span>MADKX(10): {{formatNumber(latest?.madkx)}}</span><small>1分钟周期 · 不足20 / 29根或缺少OHLC时显示 —</small></div>
  <svg v-if="rows.length" viewBox="0 0 930 425" role="img" :aria-label="`${day}当日分时价格与MA20，已展示${rows.length}分钟`">
   <g v-for="n in [0,1,2,3,4]" :key="n"><line x1="58" x2="862" :y1="38+n*66" :y2="38+n*66" class="grid"/><text x="48" :y="42+n*66" text-anchor="end">{{formatNumber(bounds.hi-(bounds.hi-bounds.lo)*n/4,1)}}</text></g>
   <polyline :points="priceLine" class="price-line"/><polyline :points="maLine" class="ma-line"/>
   <template v-if="showDkx"><path v-for="line in dkxPaths" :key="line.key" :d="line.d" :class="line.key+'-line'" :data-indicator="line.key"/></template>
   <circle v-if="rows.at(-1)" :cx="x(rows.at(-1)!.timestamp)" :cy="y(rows.at(-1)!.price)" r="3" fill="#286b9a"/>
   <circle v-for="p in rows" :key="p.timestamp" :cx="x(p.timestamp)" :cy="y(p.price)" r="7" class="hit" @mouseenter="selected=p" @mouseleave="selected=null"><title>{{formatTime(p.timestamp)}} · {{p.price}}</title></circle>
   <g v-for="{fill,point} in markers" :key="fill.id" class="trade" tabindex="0" role="button" :aria-label="`${tradeLabel(fill)} ${fill.fillPrice} 记录心得`" @click="emit('trade',fill)" @keydown.enter="emit('trade',fill)" @keydown.space.prevent="emit('trade',fill)">
    <rect :x="x(point.timestamp)-28" :y="y(fill.fillPrice)-29" width="56" height="58" fill="transparent" pointer-events="all"/>
    <circle :cx="x(point.timestamp)" :cy="y(fill.fillPrice)" r="6" :class="fill.side==='BUY'?'buy':'sell'"/><text :x="x(point.timestamp)" :y="y(fill.fillPrice)+(fill.side==='BUY'?-14:22)" text-anchor="middle" :class="fill.side==='BUY'?'buy-text':'sell-text'">{{tradeLabel(fill)}}</text><title>{{tradeLabel(fill)}} {{fill.fillPrice}} · 点击记录心得</title>
   </g>
   <line x1="58" x2="862" y1="325" y2="325" class="grid"/>
   <rect v-for="p in rows" :key="'v'+p.timestamp" :x="x(p.timestamp)-1" :y="390-(p.volume??0)/volumeMax*54" width="2" :height="(p.volume??0)/volumeMax*54" :class="p.price>=(p.open??p.price)?'buy':'sell'"/>
   <text x="58" y="320">成交量</text><text v-for="tick in timeline.labels" :key="tick.index" :x="58+tick.index/Math.max(1,timeline.slots.length-1)*804" y="411" text-anchor="middle">{{tick.label}}</text>
  </svg>
  <p v-else>{{live?'当前交易日分时尚未就绪，请核对行情状态与时间。':'当前时点尚无已完成的分钟数据。'}}</p>
  <footer>{{live?'按实际交易时段显示夜盘及日盘，当前分钟随实时行情更新；已收盘时段保留真实观测。':'按交易日显示夜盘及日盘，空白区等待回放推进；分时折线使用已完成的1分钟收盘价。'}} 点击买卖点可记录心得。</footer>
 </section>
</template>
<style scoped>
.dkx-line{stroke:#a04bb5;stroke-width:1.7;fill:none}.madkx-line{stroke:#008b87;stroke-width:1.7;fill:none;stroke-dasharray:5 3}.dkx-legend{display:flex;flex-wrap:wrap;gap:.35rem 1rem;font-size:.72rem;margin-top:.6rem;color:#a04bb5}.dkx-legend span:nth-child(2){color:#008b87}.dkx-legend small{color:#77847e}
.intraday-chart{border:1px solid var(--color-line,#dae0dd);border-radius:.8rem;background:#fff;padding:1rem;min-width:0}.intraday-chart header{display:flex;justify-content:space-between;gap:.75rem;flex-wrap:wrap;font-size:.8rem}.intraday-chart header span{display:block;font-size:.7rem;color:#64746f;margin-top:.6rem}.intraday-chart header p{margin:0;color:#46766d}.intraday-chart b{margin-left:.5rem}.intraday-chart svg{display:block;width:100%;margin-top:1rem;overflow:visible}.intraday-chart text{font-size:11px;fill:#73877f;font-family:var(--font-numeric,monospace)}.grid{stroke:#e6ede9;stroke-dasharray:3 4}.price-line{stroke:#286b9a;stroke-width:1.8;fill:none}.ma-line{stroke:#d19c21;stroke-width:1.5;fill:none}.hit{fill:transparent;cursor:crosshair}.trade{cursor:pointer}.buy{fill:#dc3e32}.sell{fill:#1b9871}.intraday-chart .buy-text{fill:#d43d30;font-size:10px}.intraday-chart .sell-text{fill:#198966;font-size:10px}.price-key,.ma-key{display:inline-block;width:1rem;border-top:2px solid #286b9a;vertical-align:middle}.ma-key{border-color:#d19c21}.intraday-chart footer{margin-top:.5rem;font-size:.7rem;color:#77847e;line-height:1.7}
</style>

<script setup lang="ts">
import {instrumentLabel} from '../../utils/instrumentNames'
import {computed,nextTick,onMounted,onUnmounted,ref,watch} from 'vue'
import {RouterLink,useRoute,useRouter,type LocationQuery,type LocationQueryRaw} from 'vue-router'
import TongdaxinChart from '../../components/TongdaxinChart.vue'
import ChanlunReader from '../../components/ChanlunReader.vue'
import {api} from '../../services/api'
import {requestUuid} from '../../utils/requestId'
import {lastTimeAtOrBefore,type TimeWindow} from '../../utils/chartTimeLink'
import {formatTradingDateTime} from '../../utils/format'
import type {Structure} from './api'
import {monitorApi} from './monitor'
import {multiframeApi,type MultiframeDraft,type MultiframeRun,type MultiframeSummary,type MultiframeFrame} from './multiframe'
import ChanlunNavigation from './ChanlunNavigation.vue'
import {multiframeQuery,multiframeResult,frozenSelection,deliverySymbol,marketOrigin} from '../../utils/chanlunContext'
import {contextUuid,contextPeriod} from '../../utils/tradingContext'
import {decisionsApi} from '../../services/decisions'
import {decisionDetail} from '../../utils/decisionResponses'
import {authState,hasPermission} from '../../services/auth'
const route=useRoute(),router=useRouter()
const current=ref<MultiframeRun|null>(null),recent=ref<MultiframeSummary[]>([]),contracts=ref<string[]>([])
const symbol=ref(''),frames=ref<'PAIR'|'TRIPLE'>('PAIR'),asOf=ref(''),busy=ref(false),loading=ref(false),error=ref(''),notice=ref('')
const archiveError=ref(''),focusedFrame=ref(''),ready=ref(false),contextValid=ref(false)
let origin:LocationQuery={},originSymbol='',applying=true
const internalQueries=new Set<string>()
const cursorBound=ref<string|null>(null),linkWindows=ref(false),viewport=ref<TimeWindow|null>(null),selected=ref<{frame:MultiframeFrame;structure:Structure}|null>(null),reader=ref(false),lesson=ref(62)
const report=computed(()=>current.value?.report)
const names:Record<string,string>={DAY:'日线',MIN30:'30 分钟',MIN5:'5 分钟'}
const chartData=computed(()=>new Map((report.value?.frames??[]).map(f=>[f.frequency,{
  points:f.analysis.bars.map((b,i,list)=>({timestamp:b.timestamp,contract:b.contract,price:b.close,open:b.open,high:b.high,low:b.low,volume:b.volume,changePct:i?(b.close/list[i-1]!.close-1)*100:0,changePctKnown:i>0})),
  overlays:f.analysis.structures.filter(s=>['BI','ZONE','BSP'].includes(s.type)),
}])))
const points=(f:MultiframeFrame)=>chartData.value.get(f.frequency)!.points
const overlays=(f:MultiframeFrame)=>chartData.value.get(f.frequency)!.overlays
function cursor(f:MultiframeFrame,timestamp:string|null){cursorBound.value=timestamp?f.analysis.bars.find(b=>b.timestamp===timestamp)?.sealedByTimestamp??null:null}
function target(f:MultiframeFrame){if(!cursorBound.value)return null;const i=lastTimeAtOrBefore(f.analysis.bars,cursorBound.value,b=>b.sealedByTimestamp);return i===null?null:f.analysis.bars[i]!.timestamp}
function select(f:MultiframeFrame,id:string){const structure=f.analysis.structures.find(s=>s.id===id);if(structure){selected.value={frame:f,structure};focusedFrame.value=f.frequency;if(current.value)void syncUrl(currentQuery(current.value))}}
function focus(f:MultiframeFrame){focusedFrame.value=f.frequency;if(selected.value?.frame.frequency!==f.frequency)selected.value=null;if(current.value)void syncUrl(currentQuery(current.value))}
function book(){const refs=selected.value?.structure.evidence?.referenceLessons;lesson.value=Array.isArray(refs)&&typeof refs[0]==='number'?refs[0]:62;reader.value=true}
let alive=true,generation=0,timer:number|undefined,attempts=0,command:MultiframeDraft|null=null
function stop(){if(timer!==undefined)window.clearTimeout(timer);timer=undefined}
function accept(value:MultiframeRun){current.value=value;cursorBound.value=null;viewport.value=null;selected.value=null;focusedFrame.value='';if(value.status==='FAILED')error.value=value.error??'观察重建未完成'}
const originFor=(target:string)=>marketOrigin(origin,target)
function currentQuery(value:MultiframeRun):LocationQueryRaw{return {...originFor(value.request.symbol),frames:value.request.frames,observation:value.id,...focusedFrame.value?{frame:focusedFrame.value}:{},...selected.value?{structure:selected.value.structure.id}:{}}}
const marketQuery=computed(()=>current.value?{...originFor(current.value.request.symbol),chanObservation:current.value.id,...focusedFrame.value?{chanFrame:focusedFrame.value}:{},...selected.value?{chanStructure:selected.value.structure.id}:{}}:{})
async function syncUrl(query:LocationQueryRaw,push=false){
 const signature=JSON.stringify(query);if(!alive||signature===JSON.stringify(route.query))return
 internalQueries.add(signature)
 try{await router[push?'push':'replace']({path:'/chanlun/multiframe',query});await nextTick()}finally{internalQueries.delete(signature)}
}
async function recentRuns(){try{const value=await multiframeApi.list();if(alive)recent.value=value}catch(e){if(alive)archiveError.value=e instanceof Error?e.message:'观察列表读取失败'}}
async function applyRoute(){
 const version=++generation;stop();applying=true;contextValid.value=false;loading.value=true;busy.value=false;error.value='';notice.value='';current.value=null;selected.value=null;focusedFrame.value='';command=null;origin={};originSymbol=''
 const q=route.query,p=multiframeQuery(q)
 try{
  if(p.errors.length)throw new Error(p.errors.join(' '))
  if(authState.user&&!hasPermission('chanlun.read'))throw new Error('当前身份不能读取缠论观察。')
  let target=p.symbol,period=String(p.frequency),cid='',pid=''
  if(q.case!==undefined){
   if(!hasPermission('market.read')||!hasPermission('paper.read'))throw new Error('当前身份不能核验关联档案。')
   cid=contextUuid(q.case);const c=decisionDetail(await decisionsApi.detail(cid),cid);if(!alive||version!==generation)return
   const plan=q.plan===undefined?c.plans.find(item=>item.version===c.version):c.plans.find(item=>item.id===contextUuid(q.plan))
   if(q.plan!==undefined&&!plan)throw new Error('指定计划版本不在此档案中。')
   pid=plan?.id??'';originSymbol=c.symbol;if(!target)target=c.symbol
   if(q.period===undefined&&q.seconds===undefined)period=String(contextPeriod(String(c.origin.evidence?.triggerSeconds))??(Number(c.origin.evidence?.triggerSeconds)===86400?'DAY':60))
  }
  let value:MultiframeRun|null=null
  if(p.observation){value=multiframeResult(await multiframeApi.get(p.observation),p.observation);if(!alive||version!==generation)return;if(target&&target!==value.request.symbol)throw new Error('冻结观察与请求的合约不一致，不替换原记录。');target=value.request.symbol;if(q.frames!==undefined&&p.frames!==value.request.frames)throw new Error('周期组合与冻结观察不一致。')}
  if(originSymbol&&target!==originSymbol)throw new Error('观察合约与原计划不是同一交割月，请先解除浏览关联。')
  target=target||symbol.value||contracts.value[0]||''
  if(target&&!deliverySymbol(target))throw new Error('请选择实际交割合约。')
  origin={symbol:target,period,...cid?{case:cid,...pid?{plan:pid}:{}}:{}}
  symbol.value=target;frames.value=value?.request.frames??p.frames;asOf.value=value?.request.asOf?new Date(Date.parse(value.request.asOf)+8*3600000).toISOString().slice(0,23):''
  if(value){const selection=frozenSelection(value,p.frame,p.structure);accept(value);focusedFrame.value=p.frame;selected.value=selection}
  await nextTick();if(!alive||version!==generation)return;applying=false;loading.value=false;contextValid.value=true
  if(value)await syncUrl(currentQuery(value));else if(target)await syncUrl({...originFor(target),frames:frames.value})
 }catch(e){if(alive&&version===generation){current.value=null;selected.value=null;error.value=e instanceof Error?e.message:'观察来源无法恢复';loading.value=false;await nextTick();if(version===generation)applying=false}}
}
function syncDraft(){
 if(applying||current.value||busy.value||loading.value||!deliverySymbol(symbol.value))return
 const target=deliverySymbol(symbol.value),q=originFor(target)
 if(originSymbol&&target!==originSymbol){notice.value='草稿已换月，解除旧计划浏览关联；原计划未修改。';originSymbol=''}
 origin=Object.fromEntries(Object.entries(q).filter(([,value])=>typeof value==='string')) as LocationQuery
 void syncUrl({...q,frames:frames.value},true)
}
function independentDraft(){
 if(busy.value||loading.value)return
 const target=deliverySymbol(route.query.symbol)||deliverySymbol(symbol.value)
 void router.replace({path:'/chanlun/multiframe',query:{...target?{symbol:target}:{},period:String(contextPeriod(route.query.period??route.query.seconds)??60),frames:frames.value}})
}
async function submit(body:MultiframeDraft,version:number){
  busy.value=true
  try{
    const value=multiframeResult(await multiframeApi.create(body),undefined,body)
    if(!alive||version!==generation)return
    accept(value);if(originSymbol&&originSymbol!==body.symbol){origin=Object.fromEntries(Object.entries(originFor(body.symbol))) as LocationQuery;originSymbol=''}
    await syncUrl(currentQuery(value));if(!alive||version!==generation)return;await recentRuns();if(!alive||version!==generation)return
    if(['WAITING_INPUT','QUEUED','RUNNING'].includes(value.status)&&attempts++<45){notice.value=value.error??'等待独立主源序列，沿用原请求继续检查';timer=window.setTimeout(()=>void submit(body,version),1500)}
    else{if(value.status==='SUCCEEDED')command=null;notice.value=value.status==='SUCCEEDED'?'本次观察已冻结保存。':'自动等待已结束，可手动继续同一请求。'}
  }catch(e){if(alive&&version===generation)error.value=(e instanceof Error?e.message:'网络响应不确定')+'；重试保留原请求编号。'}
  finally{if(alive&&version===generation)busy.value=false}
}
function create(cutoff?:string){
  if(busy.value||loading.value||!contextValid.value||!hasPermission('chanlun.write'))return
  let bound:string|null=null
  try{bound=cutoff??(asOf.value?new Date(asOf.value+'+08:00').toISOString():null)}catch{error.value='请选择有效的观察时点';return}
  const body={symbol:symbol.value.trim().toUpperCase(),frames:frames.value,asOf:bound}
  if(!/^[A-Z]{1,4}[0-9]{3,4}$/.test(body.symbol)){error.value='请选择真实交割合约';return}
  if(!command||command.symbol!==body.symbol||command.frames!==body.frames||command.asOf!==body.asOf)command={...body,clientRequestId:requestUuid()}
  stop();const version=++generation;attempts=0;error.value='';notice.value='';current.value=null;selected.value=null;focusedFrame.value='';void submit(command,version)
}
function rebuildCursor(){if(cursorBound.value&&report.value){symbol.value=report.value.config.symbol;frames.value=report.value.frames.length===3?'TRIPLE':'PAIR';create(cursorBound.value)}}
function resumePending(){
  if(!current.value||busy.value||!contextValid.value||!hasPermission('chanlun.write'))return
  command=current.value.request;stop();attempts=0;error.value='';notice.value='';void submit(command,++generation)
}
watch(()=>route.fullPath,()=>{if(internalQueries.has(JSON.stringify(route.query)))return;if(ready.value)void applyRoute()})
watch(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId,authState.user?.permissions]),()=>{if(ready.value)void applyRoute()})
watch(linkWindows,enabled=>{if(!enabled)viewport.value=null})
onMounted(async()=>{
  const metadata=await Promise.allSettled([api.instruments(),monitorApi.list()])
  if(!alive)return
  if(metadata[0].status==='fulfilled')contracts.value=metadata[0].value.exchanges.flatMap(e=>e.instruments.flatMap(p=>p.contracts))
  if(!symbol.value)symbol.value=(metadata[1].status==='fulfilled'?metadata[1].value.find(m=>m.enabled)?.symbol:null)??contracts.value.find(c=>c.startsWith('FU'))??''
  ready.value=true;await Promise.all([recentRuns(),applyRoute()])
})
onUnmounted(()=>{alive=false;generation++;stop()})
</script>
<template><main class="multi"><ChanlunNavigation active="multiframe" :context="current?currentQuery(current):{}"/>
  <header><p class="eyebrow">独立主源周期 · 共同重建界限 · 冻结观察</p><h1>多周期结构观察</h1><p>按各周期后一根已出现的证据截取原始输入，再分别计算结构。保留实际采集时间，历史重建不冒充当时已收到的行情。</p></header>
  <section v-if="current" class="bounds" aria-label="冻结缠论来源"><h2>{{instrumentLabel(current.request.symbol)}} · {{report?'冻结多周期观察':'尚未形成冻结结果'}}</h2><p>观察 {{current.id}} · 原周期组合 {{current.request.frames==='TRIPLE'?'日线 / 30分 / 5分':'30分 / 5分'}}</p><p v-if="report">共同重建界限 {{formatTradingDateTime(report.asOf)}} · 实际采集 {{formatTradingDateTime(report.capturedAt)}}。历史重建不冒充当时已收到的行情。</p><p>下方参数用于另建观察，不修改本记录；返回行情打开当前市场，不重算旧结构。</p><RouterLink v-if="hasPermission('market.read')" :to="{path:'/live',query:{...marketQuery,tab:'futures'}}">查看当前行情并保留观察回链 ↗</RouterLink></section>
  <p v-else-if="contextValid" class="muted">当前是 {{symbol?instrumentLabel(symbol):'未选合约'}} 的观察草稿；打开页面不会采集或创建观察。返回看盘周期与下面30分/5分观察组合分开。</p>
  <form class="config" @submit.prevent="create()"><label>交割合约<input v-model="symbol" @change="syncDraft" list="multiframe-contracts" required :disabled="busy||loading||!contextValid"/><datalist id="multiframe-contracts"><option v-for="c in contracts" :key="c" :value="c" :label="instrumentLabel(c)"/></datalist></label><label>周期组合<select v-model="frames" @change="syncDraft" :disabled="busy||loading||!contextValid"><option value="PAIR">30 分钟 / 5 分钟</option><option value="TRIPLE">日线 / 30 分钟 / 5 分钟</option></select></label><label>上海重建时点（留空取最新已证实界限）<input v-model="asOf" type="datetime-local" step="0.001" :disabled="busy||loading||!contextValid"/></label><button :disabled="busy||loading||!contextValid||!hasPermission('chanlun.write')" type="submit">{{busy?'等待主源与计算…':'采集并冻结观察'}}</button></form>
  <p class="muted">每周期最多 2,000 根，至少需要 50 根封存输入。各周期预热窗口不同；主源不足时等待，不用其他周期合成替代。</p><p v-if="error" role="alert" class="error">{{error}} <button v-if="!contextValid" :disabled="busy||loading" @click="independentDraft">解除引用，进入独立观察草稿</button></p><p v-if="notice" role="status">{{notice}}</p><p v-if="loading" role="status">正在恢复冻结观察…</p>
  <section v-if="current&&!report&&['QUEUED','RUNNING','WAITING_INPUT'].includes(current.status)"><p class="muted">{{current.error??'等待独立主源输入或服务器完成。'}}</p><button @click="resumePending" :disabled="busy||!hasPermission('chanlun.write')">继续原请求</button></section>
  <template v-if="report"><section class="bounds"><h2>{{instrumentLabel(report.config.symbol)}} · 共同重建界限 {{formatTradingDateTime(report.asOf)}}</h2><p>实际采集 {{formatTradingDateTime(report.capturedAt)}} · {{report.frames.map(f=>names[f.frequency]).join(' / ')}}</p><p>光标封存界限 {{cursorBound?formatTradingDateTime(cursorBound):'未选择'}}。光标只定位，结构仍属于上面的冻结观察界限；查看更早结构请重新构建。</p><button @click="rebuildCursor" :disabled="!cursorBound||busy">按光标界限重新构建</button><label class="inline"><input type="checkbox" v-model="linkWindows"/>联动时间视窗</label></section>
    <div class="frames" :class="{triple:report.frames.length===3}"><section v-for="f in report.frames" :key="`${current?.id}:${f.frequency}`" class="frame"><h2>{{names[f.frequency]}} · {{f.analysis.observedBars}} 根</h2><button type="button" :aria-pressed="focusedFrame===f.frequency" @click="focus(f)">固定此周期到链接</button><p class="muted">最后 K 线 {{formatTradingDateTime(f.analysis.bars.at(-1)!.timestamp)}} · 已观察到后继 {{formatTradingDateTime(f.lastSealedBy)}}</p><TongdaxinChart :points="points(f)" :overlays="overlays(f)" :external-cursor-timestamp="target(f)" :linked-viewport="linkWindows?viewport:null" :time-label-mode="f.frequency==='DAY'?'date':'datetime'" :selected-overlay-id="selected?.frame.frequency===f.frequency?selected.structure.id:undefined" :symbol="report.config.symbol" :display-name="names[f.frequency]" default-theme="light" :height="360" :initial-visible-bars="72" @cursor-timestamp="cursor(f,$event)" @viewport-change="linkWindows&&(viewport=$event)" @select-structure="select(f,$event)"/><details><summary>源窗口与版本</summary><p>主源实际接收 {{formatTradingDateTime(f.source.receiptAt)}} · 源窗口 {{f.sourceWindowBars}} 根 · 本次封存序号 {{f.firstProviderIndex}}—{{f.lastProviderIndex}}</p><p>规则摘要</p><code>{{f.analysis.profileHash}}</code><p>输入摘要（含封存证据）</p><code>{{f.analysis.inputHash}}</code></details></section></div>
    <section v-if="selected" class="evidence"><h2>{{names[selected.frame.frequency]}} · {{selected.structure.type}} · 修订 {{selected.structure.revision}}</h2><p>端点 {{selected.structure.pivotEndDate}} · 首次结构观察 {{selected.structure.firstObservedDate}} · 以上时间为重建序列标记，实际采集时间另列。</p><pre>{{JSON.stringify(selected.structure.evidence,null,2)}}</pre><button @click="book">阅读对应原文</button></section>
    <details open><summary>观察范围与限制</summary><ul><li v-for="item in report.limitations" :key="item">{{item}}</li></ul><code>{{report.configHash}}</code></details>
  </template>
  <section><h2>已保存的多周期观察</h2><p v-if="archiveError" role="alert">{{archiveError}}</p><p v-if="!recent.length" class="muted">尚无记录，打开此页不会自动创建订阅。</p><ul class="archive"><li v-for="r in recent" :key="r.id"><button @click="router.push({path:'/chanlun/multiframe',query:{observation:r.id}})" :disabled="busy">{{instrumentLabel(r.symbol)}} · {{r.frames==='TRIPLE'?'日/30/5':'30/5'}} · {{r.status==='SUCCEEDED'?'已冻结':r.status==='FAILED'?'未完成':'等待中'}} · {{r.createdAt}}</button></li></ul></section>
  <section v-if="reader"><button @click="reader=false">收起原文</button><ChanlunReader :initial-chapter="lesson"/></section>
</main></template>
<style scoped>.multi{max-width:1700px;margin:auto;color:#293b31}h1{font-size:1.8rem;margin:.5rem 0}h2{font-size:1rem}.eyebrow{font-size:.75rem;color:#7a725e;letter-spacing:.1em}header>p:last-child,.muted,.bounds p{font-size:.8rem;line-height:1.8;color:#657066}.config{display:flex;gap:.8rem;flex-wrap:wrap;align-items:end;padding:1rem;background:#f0f1e8;border-radius:.4rem;margin:1rem 0}label{display:grid;gap:.4rem;font-size:.8rem}input,select,button{font:inherit;padding:.55rem .7rem;border:1px solid #c6cdbf;border-radius:.3rem;background:#fff;color:inherit;max-width:100%}button{cursor:pointer}button:disabled{opacity:.5;cursor:wait}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #9e784b;outline-offset:3px}.bounds{padding:1rem;border:1px solid #dedfd5}.inline{display:inline-flex;align-items:center;gap:.4rem;margin-left:1rem}.frames{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;margin:1rem 0}.triple{grid-template-columns:repeat(3,minmax(0,1fr))}.frame{min-width:0;border:1px solid #dedfd5;border-radius:.4rem;padding:.75rem}.frame h2{margin:.2rem 0}.frame>p{margin:.5rem 0}details{font-size:.78rem;line-height:1.8;margin:.9rem 0}summary{cursor:pointer;font-weight:600}code,pre{overflow-wrap:anywhere;white-space:pre-wrap;font-size:.72rem}.evidence{padding:1rem;border:1px solid #dedfd5}.archive{list-style:none;padding:0}.archive li{margin:.5rem 0}.archive button{font-size:.75rem}.error{color:#aa4539}@media(max-width:1250px){.triple{grid-template-columns:1fr}}@media(max-width:950px){.frames{grid-template-columns:1fr}}@media(max-width:600px){.config{display:grid;grid-template-columns:1fr}.inline{display:flex;margin:.6rem 0}h1{font-size:1.4rem}}@media(pointer:coarse){button,input,select{min-height:44px}}</style>

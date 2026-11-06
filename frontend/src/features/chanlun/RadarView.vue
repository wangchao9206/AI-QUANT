<script setup lang="ts">
import {instrumentLabel} from '../../utils/instrumentNames'
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import TongdaxinChart from '../../components/TongdaxinChart.vue'
import ChanlunReader from '../../components/ChanlunReader.vue'
import {api} from '../../services/api'
import {requestUuid} from '../../utils/requestId'
import ChanlunNavigation from './ChanlunNavigation.vue'
import {monitorApi,type MonitorDraft,type MonitorSummary,type MonitorView,type MonitorEvidence,type MonitorFrequency,type MonitorReview} from './monitor'
const route=useRoute(),router=useRouter()
const monitors=ref<MonitorSummary[]>([]),current=ref<MonitorView|null>(null),evidence=ref<MonitorEvidence|null>(null),contracts=ref<string[]>([])
const title=ref('我的缠论监控'),symbol=ref(''),frequency=ref<MonitorFrequency>('MIN5'),error=ref(''),notice=ref(''),catalogNotice=ref('')
const busy=ref(false),loading=ref(false),draft=ref(''),outlook=ref<MonitorReview['outlook']>('WAIT'),reader=ref(false),lesson=ref(20)
const states:Record<string,string>={WAITING_DATA:'等待主源数据',ACTIVE:'主源监控中',CLOSED:'休市维护',STALE:'行情陈旧，暂停新提醒',DISCONNECTED:'主源断流，暂停新提醒',PAUSED:'已暂停',ERROR:'调用失败，保留水位重试',VERSION_CHANGED:'规则版本变化，已暂停',INPUT_REVISED:'已封存行情修订，已暂停',GAP:'源窗口越过水位，已暂停',LIMIT_REACHED:'已达保留上限，已暂停'}
const inbox:Record<string,string>={NEW:'新事件',ACKNOWLEDGED:'已读',SUPPRESSED_BOOTSTRAP:'历史初始化',SUPPRESSED_CLOSED:'休市留档',SUPPRESSED_BACKFILL:'补算或未取得新提醒资格'}
const frequencies:Record<MonitorFrequency,string>={DAY:'日线',MIN5:'5 分钟',MIN30:'30 分钟'}
const analysis=computed(()=>evidence.value?.analysis??current.value?.analysis)
const points=computed(()=>(analysis.value?.bars??[]).map((b,i,bars)=>({timestamp:b.timestamp,contract:b.contract,price:b.close,open:b.open,high:b.high,low:b.low,volume:b.volume,changePct:i?(b.close/bars[i-1]!.close-1)*100:0,changePctKnown:i>0})))
const overlays=computed(()=>(analysis.value?.structures??[]).filter(s=>['BI','ZONE','BSP'].includes(s.type)))
const fatal=computed(()=>['VERSION_CHANGED','INPUT_REVISED','GAP','LIMIT_REACHED'].includes(current.value?.status??''))
let active=true,generation=0,timer:number|undefined,createCommand:MonitorDraft|null=null
let reviewCommand:{key:string;clientRequestId:string;outlook:MonitorReview['outlook'];content:string;lessonNumber:number|null}|null=null
const drafts=new Map<string,string>()
const key=computed(()=>`${current.value?.id??''}:${evidence.value?.event.eventSeq??''}`)
watch(draft,value=>{if(key.value)drafts.set(key.value,value)})
function stop(){if(timer!==undefined)window.clearTimeout(timer);timer=undefined}
function schedule(){stop();if(active)timer=window.setTimeout(()=>void refresh(true),15000)}
async function load(id:string,seq?:number,quiet=false){
  const frozen=quiet&&current.value?.id===id&&evidence.value?.event.eventSeq===seq?evidence.value:null
  const version=++generation;if(!quiet){loading.value=true;current.value=null;evidence.value=null;error.value=''}
  try{const [monitor,event]=await Promise.all([monitorApi.get(id),seq?(frozen?Promise.resolve(frozen):monitorApi.evidence(id,seq)):Promise.resolve(null)])
    if(!active||generation!==version)return
    if(quiet&&monitor.analysis?.inputHash&&monitor.analysis.inputHash===current.value?.analysis?.inputHash&&monitor.analysis.profileHash===current.value.analysis.profileHash)monitor.analysis=current.value.analysis
    current.value=monitor;evidence.value=event
    if(!quiet){draft.value=drafts.get(`${id}:${seq??''}`)??'';notice.value='';reviewCommand=null}
  }catch(e){if(active&&generation===version)error.value=e instanceof Error?e.message:'监控读取失败'}
  finally{if(active&&generation===version){loading.value=false;schedule()}}
}
async function refresh(quiet=false){
  try{monitors.value=await monitorApi.list();if(current.value)await load(current.value.id,evidence.value?.event.eventSeq,quiet)}
  catch(e){error.value=e instanceof Error?e.message:'任务列表读取失败'}finally{schedule()}
}
function open(id:string,seq?:number){void router.push({path:'/chanlun/radar',query:{monitor:id,...(seq?{event:String(seq)}:{})}})}
async function create(){
  if(busy.value)return;busy.value=true;error.value=''
  const body={title:title.value.trim(),symbol:symbol.value.trim().toUpperCase(),frequency:frequency.value}
  if(!createCommand||createCommand.title!==body.title||createCommand.symbol!==body.symbol||createCommand.frequency!==body.frequency)createCommand={...body,clientRequestId:requestUuid()}
  try{const value=await monitorApi.create(createCommand);createCommand=null;if(!active)return;await refresh(true);if(active)open(value.id)}
  catch(e){error.value=e instanceof Error?e.message:'任务创建未完成；重试保留请求编号'}finally{busy.value=false}
}
async function control(check=false){
  if(!current.value||busy.value)return;const id=current.value.id;busy.value=true;error.value=''
  try{const value=check?await monitorApi.check(id):await monitorApi.control(id,!current.value.enabled);if(current.value?.id===id)current.value=value;await refresh(true)}
  catch(e){error.value=e instanceof Error?e.message:'服务器操作未完成'}finally{busy.value=false}
}
async function save(){
  if(!current.value||!evidence.value||!draft.value.trim()||busy.value)return
  const id=current.value.id,seq=evidence.value.event.eventSeq,text=draft.value.trim(),entryKey=key.value
  const refs=evidence.value.event.evidence?.referenceLessons,reference=Array.isArray(refs)&&typeof refs[0]==='number'?refs[0]:null
  if(!reviewCommand||reviewCommand.key!==entryKey||reviewCommand.content!==text||reviewCommand.outlook!==outlook.value)reviewCommand={key:entryKey,clientRequestId:requestUuid(),outlook:outlook.value,content:text,lessonNumber:reference}
  const {key:_,...body}=reviewCommand;busy.value=true;error.value=''
  try{await monitorApi.review(id,seq,body);if(key.value===entryKey){notice.value='复盘已保存，可在复盘档案恢复当时证据。';if(draft.value.trim()===text)draft.value=''}reviewCommand=null}
  catch(e){error.value=e instanceof Error?e.message:'复盘未完成；重试沿用同一编号'}finally{busy.value=false}
}
async function ack(seq:number){if(!current.value)return;try{current.value=await monitorApi.ack(current.value.id,seq)}catch(e){error.value=e instanceof Error?e.message:'已读状态保存失败'}}
function book(){const refs=evidence.value?.event.evidence?.referenceLessons;lesson.value=Array.isArray(refs)&&typeof refs[0]==='number'?refs[0]:20;reader.value=true}
function fromRoute(){const id=route.query.monitor,seq=Number(route.query.event);if(typeof id==='string')void load(id,Number.isInteger(seq)&&seq>0?seq:undefined);else{generation++;current.value=null;evidence.value=null;loading.value=false;schedule()}}
watch(()=>[route.query.monitor,route.query.event],()=>fromRoute())
onMounted(async()=>{
  try{const catalog=await api.instruments();contracts.value=catalog.exchanges.flatMap(e=>e.instruments.flatMap(p=>p.contracts));catalogNotice.value=catalog.source;symbol.value=contracts.value.find(c=>c.startsWith('FU'))??''}catch{catalogNotice.value='目录暂不可用；任务会等待主源核验，不使用降级行情计算。'}
  await refresh(true);fromRoute()
})
onUnmounted(()=>{active=false;generation++;stop()})
</script>
<template><main class="radar"><ChanlunNavigation active="radar"/>
  <header><p class="eyebrow">后台任务 · 主源封存行情 · 仅候选观察</p><h1>缠论信号雷达</h1><p>任务保存在服务器，关闭页面后仍运行。初始历史、过期补算与休市事件留档；新提醒与交易资格分开，当前不生成订单或外部通知。</p></header>
  <form class="create" @submit.prevent="create"><label>任务名称<input v-model="title" maxlength="120" required :disabled="busy"/></label><label>交割合约<input v-model="symbol" list="monitor-contracts" pattern="[A-Za-z]{1,4}[0-9]{3,4}" placeholder="选择真实交割合约" required :disabled="busy"/><datalist id="monitor-contracts"><option v-for="c in contracts" :key="c" :value="c" :label="instrumentLabel(c)"/></datalist></label><label>周期<select v-model="frequency" :disabled="busy"><option value="MIN5">5 分钟</option><option value="MIN30">30 分钟</option><option value="DAY">日线 · 暂只留档</option></select></label><button :disabled="busy" type="submit">创建后台监控</button></form>
  <p class="muted">{{catalogNotice}}。所有周期等待后一根出现才封存，末根可能延迟到下一时段。单任务保留至一万根；主源订阅最多八组合，单合约到期需新建任务，不自动换月。</p>
  <p v-if="error" role="alert" class="error">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
  <div class="layout"><aside><h2>服务器任务</h2><button @click="refresh(true)" :disabled="busy">刷新状态</button><p v-if="!monitors.length" class="muted">创建后才能启动；打开此页不会自动订阅。</p><button v-for="m in monitors" :key="m.id" class="task" @click="open(m.id)" :disabled="busy" :aria-pressed="current?.id===m.id"><strong>{{m.title}}</strong><span>{{instrumentLabel(m.symbol)}} · {{frequencies[m.frequency]}} · {{states[m.status]??m.status}}</span><span>水位 {{m.observedBars}} 根 · 检查 {{m.heartbeatAt??'尚未运行'}}</span></button></aside>
  <section><p v-if="loading" role="status">正在恢复服务器监控…</p><template v-else-if="current"><div class="heading"><h2>{{current.title}} · {{states[current.status]??current.status}}</h2><button @click="control(true)" :disabled="busy||!current.enabled">立即检查</button><button @click="control()" :disabled="busy||(!current.enabled&&fatal)">{{current.enabled?'暂停任务':'恢复任务'}}</button></div><p class="muted">{{current.error}} · 最近检查 {{current.heartbeatAt??'尚未运行'}} · 原始交割合约价 · {{instrumentLabel(current.symbol)}} / {{frequencies[current.frequency]}}</p><p v-if="current.source" class="muted">来源 {{current.source.source??'等待主源'}} · 主源接收 {{current.source.receiptAt??'尚未接收'}} · 封存证明 {{current.source.closeProof==='SUCCESSOR_OBSERVED'?'已观察到后一根':'待核验'}}</p>
    <p v-if="evidence" class="evidence-banner">当时行情与单个候选快照 · 截至 {{evidence.analysis.observedAsOfDate}} · 服务器实际发现 {{evidence.detectedAt}} <button @click="open(current.id)">返回最新监控视图</button></p>
    <TongdaxinChart v-if="analysis" :key="`${current.id}:${evidence?.event.eventSeq??'latest'}`" preserve-viewport-on-append :points="points" :overlays="overlays" :selected-overlay-id="evidence?.event.id" :symbol="current.symbol" :time-label-mode="current.frequency==='DAY'?'date':'datetime'" display-name="主源已封存交割合约行情" default-theme="light" :initial-visible-bars="72" :height="370"/>
    <p v-else class="muted">等待足够的真实封存行情；旧水位不会因断流被清空。</p>
    <section v-if="evidence" class="review"><h2>{{evidence.event.signalType}} · {{evidence.event.signalState==='INVALIDATED'?'已失效':'研究候选'}} · 修订 {{evidence.event.revision}}</h2><p class="muted">端点 {{evidence.event.pivotEndDate}} · 首次结构观察 {{evidence.event.firstObservedDate}} · 不等同历史可得时刻，实际发现时间另列。该快照只绘制此候选，完整原始行情前缀保留。</p><button @click="book">阅读对应原文</button><details><summary>当时规则证据</summary><pre>{{JSON.stringify(evidence.event.evidence,null,2)}}</pre></details><form @submit.prevent="save"><label>当时观点<select v-model="outlook"><option value="WAIT">等待</option><option value="UP">看多</option><option value="DOWN">看空</option></select></label><label>复盘判断<textarea v-model="draft" required maxlength="6000" placeholder="依据、失效条件与观察偏差"/></label><button :disabled="busy||!draft.trim()">保存复盘</button></form></section>
    <h2>候选与修订记录</h2><p class="muted">显示最近 100 条事件；所有记录保存在服务器。历史初始化不会伪装成实时提醒。</p><ol class="events"><li v-for="e in current.events" :key="e.eventSeq"><button @click="open(current.id,e.eventSeq)" :disabled="busy">{{e.payload.signalType}} · {{e.payload.signalState==='INVALIDATED'?'失效':'候选'}} · 修订 {{e.payload.revision}} · {{inbox[e.inboxState]??e.inboxState}}</button><span>实际发现 {{e.detectedAt}}</span><button v-if="e.inboxState==='NEW'" @click="ack(e.eventSeq)">标为已读</button></li></ol>
  </template><p v-else class="muted">选择任务查看健康、水位、候选证据与复盘。</p></section></div>
  <section v-if="reader"><button @click="reader=false">收起原文</button><ChanlunReader :initial-chapter="lesson"/></section>
</main></template>
<style scoped>
.radar{max-width:1450px;margin:auto;color:#293b31}.eyebrow{font-size:.75rem;color:#7a725e;letter-spacing:.1em}h1{font-size:1.8rem;margin:.5rem 0}h2{font-size:1rem;margin:1rem 0}.muted,header>p:last-child{font-size:.8rem;line-height:1.8;color:#657066}.create{display:flex;flex-wrap:wrap;align-items:end;gap:.7rem;background:#f0f1e8;padding:1rem;border-radius:.5rem;margin-top:1rem}label{display:grid;gap:.4rem;font-size:.8rem}input,select,button,textarea{font:inherit;border:1px solid #c6cdbf;border-radius:.3rem;padding:.55rem .7rem;background:#fff;color:#293b31;max-width:100%}button{cursor:pointer}button:disabled{opacity:.5;cursor:wait}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid #9e784b;outline-offset:3px}.layout{display:grid;grid-template-columns:260px minmax(0,1fr);gap:1.5rem}.task{display:grid;gap:.4rem;width:100%;text-align:left;margin:.6rem 0;font-size:.72rem}.task[aria-pressed=true],.evidence-banner{background:#e8eee3}.heading{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}.heading button{font-size:.75rem}.events{padding-left:1rem}.events li{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin:.5rem 0;font-size:.72rem}.events span{color:#657066}.error{color:#aa4539}.evidence-banner{padding:.7rem;line-height:1.8;font-size:.8rem}.review{border:1px solid #dedfd5;padding:1rem}.review form{display:grid;gap:.8rem}.review textarea{min-height:100px;resize:vertical}pre{font-size:.72rem;white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer;font-size:.8rem;margin:1rem 0}@media(max-width:900px){.layout{grid-template-columns:1fr}aside{display:flex;flex-wrap:wrap;gap:.5rem;align-items:start}.task{width:min(100%,280px)}}@media(max-width:600px){.create{display:grid;grid-template-columns:1fr}.create label{min-width:0}.heading{align-items:start}h1{font-size:1.4rem}}@media(pointer:coarse){button,input,select{min-height:44px}}
</style>

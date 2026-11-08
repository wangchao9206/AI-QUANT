<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {useRoute,useRouter,RouterLink} from 'vue-router'
import {BookOpen,RefreshCw,Save,StepForward} from 'lucide-vue-next'
import {ApiError} from '../../services/api'
import {requestUuid} from '../../utils/requestId'
import TongdaxinChart from '../../components/TongdaxinChart.vue'
import ChanlunReader from '../../components/ChanlunReader.vue'
import ChanlunNavigation from './ChanlunNavigation.vue'
import ChanlunSourceBar from './ChanlunSourceBar.vue'
import {chanlunApi,type Dataset,type Engine,type EngineId,type Structure,type Judgment} from './api'
import {replayApi,type ReplaySession,type ReplaySummary,type CreateReplay,type ReplayDecisionDraft} from './replay'

const route=useRoute(),router=useRouter()
const session=ref<ReplaySession|null>(null),recent=ref<ReplaySummary[]>([]),engines=ref<Engine[]>([]),dataset=ref<Dataset|null>(null)
const loading=ref(true),busy=ref(false),error=ref(''),notice=ref(''),metadataError=ref('')
const title=ref('我的逐根练习'),engine=ref<EngineId>('native'),startBars=ref(200)
const draft=ref(''),outlook=ref<Judgment['outlook']>('WAIT'),selectedId=ref(''),showReader=ref(false),lesson=ref(62),linkedLesson=ref<number|null>(null)
const layer=ref({BI:true,SEGMENT:false,ZONE:true,BSP:true,FRACTAL:false})
const names:Record<EngineId,string>={native:'AI-QUANT 自研引擎',chanpy:'chan.py',czsc:'CZSC',baseline:'研究基线'}
const kinds:Record<Structure['type'],string>={BI:'笔',SEGMENT:'线段',ZONE:'中枢',BSP:'候选买卖点',FRACTAL:'分型'}
const allKinds=['BI','SEGMENT','ZONE','BSP','FRACTAL'] as const
const analysis=computed(()=>session.value?.analysis??null)
const selected=computed(()=>analysis.value?.structures.find(s=>s.id===selectedId.value)??null)
const objects=computed(()=>(analysis.value?.structures??[]).slice().reverse())
const overlays=computed(()=>(analysis.value?.structures??[]).filter(s=>layer.value[s.type]))
const points=computed(()=>(analysis.value?.bars??[]).map((b,i,list)=>({timestamp:b.timestamp,contract:b.contract,price:b.close,open:b.open,high:b.high,low:b.low,volume:b.volume,changePct:i?(b.close/list[i-1]!.close-1)*100:0,changePctKnown:i>0})))
const editable=computed(()=>!!session.value&&!session.value.decisionSubmitted&&session.value.status==='ACTIVE'&&!busy.value&&!loading.value)
const lastDecision=computed(()=>session.value?.decisions.find(d=>d.step===session.value!.step-1))
const feedback=computed(()=>{
  const old=lastDecision.value?.evidence.structureSnapshot
  if(!old||!analysis.value)return ''
  const current=analysis.value.structures.find(s=>s.id===old.id)
  if(!current)return '上一步观察的结构已从当前输出撤回；原判断与当时证据仍保留。'
  if(current.signalState==='INVALIDATED'&&old.signalState!=='INVALIDATED')return '上一步观察的候选已触及失效条件。'
  return current.revision!==old.revision?`上一步观察对象由修订 ${old.revision} 变为 ${current.revision}，可查看新的端点与状态。`:'上一步观察对象暂未发生修订。'
})
const revealed=computed(()=>{
  const bars=analysis.value?.bars
  if(!session.value?.step||!bars||bars.length<2)return null
  const latest=bars.at(-1)!,previous=bars.at(-2)!
  return {date:latest.date,change:(latest.close/previous.close-1)*100}
})
let active=true,generation=0,timer:number|undefined,pollCount=0
let createCommand:CreateReplay|null=null,decisionCommand:ReplayDecisionDraft|null=null,advanceCommand:{clientRequestId:string;expectedStep:number}|null=null
const drafts=new Map<string,{content:string;outlook:Judgment['outlook'];lesson:number|null}>()
const message=(e:unknown)=>e instanceof Error?e.message:'操作尚未完成，请重试'
const storageKey='aiquant-chanlun-replay'
function stopPoll(){if(timer!==undefined)window.clearTimeout(timer);timer=undefined}
function schedulePoll(){
  stopPoll()
  if(active&&session.value?.status==='ADVANCING'&&pollCount<150)timer=window.setTimeout(()=>{pollCount++;void refresh(false)},2000)
}
function accept(value:ReplaySession){
  if(value.analysis.observedBars!==value.observedBars||value.analysis.bars.length!==value.observedBars
    ||value.analysis.bars.some((b,i)=>b.index!==i))throw new Error('练习行情界限校验失败，请恢复进度')
  const previous=session.value
  session.value=value;dataset.value=value.analysis.dataset
  if(!value.analysis.structures.some(s=>s.id===selectedId.value))selectedId.value=value.analysis.structures.filter(s=>s.type==='BI').at(-1)?.id??''
  if(previous?.id!==value.id||previous?.step!==value.step){decisionCommand=null;advanceCommand=null;notice.value=''}
  if(value.status!=='ADVANCING'){pollCount=0;if(value.error)advanceCommand=null}
  try{localStorage.setItem(storageKey,value.id)}catch{}
  schedulePoll()
}
async function refresh(showLoading=true){
  const id=session.value?.id??(typeof route.query.session==='string'?route.query.session:null)
  if(!id)return
  const version=++generation
  if(showLoading)loading.value=true
  try{const value=await replayApi.view(id);if(active&&version===generation){accept(value);error.value=''}}
  catch(e){if(active&&version===generation)error.value=message(e)}
  finally{if(active&&version===generation){loading.value=false;schedulePoll()}}
}
async function resume(id:string){
  stopPoll();const version=++generation;session.value=null;selectedId.value='';busy.value=false;decisionCommand=null;advanceCommand=null;loading.value=true;error.value='';notice.value=''
  try{
    const value=await replayApi.view(id)
    if(!active||version!==generation)return
    accept(value);await router.replace({path:'/chanlun/replay',query:{session:id}})
  }catch(e){if(active&&version===generation)error.value=message(e)}
  finally{if(active&&version===generation)loading.value=false}
}
async function create(){
  if(!dataset.value||busy.value)return
  const body={title:title.value.trim(),engineId:engine.value,datasetId:dataset.value.id,startBars:startBars.value}
  if(!createCommand||JSON.stringify({...createCommand,clientRequestId:undefined})!==JSON.stringify(body))createCommand={...body,clientRequestId:requestUuid()}
  const command=createCommand;const version=++generation;busy.value=true;error.value='';notice.value=''
  try{
    const value=await replayApi.create(command)
    if(!active||version!==generation)return
    accept(value);createCommand=null;await router.replace({path:'/chanlun/replay',query:{session:value.id}})
    recent.value=await replayApi.recent()
  }catch(e){if(active&&version===generation){error.value=message(e);if(e instanceof ApiError&&e.status===422)createCommand=null}}
  finally{if(active&&version===generation)busy.value=false}
}
async function submit(){
  if(!editable.value||!draft.value.trim()||!session.value)return
  const current=session.value
  const body={expectedStep:current.step,structureId:selected.value?.id??null,outlook:outlook.value,content:draft.value.trim(),lessonNumber:linkedLesson.value}
  if(!decisionCommand||JSON.stringify({...decisionCommand,clientRequestId:undefined})!==JSON.stringify(body))decisionCommand={...body,clientRequestId:requestUuid()}
  const version=++generation;busy.value=true;error.value='';notice.value=''
  try{const value=await replayApi.decide(current.id,decisionCommand);if(active&&version===generation){accept(value);notice.value='当时判断已锁定，可展开下一根。'}}
  catch(e){if(active&&version===generation)error.value=message(e)}
  finally{if(active&&version===generation)busy.value=false}
}
async function advance(){
  if(!session.value||busy.value||loading.value||!session.value.decisionSubmitted||session.value.status!=='ACTIVE')return
  const current=session.value
  if(!advanceCommand||advanceCommand.expectedStep!==current.step)advanceCommand={clientRequestId:requestUuid(),expectedStep:current.step}
  const version=++generation;busy.value=true;error.value='';notice.value=''
  try{const value=await replayApi.advance(current.id,advanceCommand);if(active&&version===generation)accept(value)}
  catch(e){
    if(active&&version===generation){
      error.value=message(e)
      try{const value=await replayApi.view(current.id);if(active&&version===generation)accept(value)}catch{}
      if(session.value?.id===current.id&&session.value.status==='ACTIVE')advanceCommand=null
    }
  }finally{if(active&&version===generation){busy.value=false;schedulePoll()}}
}
function read(){
  const references=selected.value?.evidence?.referenceLessons
  if(Array.isArray(references)){const valid=references.find(n=>Number.isInteger(n)&&n>=1&&n<=108);if(valid)lesson.value=valid}
  showReader.value=true;linkedLesson.value=lesson.value
}
async function newSession(){
  stopPoll();generation++;session.value=null;selectedId.value='';createCommand=null;decisionCommand=null;advanceCommand=null;busy.value=false;loading.value=false;error.value='';notice.value=''
  try{localStorage.removeItem(storageKey)}catch{}
  await router.replace({path:'/chanlun/replay'})
}
watch([()=>session.value?.id,()=>session.value?.step,selectedId],([id,step,structure],[oldId,oldStep,oldStructure])=>{
  if(oldId)drafts.set(`${oldId}:${oldStep}:${oldStructure}`,{content:draft.value,outlook:outlook.value,lesson:linkedLesson.value})
  const saved=id?drafts.get(`${id}:${step}:${structure}`):null
  draft.value=saved?.content??'';outlook.value=saved?.outlook??'WAIT';linkedLesson.value=saved?.lesson??(showReader.value?lesson.value:null)
})
watch(()=>route.query.session,id=>{if(typeof id==='string'&&id!==session.value?.id)void resume(id)})
onMounted(async()=>{
  const results=await Promise.allSettled([chanlunApi.engines(),chanlunApi.datasets(),replayApi.recent()])
  if(!active)return
  if(results[0].status==='fulfilled')engines.value=results[0].value
  if(results[1].status==='fulfilled')dataset.value=results[1].value[0]??null
  else metadataError.value=message(results[1].reason)
  if(results[2].status==='fulfilled')recent.value=results[2].value
  let id=typeof route.query.session==='string'?route.query.session:null
  if(!id)try{id=localStorage.getItem(storageKey)}catch{}
  if(id&&id!==session.value?.id)await resume(id)
  else loading.value=false
})
onUnmounted(()=>{active=false;generation++;stopPoll()})
</script>

<template>
  <div class="replay-page">
    <header class="replay-title"><div><p>CHAN THEORY / 逐根训练</p><h2>先留下判断，再展开下一根</h2><p>练习当时能看见的结构，回看自己的依据与修订。</p></div><span class="replay-badge">冻结历史 · 遮挡练习</span></header>
    <ChanlunNavigation active="replay" :session-id="session?.id" :context="session?{run:session.analysis.runId,structure:selectedId||undefined}:{}"/>
    <ChanlunSourceBar :analysis="analysis" :dataset="dataset"/>
    <p v-if="error" role="alert" class="replay-error">{{error}}</p><p v-if="metadataError&&!session" class="replay-error">{{metadataError}}</p>
    <p v-if="loading" role="status">正在恢复服务器保存的练习进度…</p>
    <section v-if="!session" class="replay-panel setup-panel">
      <h3>新建逐根练习</h3><p>先观察已有 K 线，写下理由与失效条件。每次只展开下一根，判断提交后保留原记录。</p>
      <fieldset :disabled="busy||loading"><label>练习名称<input v-model="title" maxlength="120" placeholder="我的逐根练习"></label><label>结构引擎<select v-model="engine"><option value="native">AI-QUANT 自研引擎</option><option v-for="item in engines.filter(e=>e.id!=='native')" :key="item.id" :value="item.id" :disabled="item.status!=='AVAILABLE'">{{item.name}}</option></select></label><label>先观察多少根 K 线<input v-model.number="startBars" type="number" min="50" :max="(dataset?.bars??1894)-1" step="1"></label><button type="button" class="primary" :disabled="!dataset||!Number.isInteger(startBars)||startBars<50||startBars>=(dataset?.bars??1894)" @click="create">{{busy?'准备当前结构…':'开始练习'}}</button></fieldset>
      <p class="replay-note">当前使用 FU 冻结日线。已看过该区间的走势可作为复习；这里不把单根涨跌当作缠论划分正确率。</p>
    </section>
    <template v-if="session&&analysis">
      <section class="replay-progress replay-panel"><div><h3>{{session.title}}</h3><p>{{names[session.engineId]}} · 截至 {{analysis.observedAsOfDate}} · 已观察 {{session.observedBars}} 根</p></div><div class="replay-actions"><span>{{session.status==='COMPLETE'?'已到数据末端':session.status==='ADVANCING'?'服务器正在推进':'第 '+session.step+' 步'}}</span><button type="button" :disabled="busy||loading" @click="refresh()"><RefreshCw :size="15"/>恢复进度</button><button type="button" :disabled="busy" @click="newSession">新建练习</button></div></section>
      <p v-if="session.error" role="alert" class="replay-error">{{session.error}}</p>
      <p v-if="session.status==='ADVANCING'" role="status" class="replay-note">已保存判断，正在计算下一根。可离开后用会话地址恢复。</p>
      <div class="replay-workspace">
        <section class="replay-panel replay-chart">
          <div class="replay-layers"><label v-for="kind in allKinds" :key="kind"><input v-model="layer[kind]" type="checkbox" :disabled="!analysis.layers.includes(kind)">{{kinds[kind]}}</label></div>
          <TongdaxinChart :points="points" :overlays="overlays" :selected-overlay-id="selectedId" :initial-visible-bars="72" symbol="FU0" display-name="当前可见的连续信号价格" default-theme="light" :height="410" @select-structure="selectedId=$event"/>
          <p class="replay-note">图表与缩放范围仅包含当前已展开的行情。连续信号价供结构研究使用，不作为交割合约成交价。</p>
        </section>
        <aside class="replay-panel replay-evidence" aria-label="当前观察对象">
          <h3>当前观察对象</h3><label>选择结构<select v-model="selectedId"><option value="">整体走势</option><option v-for="item in objects" :key="item.id" :value="item.id">{{kinds[item.type]}} · {{item.pivotStartDate}} → {{item.pivotEndDate}}</option></select></label>
          <dl v-if="selected"><dt>图上端点</dt><dd>{{selected.pivotEndDate}}</dd><dt>首次观察</dt><dd>{{selected.firstObservedDate}}</dd><dt>修订</dt><dd>{{selected.revision}}</dd><dt>原始状态</dt><dd>{{selected.signalState??(selected.engineConfirmed?'引擎确定':'动态 / 未提供')}}</dd><dt>交易资格</dt><dd>未评估</dd></dl>
          <details v-if="selected?.evidence"><summary>计算依据</summary><pre>{{JSON.stringify(selected.evidence,null,2)}}</pre></details>
          <button type="button" @click="read"><BookOpen :size="16"/>在系统内查阅原文</button>
        </aside>
      </div>
      <section v-if="revealed" class="replay-panel reveal-feedback" aria-label="已展开行情的反馈"><h3>最近展开 · {{revealed.date}}</h3><p>信号收盘价较前一根变化 {{revealed.change>=0?'+':''}}{{revealed.change.toFixed(2)}}%。这是价格变化，不是账户收益或理论正确率。</p><p v-if="feedback">{{feedback}}</p></section>
      <section class="replay-panel replay-editor">
        <header><h3>{{session.status==='COMPLETE'?'本段练习已完成':session.decisionSubmitted?'本步判断已留档':'写下当时的判断'}}</h3><span>观察日 {{analysis.observedAsOfDate}}</span></header>
        <template v-if="session.status!=='COMPLETE'">
          <fieldset :disabled="!editable"><label>观察倾向<select v-model="outlook"><option value="WAIT">等待 / 不判断</option><option value="UP">向上观察</option><option value="DOWN">向下观察</option></select></label><label>依据与失效条件<textarea v-model="draft" rows="4" maxlength="6000" placeholder="你看到了什么结构？出现什么情况会改变判断？"/></label></fieldset>
          <p v-if="session.decisionSubmitted" class="replay-note">{{session.decisions.find(d=>d.step===session!.step)?.content}}</p>
          <div class="replay-actions"><button type="button" class="primary" :disabled="!editable||!draft.trim()" @click="submit"><Save :size="15"/>提交当时判断</button><button type="button" :disabled="busy||loading||!session.decisionSubmitted||session.status!=='ACTIVE'" @click="advance"><StepForward :size="16"/>展开下一根</button><span v-if="linkedLesson">参考原文：第{{linkedLesson}}课</span></div>
        </template>
        <p v-else>所有已提交判断保留在下方时间线与判断档案中，可回到当时图表逐条复盘。</p>
      </section>
      <p v-if="notice" role="status" class="replay-notice">{{notice}}</p>
      <section class="replay-panel decision-timeline"><h3>判断时间线</h3><p v-if="!session.decisions.length" class="replay-note">尚未提交判断。</p><article v-for="item in session.decisions" :key="item.id"><header><strong>第{{item.step}}步 · {{item.evidence.observedAsOfDate}}</strong><span>{{item.outlook==='UP'?'向上观察':item.outlook==='DOWN'?'向下观察':'等待 / 不判断'}}</span></header><p>{{item.content}}</p><RouterLink :to="{path:'/chanlun/workbench',query:{run:item.runId,structure:item.structureId??undefined,lesson:item.evidence.lessonNumber}}">回到当时图表</RouterLink></article></section>
    </template>
    <section v-if="showReader" class="replay-panel replay-reader"><header><h3>原文参考阅读</h3><button type="button" @click="showReader=false">收起原文</button></header><ChanlunReader :initial-chapter="lesson" @chapter-change="lesson=$event;linkedLesson=$event"/></section>
    <section v-if="recent.length&&!session" class="replay-panel recent-sessions"><h3>继续已有练习</h3><button v-for="item in recent" :key="item.id" type="button" :disabled="busy||loading" @click="resume(item.id)"><span>{{item.title}} · {{names[item.engineId]}}</span><span>第{{item.step}}步 / 已观察{{item.observedBars}}根</span></button></section>
  </div>
</template>

<style scoped>
.replay-page{color:#293b31;min-width:0}.replay-title{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap;margin-bottom:1.4rem}.replay-title h2{font-size:1.6rem;margin:.25rem 0}.replay-title p{font-size:.78rem;color:#657066;margin:.5rem 0}.replay-title p:first-child{font-size:.67rem;letter-spacing:.1em}.replay-badge{font-size:.72rem;color:#365c48;background:#e9eee5;padding:.4rem .65rem;border-radius:.35rem}.replay-panel{min-width:0;background:#fffefa;border:1px solid #dedfd5;border-radius:.6rem;padding:1rem;margin-bottom:1rem}.replay-panel h3{font-size:.95rem;margin:0 0 .7rem}.replay-panel p{font-size:.8rem;line-height:1.9}.replay-note{font-size:.74rem!important;color:#657066;line-height:1.8}.replay-page fieldset{border:0;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:.8rem;align-items:end}.replay-page label{display:grid;gap:.4rem;font-size:.76rem;min-width:0}.replay-page :is(input:not([type=checkbox]),select,textarea){box-sizing:border-box;min-width:0;max-width:100%;width:100%;font:inherit;font-size:.82rem;border:1px solid #dedfd5;border-radius:.35rem;padding:.55rem;background:#fffefa;color:#293b31}.replay-page textarea{resize:vertical}.replay-page button{font:inherit;font-size:.78rem;color:#293b31;border:1px solid #dedfd5;border-radius:.35rem;background:#fffefa;padding:.55rem .75rem;display:inline-flex;align-items:center;justify-content:center;gap:.4rem;cursor:pointer}.replay-page button.primary{background:#365c48;border-color:#365c48;color:#fff}.replay-page button:disabled{opacity:.45;cursor:default}.replay-progress{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap}.replay-progress h3{margin:0}.replay-progress p{margin:.5rem 0 0}.replay-actions{display:flex;gap:.7rem;align-items:center;flex-wrap:wrap}.replay-actions span{font-size:.74rem;color:#657066}.replay-workspace{display:grid;grid-template-columns:minmax(0,1fr) 285px;gap:1rem}.replay-layers{display:flex;gap:.7rem;flex-wrap:wrap;margin-bottom:.8rem}.replay-layers label{display:flex;align-items:center;gap:.25rem;min-height:28px}.replay-layers input{accent-color:#365c48}.replay-evidence label{margin-bottom:1rem}.replay-evidence dl{display:grid;grid-template-columns:5rem minmax(0,1fr);font-size:.75rem;line-height:1.8;gap:.5rem;margin:.8rem 0}.replay-evidence dt{color:#657066}.replay-evidence dd{margin:0;overflow-wrap:anywhere}.replay-evidence details{font-size:.74rem;margin:1rem 0}.replay-evidence pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}.replay-evidence button{width:100%}.replay-editor header,.replay-reader header{display:flex;justify-content:space-between;align-items:center;gap:.8rem;margin-bottom:1rem;flex-wrap:wrap}.replay-editor header span{font-size:.74rem;color:#657066}.replay-editor fieldset{grid-template-columns:10rem minmax(0,1fr);align-items:start;margin-bottom:.8rem}.replay-error{font-size:.8rem;line-height:1.8;padding:.8rem;color:#8c3e32;border-left:3px solid #a54e3d;background:#fbf0e9}.replay-notice{font-size:.8rem;padding:.8rem;background:#e8efe3}.decision-timeline article{border-top:1px solid #dedfd5;padding:.8rem 0}.decision-timeline header{display:flex;justify-content:space-between;gap:.8rem;flex-wrap:wrap;font-size:.76rem}.decision-timeline article p{white-space:pre-wrap;overflow-wrap:anywhere}.decision-timeline a{font-size:.75rem;color:#365c48}.recent-sessions button{display:flex;width:100%;justify-content:space-between;gap:1rem;margin:.5rem 0;text-align:left;flex-wrap:wrap}.recent-sessions span{font-size:.76rem}.replay-page :is(button,input,select,textarea,a):focus-visible{outline:2px solid #9e784b;outline-offset:3px}@media(max-width:1100px){.replay-workspace{grid-template-columns:minmax(0,1fr)}}@media(max-width:600px){.replay-panel{padding:.75rem}.replay-editor fieldset{grid-template-columns:minmax(0,1fr)}.replay-title h2{font-size:1.3rem}.replay-page :is(input:not([type=checkbox]),select,textarea){font-size:16px}.replay-page :deep(.chanlun-reader){padding:.2rem}}@media(pointer:coarse){.replay-page button,.replay-page select,.replay-layers label{min-height:44px}}
</style>

<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {RouterLink,useRoute,useRouter} from 'vue-router'
import TongdaxinChart from '../../components/TongdaxinChart.vue'
import ChanlunReader from '../../components/ChanlunReader.vue'
import ChanlunNavigation from './ChanlunNavigation.vue'
import ChanlunSourceBar from './ChanlunSourceBar.vue'
import {requestUuid} from '../../utils/requestId'
import {chanlunApi,type Analysis,type Dataset,type Engine,type EngineId,type StructureEvent,type Judgment} from './api'
import {comparisonApi,type ComparisonDraft,type ComparisonRun,type ComparisonDetail,type ComparisonSummary,type ComparisonLayer,type ComparisonJudgment} from './comparison'

const route=useRoute(),router=useRouter()
const engines=ref<Engine[]>([]),dataset=ref<Dataset|null>(null),sources=ref<EngineId[]>(['native','chanpy','czsc'])
const count=ref(501),layer=ref<ComparisonLayer>('BI'),projection=ref<ComparisonDraft['projection']>('GEOMETRY'),confirmedOnly=ref(false)
const current=ref<ComparisonRun|null>(null),detail=ref<ComparisonDetail|null>(null),recent=ref<ComparisonSummary[]>([])
const busy=ref(false),loading=ref(false),saving=ref(false),error=ref(''),catalogError=ref(''),archiveError=ref(''),notice=ref(''),targetIndex=ref(0)
const sourceId=ref(''),structureId=ref(''),events=ref<StructureEvent[]>([]),eventError=ref(''),content=ref(''),outlook=ref<Judgment['outlook']>('WAIT')
const reader=ref(false),lesson=ref(62),linkedLesson=ref<number|null>(null)
const names:Record<EngineId,string>={native:'AI-QUANT 自研',chanpy:'chan.py',czsc:'CZSC',baseline:'研究基线'}
const kinds:Record<ComparisonLayer,string>={BI:'笔',SEGMENT:'线段',ZONE:'中枢'}
const report=computed(()=>current.value?.report)
const selectedFrame=computed(()=>detail.value?.frames.find(f=>f.sourceRunId===sourceId.value))
const objects=computed(()=>(selectedFrame.value?.analysis.structures??[]).filter(s=>s.type===report.value?.layer&&(!report.value.confirmedOnly||s.engineConfirmed===true)))
const selected=computed(()=>objects.value.find(s=>s.id===structureId.value))
const chartData=computed(()=>new Map((detail.value?.frames??[]).map(f=>[f.sourceRunId,{
  points:f.analysis.bars.map((b,i,bars)=>({timestamp:b.timestamp,contract:b.contract,price:b.close,open:b.open,high:b.high,low:b.low,volume:b.volume,changePct:i?(b.close/bars[i-1]!.close-1)*100:0,changePctKnown:i>0})),
  overlays:f.analysis.structures.filter(s=>s.type===report.value?.layer&&(!report.value.confirmedOnly||s.engineConfirmed===true)),
}])))
const selectedContext=computed(()=>detail.value?`${detail.value.comparisonId}:${detail.value.observedIndex}:${sourceId.value}:${structureId.value}`:'')
let alive=true,generation=0,evidenceGeneration=0,eventGeneration=0
let command:ComparisonDraft|null=null,saveCommand:{comparisonId:string;index:number;body:ComparisonJudgment}|null=null
const computations=new Map<string,string>(),cache=new Map<string,Analysis>()
const drafts=new Map<string,{content:string;outlook:Judgment['outlook'];lesson:number|null}>()
const failure=(e:unknown)=>e instanceof Error?e.message:'请求未完成，请重试'
function flag(v:boolean|null){return v===true?'当前确定':v===false?'动态':'未提供确定标记'}
function defaultLesson(){return report.value?.layer==='SEGMENT'?67:report.value?.layer==='ZONE'?20:62}
async function refreshRecent(){try{const value=await comparisonApi.list();if(alive)recent.value=value}catch(e){if(alive)archiveError.value=failure(e)}}
async function catalog(){
  const results=await Promise.allSettled([chanlunApi.engines(),chanlunApi.datasets()]);if(!alive)return
  if(results[0].status==='fulfilled')engines.value=results[0].value
  if(results[1].status==='fulfilled'&&!dataset.value)dataset.value=results[1].value[0]??null
  catalogError.value=results.flatMap(r=>r.status==='rejected'?[failure(r.reason)]:[]).join('；')
}
async function inspect(index:number,updateUrl=true){
  if(!current.value?.report)return
  const id=current.value.id,version=++evidenceGeneration
  detail.value=null;sourceId.value='';structureId.value='';events.value=[];error.value='';loading.value=true
  if(!Number.isInteger(index)||index<0||index>=current.value.report.observedBars){error.value='取证时点超出此对照范围，请选择有效根数。';loading.value=false;return}
  targetIndex.value=index
  try{
    const value=await comparisonApi.at(id,index)
    if(!alive||version!==evidenceGeneration||id!==current.value?.id)return
    if(value.comparisonId!==id||value.observedIndex!==index||value.frames.some(f=>f.analysis.observedBars!==index+1||f.analysis.bars.length!==index+1))throw new Error('取证结果与请求时点不一致')
    detail.value=value;sourceId.value=value.frames[0]?.sourceRunId??'';if(value.frames[0])dataset.value=value.frames[0].analysis.dataset
    if(updateUrl)await router.replace({path:'/chanlun/compare',query:{comparison:id,at:String(index)}})
  }catch(e){if(alive&&version===evidenceGeneration)error.value=failure(e)}finally{if(alive&&version===evidenceGeneration)loading.value=false}
}
async function accept(value:ComparisonRun,index?:number){
  current.value=value;detail.value=null;sourceId.value='';structureId.value=''
  if(value.status==='FAILED'){error.value=value.error??'对照未完成，请重新创建';return}
  if(value.report)await inspect(index??value.report.firstDifference?.observedIndex??value.report.observedBars-1)
  else notice.value='对照仍在计算，可继续读取原档案。'
}
async function restore(id:string){
  const version=++generation;++evidenceGeneration;loading.value=false;busy.value=true;error.value='';notice.value='';current.value=null;detail.value=null;command=null
  try{const value=await comparisonApi.get(id);if(!alive||version!==generation)return;const query=route.query.at;await accept(value,query===undefined?undefined:typeof query==='string'&&/^\d+$/.test(query)?Number(query):NaN)}
  catch(e){if(alive&&version===generation)error.value=failure(e)}finally{if(alive&&version===generation)busy.value=false}
}
async function compute(id:EngineId,total:number,data:Dataset){
  const key=`${data.sha256}:${id}:${total}`;if(cache.has(key))return cache.get(key)!
  if(!computations.has(key))computations.set(key,requestUuid())
  const run=await chanlunApi.create({clientRequestId:computations.get(key)!,engineId:id,datasetId:data.id,observedBars:total})
  if(run.status==='FAILED'){computations.delete(key);throw new Error(`${names[id]}：${run.error??'计算失败'}`)}
  if(run.status!=='SUCCEEDED')throw new Error(`${names[id]}仍在计算，请重试以复用原任务。`)
  const value=await chanlunApi.result(run.id)
  if(value.engineId!==id||value.observedBars!==total||value.datasetHash!==data.sha256)throw new Error('引擎返回了不同输入，请重新创建分析')
  cache.set(key,value);return value
}
async function create(){
  if(busy.value||loading.value||saving.value)return
  if(!dataset.value||sources.value.length<2||sources.value.length>4){error.value='请先载入行情目录，并选择两个至四个引擎。';return}
  if(!Number.isInteger(count.value)||count.value<50||count.value>dataset.value.bars){error.value='请填写有效的观察根数（至少50根）。';return}
  if(sources.value.some(id=>!engines.value.find(e=>e.id===id)?.layers.includes(layer.value))){error.value='所选引擎未全部提供此图层，请更换图层或取消该来源。';return}
  if(confirmedOnly.value&&layer.value==='ZONE'&&sources.value.includes('czsc')){error.value='CZSC中枢未提供确定标记，请选择全部已观察结构。';return}
  const version=++generation;++evidenceGeneration;loading.value=false;busy.value=true;error.value='';notice.value='';detail.value=null;current.value=null
  const data=dataset.value,ids=[...sources.value],total=count.value,settings={layer:layer.value,projection:projection.value,confirmedOnly:confirmedOnly.value}
  try{
    const results:Analysis[]=[]
    for(let offset=0;offset<ids.length;offset+=3){
      const batch=await Promise.allSettled(ids.slice(offset,offset+3).map(id=>compute(id,total,data)))
      if(!alive||version!==generation)return
      const failures=batch.flatMap(r=>r.status==='rejected'?[failure(r.reason)]:[])
      if(failures.length)throw new Error(failures.join('；')+'；全部来源成功后才会创建对照。')
      results.push(...batch.flatMap(r=>r.status==='fulfilled'?[r.value]:[]))
    }
    const body={runIds:results.map(r=>r.runId),...settings}
    if(!command||JSON.stringify({...command,clientRequestId:undefined})!==JSON.stringify(body))command={...body,clientRequestId:requestUuid()}
    const value=await comparisonApi.create(command)
    if(!alive||version!==generation)return
    await accept(value);if(!value.report)await router.replace({path:'/chanlun/compare',query:{comparison:value.id}})
    await refreshRecent();if(value.status==='FAILED')command=null
  }catch(e){if(alive&&version===generation)error.value=failure(e)}finally{if(alive&&version===generation)busy.value=false}
}
function choose(source:string,id:string){sourceId.value=source;structureId.value=id}
function chooseEvidence(engineId:EngineId,id:string){const source=detail.value?.frames.find(f=>f.analysis.engineId===engineId);if(source)choose(source.sourceRunId,id)}
async function prepareSource(id:string){
  const version=++generation;busy.value=true
  try{const value=await chanlunApi.result(id);if(!alive||version!==generation)return
    if(value.observedBars<50){notice.value='来源是早期冻结前缀。新对照至少需要50根，请另选观察根数。';return}
    count.value=value.observedBars;dataset.value=value.dataset;cache.set(`${value.datasetHash}:${value.engineId}:${value.observedBars}`,value)
    notice.value=`已沿用工作台的${value.observedBars}根输入界限，创建对照后再取证。`
  }catch(e){if(alive&&version===generation)error.value=failure(e)}finally{if(alive&&version===generation)busy.value=false}
}
function book(){const refs=selected.value?.evidence?.referenceLessons;lesson.value=Array.isArray(refs)&&Number.isInteger(refs[0])?Number(refs[0]):defaultLesson();reader.value=true;linkedLesson.value=lesson.value}
watch(sourceId,()=>{structureId.value='';events.value=[]},{flush:'sync'})
watch(selectedContext,(key,previous)=>{
  if(previous)drafts.set(previous,{content:content.value,outlook:outlook.value,lesson:linkedLesson.value})
  const saved=drafts.get(key);content.value=saved?.content??'';outlook.value=saved?.outlook??'WAIT';linkedLesson.value=saved?.lesson??null
})
watch([sourceId,structureId,()=>detail.value?.observedIndex],async()=>{
  const version=++eventGeneration;events.value=[];eventError.value=''
  if(!current.value||!detail.value||!sourceId.value||!structureId.value)return
  try{const value=await comparisonApi.events(current.value.id,sourceId.value,detail.value.observedIndex,structureId.value);if(alive&&version===eventGeneration)events.value=value}catch(e){if(alive&&version===eventGeneration)eventError.value=failure(e)}
})
async function save(){
  if(!current.value||!detail.value||!sourceId.value||!content.value.trim()||saving.value||loading.value)return
  const context=selectedContext.value,comparisonId=current.value.id,index=detail.value.observedIndex
  const body={sourceRunId:sourceId.value,structureId:selected.value?.id??null,outlook:outlook.value,content:content.value.trim(),lessonNumber:linkedLesson.value}
  if(!saveCommand||saveCommand.comparisonId!==comparisonId||saveCommand.index!==index||JSON.stringify({...saveCommand.body,clientRequestId:undefined})!==JSON.stringify(body))saveCommand={comparisonId,index,body:{...body,clientRequestId:requestUuid()}}
  const attempt=saveCommand;saving.value=true;error.value=''
  try{await comparisonApi.judge(attempt.comparisonId,attempt.index,attempt.body);if(!alive)return;if(context===selectedContext.value&&content.value.trim()===attempt.body.content)content.value='';saveCommand=null;notice.value='判断与当时前缀已保存，可在独立判断中恢复。'}catch(e){if(alive)error.value=failure(e)}finally{if(alive)saving.value=false}
}
watch(()=>[route.query.comparison,route.query.at] as const,([id,at])=>{
  if(typeof id!=='string')return
  if(id!==current.value?.id){void restore(id);return}
  if(at!==undefined&&String(detail.value?.observedIndex)!==at&&!loading.value){void inspect(typeof at==='string'&&/^\d+$/.test(at)?Number(at):NaN,false)}
})
onMounted(()=>{if(typeof route.query.comparison==='string')void restore(route.query.comparison);else if(typeof route.query.run==='string')void prepareSource(route.query.run);void catalog();void refreshRecent()})
onUnmounted(()=>{alive=false;generation++;evidenceGeneration++;eventGeneration++})
</script>
<template><main class="compare"><ChanlunNavigation active="compare" :context="selectedFrame?{run:selectedFrame.analysis.runId}:{}"/><ChanlunSourceBar :analysis="selectedFrame?.analysis" :dataset="dataset"/>
  <header><p class="eyebrow">观察事件 · 首次分歧 · 原文取证</p><h1>引擎分歧研究</h1><p>从每根日线当时的观察记录重建结构，定位首次分歧，再核对端点与各引擎的确定口径。</p></header>
  <form class="config" @submit.prevent="create"><fieldset :disabled="busy||loading||saving"><legend>相同输入下的新对照 · FU 冻结日线</legend><div class="controls"><label v-for="id in (['native','chanpy','czsc','baseline'] as const)" :key="id" class="inline"><input v-model="sources" type="checkbox" :value="id"/>{{names[id]}}<small v-if="engines.find(e=>e.id===id)?.status==='UNAVAILABLE'">服务不可用</small></label><label>观察根数<input v-model.number="count" type="number" min="50" :max="dataset?.bars??1894" required/></label><label>比较图层<select v-model="layer"><option v-for="(name,key) in kinds" :key="key" :value="key">{{name}}</option></select></label><label>比较范围<select v-model="projection"><option value="GEOMETRY">结构几何</option><option value="WITH_CONFIRMATION">结构几何及确定标记</option></select></label><label class="inline"><input v-model="confirmedOnly" type="checkbox"/>只纳入各引擎标为确定的结构</label><button type="submit" :disabled="!dataset">{{busy?'正在准备来源与对照…':'创建并保存对照'}}</button></div></fieldset></form>
  <p v-if="catalogError" class="error">新分析目录：{{catalogError}} <button @click="catalog">重试目录</button></p><p v-if="error" role="alert" class="error">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
  <p v-if="busy&&!report" role="status">正在载入或创建对照…</p><button v-if="current?.status==='RUNNING'" :disabled="busy" @click="restore(current.id)">继续读取原档案</button>
  <template v-if="report"><section class="bounds"><h2>{{kinds[report.layer]}} · {{report.projection==='GEOMETRY'?'结构几何':'结构几何及确定标记'}} · {{report.confirmedOnly?'各引擎确定结构':'全部已观察结构'}}</h2><p>完整对照范围 {{report.observedBars}} 根，截至 {{report.observedAsOfDate}}；其中 {{report.differentObservationCount}} 个观察时点有分歧。当前下方图表只返回取证时点及以前的价格与观察。</p><div class="controls"><button :disabled="!report.firstDifference||loading||saving" @click="inspect(report.firstDifference!.observedIndex)">首次所选分歧{{report.firstDifference?' · '+report.firstDifference.date:' · 未发现'}}</button><button :disabled="!report.firstGeometryDifference||loading||saving" @click="inspect(report.firstGeometryDifference!.observedIndex)">首次几何分歧</button><button :disabled="!report.firstConfirmationDifference||loading||saving" @click="inspect(report.firstConfirmationDifference!.observedIndex)">首次确定标记分歧</button></div><label class="prefix">取证观察根数：{{targetIndex+1}} / {{report.observedBars}}<input v-model.number="targetIndex" type="range" min="0" :max="report.observedBars-1" :disabled="loading||saving"/></label><div class="controls"><button :disabled="targetIndex<=0||loading||saving" @click="inspect(targetIndex-1)">上一根</button><button :disabled="targetIndex>=report.observedBars-1||loading||saving" @click="inspect(targetIndex+1)">下一根</button><button :disabled="loading||saving" @click="inspect(targetIndex)">载入所选时点</button></div><details><summary>连续分歧区间（{{report.spans.length}}段）</summary><div class="spans"><button v-for="span in report.spans" :key="span.startIndex" :disabled="loading||saving" @click="inspect(span.startIndex)">{{report.timeline[span.startIndex]?.date}} → {{report.timeline[span.endIndex]?.date}}</button></div></details></section>
    <p v-if="loading" role="status">正在从存档事件重建该时点…</p>
    <template v-if="detail"><h2 class="asof">当时取证 · {{detail.date}} · {{detail.observedIndex+1}} 根</h2><div class="charts"><section v-for="frame in detail.frames" :key="`${detail.comparisonId}:${detail.observedIndex}:${frame.sourceRunId}`" class="frame"><h2>{{names[frame.analysis.engineId]}} · {{chartData.get(frame.sourceRunId)?.overlays.length}} 个{{kinds[report.layer]}}</h2><TongdaxinChart :points="chartData.get(frame.sourceRunId)!.points" :overlays="chartData.get(frame.sourceRunId)!.overlays" :selected-overlay-id="sourceId===frame.sourceRunId?structureId:undefined" symbol="FU0" display-name="燃油 · 连续信号价格" default-theme="light" :height="330" :initial-visible-bars="72" @select-structure="choose(frame.sourceRunId,$event)"/><details><summary>来源版本</summary><p>{{frame.analysis.engineVersion}}</p><code>{{frame.analysis.profileHash}}</code><p>原分析 {{frame.sourceRunId}}</p></details></section></div>
      <section class="pair-panel"><h2>此时点逐对取证</h2><p class="muted">按类型、端点索引、方向和价格一一匹配；价格绝对容差 {{report.priceTolerance}}。不同起点不会被强行归为同一结构。</p><article v-for="pair in detail.pairs" :key="pair.summary.left+pair.summary.right"><h3>{{names[pair.summary.left]}} / {{names[pair.summary.right]}}</h3><p>几何匹配 {{pair.summary.matched}}；左侧未匹配 {{pair.summary.leftOnly}}，右侧未匹配 {{pair.summary.rightOnly}}；几何匹配但确定标记不同 {{pair.summary.confirmationDifferences}}。</p><div class="witnesses"><div v-for="side in (['left','right'] as const)" :key="side"><p>{{names[pair.summary[side]]}} · 未匹配对象（最多8项）</p><button v-for="s in (side==='left'?pair.leftObjects:pair.rightObjects)" :key="s.id" :disabled="saving" @click="chooseEvidence(pair.summary[side],s.id)">{{s.pivotStartDate}} → {{s.pivotEndDate}} · {{s.direction}} · {{flag(s.engineConfirmed)}}</button></div><div v-if="pair.confirmationObjects.length"><p>相同几何的确定标记差异（最多8项）</p><button v-for="item in pair.confirmationObjects" :key="item.left.id" :disabled="saving" @click="chooseEvidence(pair.summary.left,item.left.id)">{{item.left.pivotEndDate}} · {{names[pair.summary.left]}} {{flag(item.left.engineConfirmed)}} / {{names[pair.summary.right]}} {{flag(item.right.engineConfirmed)}}</button></div></div><details><summary>查看原始取证字段</summary><pre>{{JSON.stringify({左侧:pair.leftObjects,右侧:pair.rightObjects,标记:pair.confirmationObjects},null,2)}}</pre></details></article></section>
      <section class="evidence"><h2>核对结构与独立判断</h2><div class="controls"><label>取证来源<select v-model="sourceId" :disabled="saving"><option v-for="f in detail.frames" :key="f.sourceRunId" :value="f.sourceRunId">{{names[f.analysis.engineId]}}</option></select></label><label>结构<select v-model="structureId" :disabled="saving"><option value="">此时点整体判断</option><option v-for="s in objects" :key="s.id" :value="s.id">{{s.pivotStartDate}} → {{s.pivotEndDate}} · {{s.direction}} · r{{s.revision}}</option></select></label><button @click="book">系统内阅读原文</button></div><template v-if="selected"><p>首次观察 {{selected.firstObservedDate}} · {{flag(selected.engineConfirmed)}} · 原始标记 {{selected.rawFlag}}</p><details><summary>该修订的规则证据</summary><pre>{{JSON.stringify(selected.evidence,null,2)}}</pre></details><p v-if="eventError" role="alert">{{eventError}}</p><ol><li v-for="event in events" :key="event.eventSeq">{{event.observedDate}} · {{event.eventType}} · r{{event.revision}}</li></ol></template><label>观察倾向<select v-model="outlook" :disabled="saving"><option value="WAIT">等待 / 不判断</option><option value="UP">向上观察</option><option value="DOWN">向下观察</option></select></label><label>理由与失效条件<textarea v-model="content" rows="3" maxlength="6000" placeholder="记录对分歧的解释，以及改变判断的条件。"/></label><p v-if="linkedLesson" class="muted">引用第{{linkedLesson}}课</p><button :disabled="saving||!content.trim()||!sourceId" @click="save">{{saving?'保存中…':'保存此时点判断'}}</button> <RouterLink to="/chanlun/judgments">查看独立判断</RouterLink></section>
    </template><details><summary>对照范围与限制</summary><ul><li v-for="item in report.limitations" :key="item">{{item}}</li></ul><p>日线日期为交易日标签。此页允许任意历史取证，属于研究回放。换月连续信号价格不作为交割合约成交价。</p><code>输入 {{report.datasetHash}} · {{report.priceBasis}}</code></details>
  </template>
  <section class="archives"><h2>已保存的引擎对照</h2><p v-if="archiveError" role="alert">{{archiveError}}</p><p v-if="!recent.length" class="muted">尚无对照记录，打开此页不会自动计算。</p><ul><li v-for="item in recent" :key="item.id"><button :disabled="busy||loading||saving" @click="router.push({path:'/chanlun/compare',query:{comparison:item.id}})">{{kinds[item.layer]}} · {{item.observedBars??'等待'}} 根 · {{item.status==='SUCCEEDED'?'已保存':item.status==='RUNNING'?'计算中':'未完成'}} · {{item.createdAt}}</button></li></ul></section>
  <section v-if="reader"><button @click="reader=false">收起原文</button><ChanlunReader :initial-chapter="lesson" @chapter-change="lesson=$event;linkedLesson=$event"/></section>
</main></template>
<style scoped>
.compare{max-width:1700px;margin:auto;color:#293b31}h1{font-size:1.8rem;margin:.5rem 0}h2{font-size:1rem}h3{font-size:.9rem}.eyebrow{font-size:.75rem;letter-spacing:.1em;color:#7a725e}header>p:last-child,.muted,.bounds p{font-size:.8rem;line-height:1.8;color:#657066}.config{background:#f0f1e8;padding:1rem;margin:1rem 0;border-radius:.4rem}fieldset{border:0;padding:0;min-width:0}legend{font-size:.85rem;margin-bottom:.8rem}.controls{display:flex;gap:.7rem;flex-wrap:wrap;align-items:end}label{display:grid;gap:.4rem;font-size:.8rem}.inline{display:inline-flex;align-items:center;gap:.4rem;align-self:center}input,select,button,textarea{font:inherit;padding:.55rem .7rem;border:1px solid #c6cdbf;border-radius:.3rem;background:#fff;color:inherit;max-width:100%}input[type=number]{width:7rem}input[type=checkbox]{padding:0}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}.bounds,.evidence,.pair-panel{padding:1rem;border:1px solid #dedfd5;border-radius:.4rem;margin:1rem 0}.prefix{margin:1rem 0}.prefix input{width:100%;padding:0}.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,430px),1fr));gap:1rem}.frame{min-width:0;border:1px solid #dedfd5;border-radius:.4rem;padding:.75rem}.asof{padding:.5rem 0}.evidence>label{margin:.8rem 0}.evidence textarea{width:100%}details{font-size:.78rem;line-height:1.8;margin:.8rem 0}summary{cursor:pointer;font-weight:600}code,pre{overflow-wrap:anywhere;white-space:pre-wrap;font-size:.72rem}pre{max-height:28rem;overflow:auto}.spans{display:flex;flex-wrap:wrap;gap:.5rem;margin:.5rem 0}.archives ul{list-style:none;padding:0}.archives li{margin:.5rem 0}.archives button{font-size:.75rem}.witnesses{display:flex;gap:.8rem;flex-wrap:wrap}.witnesses>div{display:grid;gap:.4rem;align-content:start}.witnesses p{font-size:.75rem;color:#657066}.witnesses button{font-size:.75rem;text-align:left}.error{color:#aa4539}a{color:#436a50;font-size:.8rem}.compare :is(button,input,select,textarea,a):focus-visible{outline:2px solid #9e784b;outline-offset:3px}@media(max-width:600px){.charts{grid-template-columns:1fr}.controls{align-items:stretch}.controls>label:not(.inline){width:100%}select,textarea,input{font-size:16px}h1{font-size:1.4rem}}@media(pointer:coarse){button,select,input:not([type=checkbox]){min-height:44px}}
</style>

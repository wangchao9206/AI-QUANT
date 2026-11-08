<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {RouterLink,useRoute,useRouter} from 'vue-router'
import {BookOpen,RefreshCw,Save,ScanLine} from 'lucide-vue-next'
import TongdaxinChart from '../../components/TongdaxinChart.vue'
import ChanlunReader from '../../components/ChanlunReader.vue'
import ChanlunNavigation from './ChanlunNavigation.vue'
import ChanlunSourceBar from './ChanlunSourceBar.vue'
import {chanObject,historicalResult} from '../../utils/chanlunContext'
import {instrumentLabel} from '../../utils/instrumentNames'
import {requestUuid} from '../../utils/requestId'
import chapters from '../../content/chanlunChapters.json'
import {chanlunApi,type Analysis,type Engine,type EngineId,type Dataset,type Structure,type StructureEvent,type Judgment,type JudgmentDraft} from './api'

const route=useRoute(),router=useRouter()
const engines=ref<Engine[]>([]),dataset=ref<Dataset|null>(null),engine=ref<EngineId>('native'),observed=ref(1894)
const datasets=ref<Dataset[]>([])
const datasetAvailable=computed(()=>!!dataset.value&&datasets.value.some(d=>d.id===dataset.value!.id&&d.sha256===dataset.value!.sha256))
const analysis=ref<Analysis|null>(null),busy=ref(false),error=ref(''),notice=ref(''),selectedId=ref(''),events=ref<StructureEvent[]>([]),eventError=ref('')
const judgments=ref<Judgment[]>([]),journalError=ref(''),saving=ref(false),draft=ref(''),outlook=ref<Judgment['outlook']>('WAIT')
const showReader=ref(false),lesson=ref(62),linkedLesson=ref<number|null>(null),layout=ref('chart')
const layer=ref({FRACTAL:false,BI:true,SEGMENT:false,ZONE:true,BSP:true}),structureFilter=ref<Structure['type']>('BI')
let generation=0,eventGeneration=0,active=true
const cache=new Map<string,Analysis>(),commands=new Map<string,string>()
const drafts=new Map<string,{content:string;outlook:Judgment['outlook'];lesson:number|null}>()
let saveCommand:JudgmentDraft|null=null
const tab=computed(()=>String(route.name??'chanlun-workbench').replace('chanlun-',''))
const names:Record<EngineId,string>={native:'AI-QUANT 自研引擎',chanpy:'chan.py',czsc:'CZSC',baseline:'AI-QUANT 研究基线'}
const types:Record<Structure['type'],string>={FRACTAL:'分型',BI:'笔',SEGMENT:'线段',ZONE:'中枢',BSP:'候选买卖点'}
const allKinds=['FRACTAL','BI','SEGMENT','ZONE','BSP'] as const
const nativeRuleText:Record<string,string>={
  SEALED_THREE_MERGED_CANDLES_V1:'先处理K线包含关系，待右侧合并K线封存后，检查三根合并K线的高低点。',
  SEALED_OPPOSITE_STROKE_V1:'两个相反分型中心至少相隔四根合并K线，待后继反向笔成立后封存。此口径有意保留确认延迟。',
  DYNAMIC_STROKE_V1:'当前末笔仍可延伸，尚未满足封存条件。',
  SEGMENT_FEATURE_FRACTAL_V1:'由反向笔构成特征序列，处理包含后识别分型；存在特征缺口时继续等待反向特征分型。',
  DYNAMIC_SEGMENT_V1:'当前线段尚未通过特征序列的结束判定，端点仍可变化。',
  THREE_BI_FIXED_CORE_ZONE_V1:'三根已封存笔形成严格重叠区间，固定初始中枢边界，并跟踪延伸与离开。这是笔中枢口径。',
  TREND_MACD_AREA_DIVERGENCE_V1:'在两个不重叠趋势中枢之后，比较同向笔创新高低与MACD面积衰减，仅作为一类候选的研究条件。',
  SECOND_POINT_HIGHER_LOW_LOWER_HIGH_V1:'一类候选形成后，等待反弹与再次回撤；低点抬高或高点降低，且原候选尚未失效。',
  THIRD_POINT_STRICT_RETEST_V1:'离开中枢后回踩笔必须严格位于中枢外；若等待确认期间已触及边界，也不生成候选。',
}
const supports=computed(()=>analysis.value?.layers??engines.value.find(e=>e.id===engine.value)?.layers??[])
const selected=computed(()=>analysis.value?.structures.find(s=>s.id===selectedId.value)??null)
const ruleExplanation=computed(()=>nativeRuleText[String(selected.value?.evidence?.ruleId??'')]??'')
const objects=computed(()=>(analysis.value?.structures??[]).filter(s=>s.type===structureFilter.value).slice().reverse())
const overlays=computed(()=>(analysis.value?.structures??[]).filter(s=>layer.value[s.type]))
const points=(item:Analysis)=>item.bars.map((b,i)=>({timestamp:b.timestamp,contract:b.contract,price:b.close,open:b.open,high:b.high,low:b.low,volume:b.volume,changePct:i?(b.close/item.bars[i-1]!.close-1)*100:0,changePctKnown:i>0}))
const chartPoints=computed(()=>analysis.value?points(analysis.value):[])
const failure=(e:unknown)=>e instanceof Error?e.message:'请求失败，请稍后重试'
const queryFor=()=>analysis.value?{run:analysis.value.runId,structure:selectedId.value||undefined}:{}

function accept(result:Analysis){
  historicalResult(result)
  analysis.value=result;engine.value=result.engineId;observed.value=result.observedBars;dataset.value=result.dataset
  cache.set(`${result.dataset.id}:${result.datasetHash}:${result.engineId}:${result.observedBars}`,result)
  if(cache.size>12)cache.delete(cache.keys().next().value!)
  if(!result.layers.includes(structureFilter.value))structureFilter.value='BI'
  const last=result.structures.filter(s=>s.type===structureFilter.value).at(-1)
  const requested=result.structures.find(s=>s.id===route.query.structure)
  if(route.query.structure!==undefined&&!requested)throw new Error('指定结构不在此历史分析中，不替换其他结构。')
  selectedId.value=requested?.id??last?.id??''
  if(requested)structureFilter.value=requested.type
  const requestedLesson=Number(route.query.lesson)
  if(Number.isInteger(requestedLesson)&&requestedLesson>=1&&requestedLesson<=108)lesson.value=requestedLesson
}
async function compute(id:EngineId,count:number,fresh=false){
  const key=`${dataset.value!.id}:${dataset.value!.sha256}:${id}:${count}`
  if(!fresh&&cache.has(key))return cache.get(key)!
  let command=commands.get(key)
  if(!command||fresh){command=requestUuid();commands.set(key,command)}
  const run=await chanlunApi.create({clientRequestId:command,engineId:id,datasetId:dataset.value!.id,observedBars:count})
  if(run.status==='FAILED'){commands.delete(key);throw new Error(run.error??'结构计算失败，请重新分析')}
  if(run.status!=='SUCCEEDED')throw new Error('该分析仍在计算。稍后再次载入会复用同一任务。')
  const result=historicalResult(await chanlunApi.result(run.id),run.id)
  if(result.engineId!==id||result.observedBars!==count||result.datasetHash!==dataset.value?.sha256)throw new Error('结果来源与所选条件不一致，请重试')
  cache.set(key,result);return result
}
async function load(fresh=false){
  if(observed.value<50){error.value='新分析至少需要50根日线。当前较早时点可按存档取证查看。';return}
  if(!dataset.value||!datasetAvailable.value){error.value='历史数据集与当前目录版本不一致，请先选择目录中的数据集。';return}
  const version=++generation
  error.value='';notice.value='';analysis.value=null;events.value=[];selectedId.value=''
  busy.value=true
  try{
    const result=await compute(engine.value,observed.value,fresh)
    if(!active||version!==generation)return
    accept(result)
    await router.replace({path:route.path,query:{...route.query,run:result.runId,structure:selectedId.value||undefined}})
  }catch(e){if(active&&version===generation)error.value=failure(e)}
  finally{if(active&&version===generation)busy.value=false}
}
async function restore(id:string){
  const version=++generation;analysis.value=null;selectedId.value='';events.value=[];busy.value=true;error.value=''
  try{if(!chanObject(id))throw new Error('历史分析标识无效。');const result=historicalResult(await chanlunApi.result(id),id);if(active&&version===generation)accept(result)}
  catch(e){if(active&&version===generation)error.value=failure(e)}
  finally{if(active&&version===generation)busy.value=false}
}
async function initialize(){
  busy.value=true;error.value=''
  const existing=typeof route.query.run==='string'?route.query.run:null
  if(route.query.run!==undefined&&!existing||route.query.structure!==undefined&&!existing){error.value='历史分析或结构关联标识无效。';busy.value=false;return}
  if(existing)await restore(existing)
  const results=await Promise.allSettled([chanlunApi.engines(),chanlunApi.datasets(),chanlunApi.judgments()])
  if(!active)return
  const [e,d,j]=results
  if(e.status==='fulfilled')engines.value=e.value
  if(d.status==='rejected')error.value=failure(d.reason)
  if(d.status==='fulfilled'){datasets.value=d.value;if(!analysis.value&&!existing){dataset.value=d.value.find(item=>item.id===route.query.dataset)??(route.query.dataset===undefined?d.value[0]??null:null);if(!dataset.value&&route.query.dataset!==undefined)error.value='指定历史数据集不在目录中，不替换其他数据集。';if(dataset.value)observed.value=Math.min(observed.value,dataset.value.bars)}}
  if(j.status==='fulfilled')judgments.value=j.value;else journalError.value=failure(j.reason)
  busy.value=false
}
function chooseDataset(event:Event){const key=(event.target as HTMLSelectElement).value,item=datasets.value.find(d=>`${d.id}:${d.sha256}`===key);if(!item)return;++generation;analysis.value=null;selectedId.value='';events.value=[];dataset.value=item;observed.value=Math.min(observed.value,item.bars);error.value='';void router.replace({path:route.path,query:{...route.query,run:undefined,structure:undefined,dataset:item.id}})}
async function selectStructure(id:string){selectedId.value=id;const target=analysis.value?.structures.find(s=>s.id===id);if(target){structureFilter.value=target.type;await router.replace({path:route.path,query:{...route.query,structure:id}})}}
watch([selectedId,()=>analysis.value?.runId],async ([id])=>{
  const version=++eventGeneration;events.value=[];eventError.value=''
  if(!id||!analysis.value)return
  try{const result=await chanlunApi.events(analysis.value.runId,id);if(active&&version===eventGeneration)events.value=result}
  catch(e){if(active&&version===eventGeneration)eventError.value=failure(e)}
})
watch([()=>analysis.value?.runId,selectedId],([run,id],[previousRun,previousId])=>{
  if(previousRun)drafts.set(`${previousRun}:${previousId}`,{content:draft.value,outlook:outlook.value,lesson:linkedLesson.value})
  const saved=run?drafts.get(`${run}:${id}`):null
  draft.value=saved?.content??'';outlook.value=saved?.outlook??'WAIT';linkedLesson.value=saved?.lesson??null
})
watch(()=>route.query.run,id=>{if(typeof id==='string'&&id!==analysis.value?.runId)void restore(id);else if(id===undefined){++generation;analysis.value=null;selectedId.value='';events.value=[];busy.value=false}else if(typeof id!=='string'){++generation;analysis.value=null;error.value='历史分析标识无效。'}})
watch(()=>route.query.structure,id=>{if(id===undefined)return;if(typeof id==='string'&&analysis.value?.structures.some(s=>s.id===id)){selectedId.value=id;structureFilter.value=selected.value!.type}else if(analysis.value){selectedId.value='';error.value='指定结构不在此历史分析中，不替换其他结构。'}})
function read(){const references=selected.value?.evidence?.referenceLessons;if(Array.isArray(references)){const reference=references.find(n=>Number.isInteger(n)&&n>=1&&n<=108);if(reference)lesson.value=reference}showReader.value=true;linkedLesson.value=lesson.value}
async function save(){
  if(!analysis.value||!draft.value.trim()||saving.value)return
  const payload={runId:analysis.value.runId,structureId:selected.value?.id??null,outlook:outlook.value,content:draft.value.trim(),lessonNumber:linkedLesson.value}
  if(!saveCommand||JSON.stringify({...saveCommand,clientRequestId:undefined})!==JSON.stringify(payload))saveCommand={...payload,clientRequestId:requestUuid()}
  const command=saveCommand;saving.value=true;journalError.value='';notice.value=''
  try{
    await chanlunApi.judge(command)
    if(!active)return
    if(analysis.value?.runId===command.runId&&(selected.value?.id??null)===command.structureId&&draft.value.trim()===command.content&&outlook.value===command.outlook)draft.value=''
    saveCommand=null;notice.value='判断已保存，数据版本与观察时点已一并留档。'
    judgments.value=await chanlunApi.judgments()
  }catch(e){if(active)journalError.value=failure(e)}finally{if(active)saving.value=false}
}
function changeType(){const target=objects.value[0];if(target)void selectStructure(target.id);else{selectedId.value='';void router.replace({path:route.path,query:{...route.query,structure:undefined}})}}
onMounted(()=>{try{const saved=JSON.parse(localStorage.getItem('aiquant-chanlun-layout')??'null');if(saved?.layout==='evidence')layout.value='evidence';if(saved?.layer)for(const key of allKinds)if(typeof saved.layer[key]==='boolean')layer.value[key]=saved.layer[key]}catch{}void initialize()})
watch([layout,layer],()=>{try{localStorage.setItem('aiquant-chanlun-layout',JSON.stringify({layout:layout.value,layer:layer.value}))}catch{}},{deep:true})
onUnmounted(()=>{active=false;generation++;eventGeneration++})
</script>

<template>
  <div class="chanlun-center">
    <header class="chan-title"><div><p class="eyebrow">CHAN THEORY / 缠论中心</p><h2>从结构，看到依据</h2><p>保留当时所见，用原文理解，用独立判断验证。</p></div><span class="history-badge">冻结历史 · 日线研究</span></header>
    <ChanlunNavigation :active="tab" :context="queryFor()"/>
    <ChanlunSourceBar :analysis="analysis" :dataset="dataset"/>
    <p v-if="!analysis&&!busy" class="evidence-note">浏览页面不会自动创建分析。选择历史数据集和引擎后，点击“开始历史分析”；按存档链接进入时只读取原记录。</p>
    <p v-if="analysis&&!datasetAvailable" class="evidence-note">此存档数据集不在当前目录或版本已变化，仍可读取原证据；新分析需先选择目录中的数据集。</p>
    <div v-if="tab==='workbench'" class="chan-toolbar">
      <label>历史数据集<select aria-label="历史数据集" :value="dataset?`${dataset.id}:${dataset.sha256}`:''" :disabled="busy" @change="chooseDataset"><option v-if="!dataset" value="">选择历史数据集</option><option v-if="dataset&&!datasetAvailable" :value="`${dataset.id}:${dataset.sha256}`">{{dataset.displayName}} · 存档版本（目录未包含）</option><option v-for="item in datasets" :key="`${item.id}:${item.sha256}`" :value="`${item.id}:${item.sha256}`">{{item.displayName}} · {{item.symbol}} · {{item.frequency}}</option></select></label>
      <label>结构引擎<select aria-label="结构引擎" v-model="engine" :disabled="busy"><option value="native">AI-QUANT 自研引擎</option><option value="chanpy">chan.py</option><option value="czsc">CZSC</option><option value="baseline">AI-QUANT 研究基线</option></select></label>
      <label v-if="tab==='workbench'">布局<select v-model="layout"><option value="chart">图表优先</option><option value="evidence">证据优先</option></select></label>
      <button type="button" :disabled="busy||observed<50||!datasetAvailable" @click="load(true)"><RefreshCw :size="15"/>{{analysis?'重新分析':'开始历史分析'}}</button>
    </div>
    <p v-if="error" role="alert" class="chan-error">{{error}} <button type="button" :disabled="busy" @click="initialize">刷新服务状态</button></p>
    <p v-if="busy" role="status" class="chan-empty">正在按当前时点逐根计算结构与修订记录…</p>

    <template v-if="analysis&&tab==='workbench'">
      <p v-if="analysis.derivedFrom" class="evidence-note">当前为观察事件重建的冻结前缀，共{{analysis.observedBars}}根。新分析至少需要50根；可继续核对当前证据和保存判断。</p>
      <div class="chan-workspace" :class="{'evidence-first':layout==='evidence'}">
        <section class="chan-panel chart-panel">
          <header class="panel-title"><div><h3>{{instrumentLabel(analysis.dataset.symbol)}} · {{names[analysis.engineId]}}</h3><p>截至 {{analysis.observedAsOfDate}} · {{analysis.observedBars.toLocaleString()}} 根已观察 {{analysis.dataset.frequency}}</p></div><span class="history-badge">非实时</span></header>
          <div class="layer-controls" aria-label="结构图层"><label v-for="kind in allKinds" :key="kind"><input v-model="layer[kind]" type="checkbox" :disabled="!supports.includes(kind)">{{types[kind]}}<small v-if="!supports.includes(kind)">当前未接入</small></label><span>实线：引擎确定　虚线：动态结构　×：候选已失效</span></div>
          <TongdaxinChart :points="chartPoints" :overlays="overlays" :selected-overlay-id="selectedId" :initial-visible-bars="72" :symbol="analysis.dataset.symbol" :display-name="analysis.dataset.displayName+' · 历史结构'" default-theme="light" :height="410" @select-structure="selectStructure"/>
          <p class="price-note">使用存档价格口径 {{analysis.priceBasis}}，仅供历史结构研究；不作为当前交割合约成交报价。交易日标签不代表当日零点已知。</p>
        </section>
        <aside class="chan-panel evidence-panel" aria-label="结构证据">
          <header class="panel-title"><h3><ScanLine :size="17"/>结构证据</h3><label class="compact-label">对象类型<select v-model="structureFilter" @change="changeType"><option v-for="kind in allKinds" :key="kind" :value="kind" :disabled="!supports.includes(kind)">{{types[kind]}}</option></select></label></header>
          <label class="object-picker">选择结构<select :value="selectedId" @change="selectStructure(($event.target as HTMLSelectElement).value)"><option v-for="item in objects" :key="item.id" :value="item.id">{{types[item.type]}} · {{item.pivotStartDate}} → {{item.pivotEndDate}} · r{{item.revision}}</option></select></label>
          <template v-if="selected">
            <h4>{{types[selected.type]}} · {{selected.direction==='RANGE'?'重叠区间':selected.direction==='UP'?'向上':'向下'}}<span>修订 {{selected.revision}}</span></h4>
            <dl><dt>图上起点</dt><dd>{{selected.pivotStartDate}}</dd><dt>图上端点</dt><dd>{{selected.pivotEndDate}}</dd><dt>首次观察日</dt><dd>{{selected.firstObservedDate}}</dd><dt>当前修订确认日</dt><dd>{{selected.engineConfirmedDate??'未提供 / 未确定'}}</dd><dt>原始状态口径</dt><dd>{{selected.rawFlag}} · {{selected.engineConfirmed===null?'无统一确定字段':selected.engineConfirmed?'当前确定':'动态'}}</dd><dt>允许交易</dt><dd>未评估</dd></dl>
            <p class="evidence-note">图上端点与首次观察日分开记录。“引擎确定”仍可能修订，不直接构成交易资格。</p>
            <p v-if="ruleExplanation" class="evidence-note">{{ruleExplanation}}</p>
            <p v-if="selected.type==='BSP'" class="evidence-note"><strong>{{selected.signalType}} · {{selected.signalState==='INVALIDATED'?'已失效':'研究候选'}}</strong><br>失效价格：{{selected.invalidation}}。候选条件不代表交易建议或收益保证。</p>
            <details v-if="selected.evidence" class="event-trace"><summary>计算规则与构成证据</summary><pre class="native-evidence">{{JSON.stringify(selected.evidence,null,2)}}</pre></details>
            <details open class="event-trace"><summary>该结构的观察与修订</summary><p v-if="eventError" role="alert">{{eventError}}</p><ol><li v-for="event in events.slice(0,8)" :key="event.eventSeq"><time>{{event.observedDate}}</time><span>{{event.eventType==='OBSERVED'?'首次 / 再次观察':event.eventType==='REVISED'?'修订':'撤回'}} · r{{event.revision}}</span></li></ol><small v-if="events.length>8">最近展示8条；本次查询返回{{events.length}}条记录。</small></details>
          </template><p v-else class="chan-empty">当前规则与时点尚无此类结构。</p>
          <button type="button" class="read-original" @click="read"><BookOpen :size="16"/>系统内查阅原文</button>
        </aside>
      </div>
      <section class="chan-panel observation-panel"><div><label for="chan-prefix">观察界限 · 已观察根数</label><output>{{observed}} / {{dataset?.bars}}</output></div><input id="chan-prefix" v-model.number="observed" type="range" min="50" :max="dataset?.bars??1894" step="1" :disabled="busy"><div class="observation-actions"><button type="button" :disabled="busy||observed<=50" @click="observed--;load()">上一根</button><button type="button" :disabled="busy||observed<50||observed>=(dataset?.bars??1894)" @click="observed++;load()">下一根</button><button type="button" :disabled="busy||observed<50" @click="load()">载入此时点</button><span>研究回放 · 可自由选历史区间，非盲训练</span></div></section>
      <section class="chan-panel judgment-editor"><h3>留下当时的判断</h3><p>绑定 {{analysis.observedAsOfDate}}、{{names[analysis.engineId]}} 和当前结构；后续修订不会覆盖这条记录。</p><div class="judgment-form"><label>观察倾向<select v-model="outlook"><option value="WAIT">等待 / 不判断</option><option value="UP">向上观察</option><option value="DOWN">向下观察</option></select></label><label>理由与失效条件<textarea v-model="draft" rows="3" maxlength="6000" placeholder="记录结构依据，以及出现什么情况会改变判断。"/></label></div><button type="button" class="primary" :disabled="saving||!draft.trim()" @click="save"><Save :size="15"/>{{saving?'保存中…':'保存判断'}}</button><span v-if="linkedLesson" class="attached-lesson">参考原文：第{{linkedLesson}}课</span></section>
    </template>

    <section v-if="tab==='academy'||showReader" class="chan-panel original-panel"><header class="panel-title"><div><h3><BookOpen :size="18"/>原典课堂 · 缠中说禅</h3><p>108课原文与原图 · 参考阅读与引擎解释分开。</p></div><button v-if="tab!=='academy'" type="button" @click="showReader=false">收起原文</button></header><label class="lesson-picker">直接选课<select v-model.number="lesson"><option v-for="chapter in chapters.chapters" :key="chapter.number" :value="chapter.number">{{chapter.title}}</option></select></label><ChanlunReader :initial-chapter="lesson" @chapter-change="lesson=$event;linkedLesson=$event"/></section>

    <section v-if="tab==='judgments'" class="journal">
      <header class="panel-title"><div><h3>当时的判断，保留当时的依据</h3><p>按实际保存时间排列；观察日与保存日分别记录。</p></div></header>
      <p v-if="!judgments.length" class="chan-empty">尚未保存判断。可在工作台选中结构后记录理由与失效条件。</p>
      <article v-for="item in judgments" :key="item.id" class="chan-panel saved-judgment">
        <header><strong>{{item.evidence.observedAsOfDate}} · {{names[item.evidence.engineId]}}</strong><span>{{item.outlook==='UP'?'向上观察':item.outlook==='DOWN'?'向下观察':'等待 / 不判断'}}</span></header>
        <p>{{item.content}}</p>
        <footer>
          <time>保存于 {{new Date(item.createdAt).toLocaleString('zh-CN')}}</time>
          <RouterLink :to="{path:'/chanlun/workbench',query:{run:item.runId,structure:item.structureId??undefined,lesson:item.evidence.lessonNumber}}">回到当时图表</RouterLink>
          <RouterLink v-if="item.evidence.comparisonId" :to="{path:'/chanlun/compare',query:{comparison:item.evidence.comparisonId,at:item.evidence.observedIndex}}">回到当时分歧取证</RouterLink>
          <RouterLink v-if="item.evidence.lessonNumber" :to="{path:'/chanlun/academy',query:{run:item.runId,lesson:item.evidence.lessonNumber}}">参考原文第{{item.evidence.lessonNumber}}课</RouterLink>
        </footer>
      </article>
    </section>

    <section v-if="tab==='settings'" class="settings-area"><h3>引擎与数据来源</h3><div class="engine-list"><article v-for="item in engines" :key="item.id" class="chan-panel"><h4>{{item.name}}</h4><span>{{item.status==='AVAILABLE'?'服务可用':'服务暂不可用'}}</span><p>{{item.layers.map(k=>types[k as Structure['type']]).join(' / ')||'暂无已接入图层'}}</p></article></div><section v-if="analysis" class="chan-panel provenance"><h4>当前分析版本</h4><dl><dt>引擎版本</dt><dd>{{analysis.engineVersion}}</dd><dt>规则哈希</dt><dd>{{analysis.profileHash}}</dd><dt>冻结数据哈希</dt><dd>{{analysis.datasetHash}}</dd><dt>固定参数</dt><dd>{{JSON.stringify(analysis.profile.parameters)}}</dd><dt>价格口径</dt><dd>{{analysis.priceBasis}}</dd><dt>实际计算时间</dt><dd>{{analysis.recordedAt}}</dd></dl></section><p class="price-note">当前提供冻结 FU 日线研究、逐根训练、持续监控、多周期观察及成本实验；模拟交易桥接仍待实现。</p></section>
    <p v-if="journalError" role="alert" class="chan-error">{{journalError}}</p><p v-if="notice" role="status" class="chan-notice">{{notice}}</p>
  </div>
</template>

<style scoped>
.native-evidence{font-size:.72rem;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;margin:.6rem 0}
.chanlun-center{--chan-surface:#fffefa;--chan-bg:#f6f4ef;--chan-border:#dedfd5;--chan-muted:#657066;--chan-ink:#293b31;--chan-accent:#365c48;color:var(--chan-ink);min-width:0}.chan-title{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-bottom:1.4rem}.chan-title h2{margin:.25rem 0;font-size:1.65rem;letter-spacing:-.03em}.chan-title p{font-size:.8rem;color:var(--chan-muted);margin:.45rem 0}.eyebrow{letter-spacing:.1em;font-size:.67rem!important}.history-badge{font-size:.72rem;color:var(--chan-accent);padding:.35rem .65rem;border-radius:.35rem;background:#e9eee5;white-space:nowrap}.chan-tabs{display:flex;gap:.5rem;flex-wrap:wrap;border-bottom:1px solid var(--chan-border);padding-bottom:.9rem;margin-bottom:1.2rem}.chan-tabs a{padding:.55rem .8rem;color:var(--chan-muted);text-decoration:none;font-size:.8rem;border-radius:.35rem}.chan-tabs a[aria-current=page]{color:var(--chan-ink);background:#e6ede1;font-weight:600}.chan-toolbar{display:flex;gap:.8rem;align-items:center;flex-wrap:wrap;margin-bottom:1rem}.chanlun-center button{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;padding:.55rem .7rem;border:1px solid var(--chan-border);border-radius:.35rem;background:var(--chan-surface);color:var(--chan-ink);font:inherit;font-size:.76rem;cursor:pointer}.chanlun-center button:disabled{opacity:.45;cursor:default}.chanlun-center button.primary{background:var(--chan-accent);border-color:var(--chan-accent);color:#fff}.chanlun-center select,.chanlun-center textarea{box-sizing:border-box;max-width:100%;min-width:0;border:1px solid var(--chan-border);border-radius:.35rem;background:var(--chan-surface);color:var(--chan-ink);font:inherit;font-size:.78rem;padding:.5rem .6rem}.chan-toolbar label{display:flex;align-items:center;gap:.5rem;color:var(--chan-muted);font-size:.75rem}.instrument{font-size:.87rem;font-weight:600;margin-right:.5rem}.instrument small{font-size:.7rem;font-weight:400;margin-left:.35rem}.chan-panel{border:1px solid var(--chan-border);border-radius:.6rem;padding:1rem;background:var(--chan-surface);min-width:0}.chan-workspace{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:1rem}.chan-workspace.evidence-first{grid-template-columns:minmax(0,1fr)}.evidence-first .evidence-panel{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.evidence-first .evidence-panel>.panel-title,.evidence-first .object-picker{grid-column:1/-1}.evidence-first .event-trace{grid-column:2;grid-row:3/6}.panel-title{display:flex;align-items:center;justify-content:space-between;gap:.8rem;flex-wrap:wrap}.panel-title h3{display:flex;align-items:center;gap:.5rem;font-size:.88rem;margin:0}.panel-title p,.comparison-charts p{font-size:.74rem;color:var(--chan-muted);margin:.4rem 0}.layer-controls{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin:.8rem 0;font-size:.74rem}.layer-controls label{display:flex;align-items:center;gap:.3rem}.layer-controls input{accent-color:var(--chan-accent)}.layer-controls span,.layer-controls small{font-size:.68rem;color:var(--chan-muted)}.price-note,.evidence-note{font-size:.72rem;line-height:1.8;color:var(--chan-muted);margin:.7rem 0 0}.evidence-panel h4{margin:1rem 0;font-size:.95rem;display:flex;justify-content:space-between;align-items:center}.evidence-panel h4 span{font-size:.68rem;font-weight:400;color:var(--chan-muted)}dl{display:grid;grid-template-columns:6rem minmax(0,1fr);gap:.6rem .5rem;margin:0;font-size:.72rem;line-height:1.7}dt{color:var(--chan-muted)}dd{margin:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.compact-label{font-size:.65rem;color:var(--chan-muted);display:flex;align-items:center;gap:.3rem}.compact-label select{font-size:.7rem;padding:.25rem}.object-picker{display:grid;gap:.4rem;margin-top:.7rem;font-size:.7rem;color:var(--chan-muted)}.object-picker select{width:100%}.event-trace{font-size:.72rem;border-top:1px solid var(--chan-border);padding-top:.8rem;margin-top:.8rem}.event-trace summary{cursor:pointer}.event-trace ol{list-style:none;padding:0;margin:.7rem 0}.event-trace li{display:flex;justify-content:space-between;gap:.5rem;padding:.3rem 0;color:var(--chan-muted)}.read-original{margin-top:.8rem;width:100%}.observation-panel,.judgment-editor{margin-top:1rem}.observation-panel>div:first-child{display:flex;align-items:center;justify-content:space-between;font-size:.78rem;gap:.5rem}.observation-panel input{width:100%;margin:.8rem 0;accent-color:var(--chan-accent);min-height:24px}.observation-actions{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}.observation-actions span{color:var(--chan-muted);font-size:.7rem}.judgment-editor h3{font-size:.9rem;margin:0}.judgment-editor p{font-size:.75rem;color:var(--chan-muted)}.judgment-form{display:grid;grid-template-columns:10rem minmax(0,1fr);gap:1rem;margin:.9rem 0}.judgment-form label{display:grid;align-content:start;gap:.4rem;color:var(--chan-muted);font-size:.75rem}.judgment-form textarea{width:100%;resize:vertical}.attached-lesson{font-size:.72rem;color:var(--chan-muted);margin-left:.8rem}.chan-error{padding:.8rem;border-left:3px solid #a54e3d;color:#8c3e32;font-size:.8rem;background:#fbf0e9}.chan-empty{padding:1.6rem;font-size:.85rem;color:var(--chan-muted);line-height:1.9}.chan-notice{padding:.8rem;background:#e8efe3;font-size:.8rem}.comparison-charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,370px),1fr));gap:1rem;margin-top:1rem}.comparison-charts h3{font-size:.9rem}.comparison-charts a,.saved-judgment a{font-size:.75rem;color:var(--chan-accent)}.original-panel{margin-top:1rem}.lesson-picker{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;font-size:.75rem;margin:.9rem 0}.lesson-picker select{max-width:100%}.journal>.panel-title{margin-bottom:1rem}.saved-judgment{margin-bottom:.8rem}.saved-judgment header,.saved-judgment footer{display:flex;justify-content:space-between;gap:.8rem;flex-wrap:wrap;font-size:.75rem}.saved-judgment p{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem;line-height:1.9}.saved-judgment footer{color:var(--chan-muted)}.engine-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.8rem;margin-bottom:1rem}.engine-list h4,.provenance h4{margin:0 0 .8rem;font-size:.9rem}.engine-list span,.engine-list p{font-size:.75rem;color:var(--chan-muted)}.settings-area>h3{font-size:1rem}.chanlun-center :is(button,select,textarea,input,a):focus-visible{outline:2px solid #9e784b;outline-offset:3px}
@media(max-width:1150px){.chan-workspace{grid-template-columns:minmax(0,1fr)}.evidence-panel{max-width:none}.evidence-first .evidence-panel{display:block}}
@media(max-width:600px){.chan-panel{padding:.75rem}.chan-title h2{font-size:1.3rem}.chan-toolbar label{flex-wrap:wrap}.chan-tabs{gap:.1rem}.chan-tabs a{padding:.5rem;font-size:.75rem}.judgment-form{grid-template-columns:minmax(0,1fr)}.chanlun-center select,.chanlun-center textarea{font-size:16px}.chan-title{gap:.5rem}.compact-label{max-width:100%}.observation-actions button{flex:1}.evidence-panel dd{font-size:.73rem}.chanlun-center :deep(.chanlun-reader){padding:.2rem}.chanlun-center :deep(.tdx-toolbar){flex-wrap:wrap}}
@media(pointer:coarse){.chanlun-center button,.chanlun-center select,.chan-tabs a{min-height:44px}.layer-controls label{min-height:44px}}
</style>

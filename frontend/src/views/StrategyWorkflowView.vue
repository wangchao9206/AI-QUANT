<script setup lang="ts">
import {instrumentLabel} from '../utils/instrumentNames'
import {computed,nextTick,onMounted,ref,watch} from 'vue'
import {onBeforeRouteLeave,useRoute,useRouter} from 'vue-router'
import {GitBranch,Plus,Save,Upload,Undo2,Redo2,Play,Check,ArrowUpRight,ArrowRight} from 'lucide-vue-next'
import WorkflowCanvas from '../components/WorkflowCanvas.vue'
import WorkflowRuleForm from '../components/WorkflowRuleForm.vue'
import MaTrendWorkflowPreview from '../components/MaTrendWorkflowPreview.vue'
import MaTrendWorkflowReplay from '../components/MaTrendWorkflowReplay.vue'
import WorkflowReplayFeedback from '../components/WorkflowReplayFeedback.vue'
import type {ReplayReviewContext} from '../services/replayReviews'
import {api,type ReplayStatus} from '../services/api'
import {workflowsApi,type FlowGraph,type NodeType,type WorkflowDraft,type WorkflowSummary,type WorkflowVersion,type WorkflowCheck,type WorkflowDebug,type WorkflowShadow,type WorkflowEvidence} from '../services/workflows'
import {clone,chanTemplate,customTemplate,makeNode,ports,presetNames,specs,template,traceValue} from '../utils/workflowGraph'
import TongdaxinChart from '../components/TongdaxinChart.vue'
import ChanlunReader from '../components/ChanlunReader.vue'
import {formatTradingDate} from '../utils/format'
import type {ChartStructureOverlay} from '../utils/chartStructureOverlays'
import {requestId,requestUuid} from '../utils/requestId'
import {workflowSignalLabel,workflowNodeStatusLabel} from '../utils/workflowGuide'
import {MA_TREND_DESCRIPTION,MA_TREND_DRAFT_KIND,MA_TREND_NAME,maTrendTemplate} from '../utils/maTrendWorkflow'
const route=useRoute(),router=useRouter()
const reviewSource=computed<ReplayReviewContext|null>(()=>{
 const {reviewSession,reviewVersion,reviewRun}=route.query
 if(typeof reviewSession==='string')return {kind:'session',id:reviewSession}
 if(typeof reviewVersion==='string'&&typeof reviewRun==='string')return {kind:'workflow',id:reviewVersion,reviewRunId:reviewRun}
 return null
})
const steps=[
 {id:'choose',label:'选策略'},
 {id:'edit',label:'改规则'},
 {id:'preview',label:'看信号'},
 {id:'publish',label:'发布与模拟'},
] as const
type Stage=typeof steps[number]['id']
const stage=ref<Stage>('choose')
const editingReady=ref(false),showCanvas=ref(false)
const stageTitle=ref<HTMLElement>()
const shadow=ref<WorkflowShadow|null>(null),evidence=ref<WorkflowEvidence|null>(null),recentShadows=ref<WorkflowShadow[]>([]),showLesson=ref(false)
let shadowCommand:{key:string;id:string;asOf:string}|null=null
const graph=ref<FlowGraph>(template()),selected=ref(''),name=ref('我的突破策略'),description=ref('')
const canvas=ref<InstanceType<typeof WorkflowCanvas>>(),draft=ref<WorkflowDraft|null>(null),items=ref<WorkflowSummary[]>([])
const busy=ref(false),error=ref(''),notice=ref(''),listError=ref(''),checked=ref<WorkflowCheck|null>(null),debug=ref<WorkflowDebug|null>(null)
const history=ref<ReplayStatus|null>(null),historyError=ref(''),symbol=ref(''),asOfDate=ref(''),direction=ref(0)
const selectedTemplate=ref('MOMENTUM_BREAKOUT'),versionId=ref(''),published=ref<WorkflowVersion[]>([])
const snapshot=()=>JSON.stringify({name:name.value.trim(),description:description.value.trim(),definition:graph.value})
const baseline=ref(snapshot()),dirty=computed(()=>snapshot()!==baseline.value)
const undo=ref<FlowGraph[]>([]),redo=ref<FlowGraph[]>([])
let createCommand=requestId(),publishCommand:{revision:number;id:string}|null=null
const node=computed(()=>graph.value.nodes.find(n=>n.id===selected.value))
const versions=computed(()=>draft.value?.versions??published.value)
const version=computed(()=>{const id=versionId.value;return versions.value.find(v=>v.id===id)})
const trace=computed(()=>debug.value?.nodeTrace??[])
const today=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Shanghai'})
const isChanVersion=computed(()=>version.value?.engineVersion==='workflow-daily-v2')
const canArchive=computed(()=>isChanVersion.value&&!dirty.value&&!!symbol.value&&!!asOfDate.value)
const testingSymbol=computed(()=>history.value?.symbols.find(row=>row.symbol===symbol.value))
const maTrendDraft=computed(()=>graph.value.draftKind===MA_TREND_DRAFT_KIND)
const maTrendTemplateKey='ma-trend-15m'
const maTrendEngine='workflow-ma-trend-15m-v1'
const maTrendVersions=computed(()=>versions.value.filter(item=>item.engineVersion===maTrendEngine))
const maTrendVersion=computed(()=>maTrendVersions.value.find(item=>item.id===versionId.value))
function setMaTakeProfit(event:Event){
 const input=event.target as HTMLInputElement
 const next=clone(graph.value)
 if(input.validity.valid&&Number.isFinite(input.valueAsNumber))next.maTrendExecution={takeProfitPct:input.valueAsNumber}
 else delete next.maTrendExecution
 graph.value=next
}
function goTo(target:Stage,focus=true){
 stage.value=target
 void nextTick(()=>{
  if(focus)stageTitle.value?.focus()
  if(target==='edit'&&showCanvas.value)canvas.value?.fit()
 })
}
function showEditor(){
 editingReady.value=true
 showCanvas.value=false
 goTo('edit')
}
async function toggleCanvas(){
 showCanvas.value=!showCanvas.value
 if(showCanvas.value){await nextTick();canvas.value?.fit()}
}
async function inspectNode(id:string){
 selected.value=id
 goTo('edit')
 if(!showCanvas.value)await toggleCanvas()
}
function clearObservation(){
 shadow.value=null
 evidence.value=null
 recentShadows.value=[]
 showLesson.value=false
 shadowCommand=null
}
function invalidate(){checked.value=null;debug.value=null;notice.value='';error.value=''}
function change(value:FlowGraph){
 if(busy.value)return
 const next=clone(value)
 next.schemaVersion=next.nodes.some(n=>n.type==='CHAN_SIGNAL')?2:1
 undo.value.push(clone(graph.value))
 if(undo.value.length>50)undo.value.shift()
 redo.value=[]
 graph.value=next
 invalidate()
}
function travel(back:boolean){if(busy.value)return;const from=back?undo:redo,to=back?redo:undo,value=from.value.pop();if(!value)return;to.value.push(clone(graph.value));graph.value=value;selected.value='';invalidate()}
function updateNode(key:string,value:string|number){if(!node.value)return;if(typeof value==='number'&&!Number.isFinite(value)){error.value='请输入有效数字';return}const next=clone(graph.value),target=next.nodes.find(n=>n.id===node.value!.id)!;if(key==='label')target.label=String(value);else target.params[key]=value
 next.edges=next.edges.filter(e=>{const a=next.nodes.find(n=>n.id===e.source),b=next.nodes.find(n=>n.id===e.target);return a&&b&&ports(a).outputs[e.sourcePort]===ports(b).inputs[e.targetPort]&&ports(a).outputs[e.sourcePort]})
 change(next)}
function add(type:NodeType){if(busy.value)return;if(graph.value.nodes.length>=40){error.value='最多40个节点';return}const node=makeNode(type,150+graph.value.nodes.length*30,170+graph.value.nodes.length*20);change({...graph.value,nodes:[...graph.value.nodes,node]});selected.value=node.id}
function dragPalette(e:DragEvent,type:string){e.dataTransfer?.setData('application/x-strategy-node',type)}
function reset(){
 if(busy.value||dirty.value&&!window.confirm('当前草稿尚未保存。是否放弃本地修改并新建？'))return
 draft.value=null
 const maTrend=selectedTemplate.value===maTrendTemplateKey
 graph.value=maTrend?maTrendTemplate():selectedTemplate.value==='CUSTOM'?customTemplate():template(selectedTemplate.value)
 name.value=maTrend?MA_TREND_NAME:selectedTemplate.value==='CUSTOM'?'收盘价高于均线':(presetNames[selectedTemplate.value]??'新策略')+'工作流'
 description.value=maTrend?MA_TREND_DESCRIPTION:''
 selected.value=''
 undo.value=[]
 redo.value=[]
 versionId.value=''
 published.value=[]
 createCommand=requestId()
 publishCommand=null
 baseline.value=snapshot()
 error.value=''
 clearObservation()
 invalidate()
 showEditor()
}
function useMaTrendTemplate(){selectedTemplate.value=maTrendTemplateKey;reset()}
async function refresh(){try{items.value=await workflowsApi.list();listError.value=''}catch(e){listError.value=e instanceof Error?e.message:'草稿列表暂不可用'}}
function accept(value:WorkflowDraft){draft.value=value;graph.value=clone(value.definition);name.value=value.name;description.value=value.description;baseline.value=snapshot()}
async function open(id:string){
 if(!id||busy.value)return
 if(draft.value?.id===id){goTo('edit');return}
 if(dirty.value&&!window.confirm('是否放弃本地未保存修改并打开此草稿？'))return
 busy.value=true
 error.value=''
 try{
  accept(await workflowsApi.draft(id))
  selected.value=''
  versionId.value=draft.value?.versions[0]?.id??''
  undo.value=[]
  redo.value=[]
  createCommand=requestId()
  publishCommand=null
  clearObservation()
  invalidate()
  showEditor()
 }catch(e){fail(e)}finally{busy.value=false}
}
function fail(e:unknown){error.value=e instanceof Error?e.message:'操作失败，请重试'}
async function saveCore(){if(!name.value.trim())throw new Error('请填写策略名称');if(!dirty.value&&draft.value)return draft.value
 const value={name:name.value.trim(),description:description.value.trim(),definition:clone(graph.value)}
 const result=draft.value?await workflowsApi.save(draft.value.id,{...value,expectedRevision:draft.value.revision}):await workflowsApi.create({...value,clientRequestId:createCommand})
 accept(result);return result}
async function save(){busy.value=true;error.value='';try{await saveCore();notice.value='草稿已保存';await refresh()}catch(e){fail(e)}finally{busy.value=false}}
async function validate(){busy.value=true;error.value='';notice.value='';try{checked.value=await workflowsApi.validate(clone(graph.value));notice.value='校验通过，可发布并运行'}catch(e){fail(e)}finally{busy.value=false}}
async function publish(){busy.value=true;error.value='';notice.value='';try{
 checked.value=await workflowsApi.validate(clone(graph.value));const saved=await saveCore()
 if(publishCommand?.revision!==saved.revision)publishCommand={revision:saved.revision,id:requestId()}
 const value=await workflowsApi.publish(saved.id,saved.revision,publishCommand.id)
 if(versionId.value!==value.id)selectVersion()
 if(!draft.value!.versions.some(v=>v.id===value.id))draft.value!.versions.push(value);versionId.value=value.id
 notice.value='已发布 v'+value.version+(value.engineVersion===maTrendEngine?'，可运行历史模拟':value.engineVersion==='workflow-daily-v2'?'，归档观察后可创建历史模拟':'，可用于回测和历史 / 实时模拟');await refresh()
 }catch(e){fail(e)}finally{busy.value=false}}
function selectSymbol(){asOfDate.value=testingSymbol.value?.endDate.slice(0,10)??today}
watch([symbol,asOfDate,direction],()=>{debug.value=null})
async function runDebug(){if(!symbol.value||!asOfDate.value){error.value='请选择有真实数据的品种与观测日期';return}busy.value=true;error.value='';debug.value=null;try{const end=new Date(asOfDate.value+'T23:59:59+08:00').getTime();if(!Number.isFinite(end))throw new Error('日期格式无效');debug.value=await workflowsApi.debug(clone(graph.value),symbol.value,new Date(Math.min(Date.now(),end)).toISOString(),direction.value)}catch(e){fail(e)}finally{busy.value=false}}
const frozen=computed(()=>evidence.value??shadow.value)
const frozenPoints=computed(()=>(frozen.value?.inputSnapshot?.signalBars??[]).map(b=>({...b,contract:b.contract??undefined,price:b.close,changePct:0,changePctKnown:false})))
const frozenOverlays=computed<ChartStructureOverlay[]>(()=>{
 const node=frozen.value?.nodeTrace.find(n=>n.type==='CHAN_SIGNAL')
 const value=node?.value as {candidates?:Record<string,unknown>[];invalidations?:Record<string,unknown>[]} | undefined
 return [...(value?.candidates??[]),...(value?.invalidations??[])].map(row=>({...row,id:row.structureId}) as unknown as ChartStructureOverlay)
})
const frozenTrace=computed(()=>frozen.value?.nodeTrace??[])
async function newChan(group='THIRD',command?:string){
 if(busy.value||dirty.value&&!window.confirm('是否放弃本地未保存修改并创建缠论草稿？'))return
 busy.value=true;error.value=''
 try{
  const profile=await workflowsApi.chanProfile()
  if(route.query.chanlun){
   const fu=history.value?.symbols.find(s=>s.symbol.toUpperCase().replace(/0$/,'M')==='FUM')
   if(fu){symbol.value=fu.symbol;selectSymbol()}
  }
  graph.value=chanTemplate(profile,group)
  name.value='缠论首次观察 · '+(group==='ALL'?'全部候选':'三类候选')
  description.value='历史下一根成交；同方向任一所选候选失效时退出。'
  draft.value=null
  published.value=[]
  versionId.value=''
  createCommand=command??requestUuid()
  publishCommand=null
  selected.value=''
  undo.value=[]
  redo.value=[]
  clearObservation()
  invalidate()
  showEditor()
  await saveCore()
  await refresh()
  notice.value='缠论草稿已保存。发布后可归档观察。'
  if(route.query.chanlun)await router.replace({path:route.path,query:{draft:draft.value!.id}})
 }
 catch(e){fail(e)}finally{busy.value=false}
}
async function archiveShadow(){
 if(busy.value||!canArchive.value||!version.value)return
 const end=new Date(asOfDate.value+'T23:59:59+08:00').getTime()
 if(!Number.isFinite(end)){error.value='请填写有效的观察日期';return}
 const asOf=new Date(Math.min(Date.now(),end)).toISOString()
 const key=JSON.stringify([version.value.id,symbol.value,asOfDate.value,direction.value])
 if(shadowCommand?.key!==key)shadowCommand={key,id:requestUuid(),asOf}
 busy.value=true;error.value=''
 try{
  shadow.value=await workflowsApi.observe(version.value.id,{clientRequestId:shadowCommand.id,symbol:symbol.value,asOf:shadowCommand.asOf,direction:direction.value})
  evidence.value=null
  shadowCommand=null
  notice.value='观察已归档'
  await loadObservations()
 }catch(e){fail(e)}finally{busy.value=false}
}
const observationListError=ref('')
let observationsGeneration=0
async function loadObservations(){
 const ticket=++observationsGeneration
 observationListError.value=''
 if(!version.value||!isChanVersion.value){recentShadows.value=[];return}
 try{
  const rows=await workflowsApi.shadows(version.value.id)
  if(ticket===observationsGeneration)recentShadows.value=rows
 }catch(e){
  if(ticket===observationsGeneration)observationListError.value=e instanceof Error?e.message:'已归档的观察暂不可用'
 }
}
watch(()=>version.value?.id,()=>void loadObservations())
function selectVersion(){
 shadow.value=null
 evidence.value=null
 recentShadows.value=[]
 shadowCommand=null
 showLesson.value=false
}
async function restoreShadow(id:string){
 if(busy.value)return
 busy.value=true;error.value=''
 try{
  const archived=await workflowsApi.shadow(id)
  if(version.value?.id!==archived.workflowVersionId){
   const restored=await workflowsApi.version(archived.workflowVersionId)
   published.value=[restored]
   draft.value=null
   versionId.value=restored.id
   graph.value=clone(archived.workflowDefinition)
   name.value=restored.name
   description.value='冻结发布版本'
   baseline.value=snapshot()
   undo.value=[]
   redo.value=[]
   selected.value=''
   invalidate()
   editingReady.value=true
  }
  shadow.value=archived
  evidence.value=null
  symbol.value=archived.symbol
  asOfDate.value=formatTradingDate(archived.signalTime)
  direction.value=archived.direction
  goTo('publish',false)
 }catch(e){fail(e)}finally{busy.value=false}
}
async function restoreDecision(session:string,asOf:string){
 busy.value=true
 error.value=''
 try{
  evidence.value=await workflowsApi.evidence(session,asOf)
  goTo('publish',false)
 }catch(e){fail(e)}finally{busy.value=false}
}
onBeforeRouteLeave(()=>!dirty.value||window.confirm('本地修改尚未保存，是否离开？'))
watch(reviewSource,source=>{
 if(!source)return
 if(typeof route.query.draft==='string')void open(route.query.draft)
 else if(typeof route.query.preset==='string'&&Object.hasOwn(presetNames,route.query.preset)){
  selectedTemplate.value=route.query.preset
  reset()
 }
})
onMounted(async()=>{
 await Promise.allSettled([
  refresh(),
  api.replayStatus().then(v=>{history.value=v;symbol.value=v.symbols[0]?.symbol??'';selectSymbol()})
   .catch(()=>historyError.value='历史数据暂不可用，无法试算。'),
 ])
 const paperSession=route.query.session??route.query.paperSession
 if(typeof route.query.shadow==='string')await restoreShadow(route.query.shadow)
 else if(typeof paperSession==='string'&&typeof route.query.decision==='string')await restoreDecision(paperSession,route.query.decision)
 else if(typeof route.query.draft==='string')await open(route.query.draft)
 else if(typeof route.query.chanlun==='string')await newChan(route.query.chanlun,typeof route.query.command==='string'?route.query.command:undefined)
 else if(route.query.template===maTrendTemplateKey)useMaTrendTemplate()
 else if(typeof route.query.preset==='string'&&Object.hasOwn(presetNames,route.query.preset)){
  selectedTemplate.value=route.query.preset
  reset()
 }
})
</script>
<template>
  <div class="workflow-page">
    <header class="workflow-heading">
      <div>
        <h2>构建策略工作流</h2>
        <p>从一份模板或草稿开始，调整规则，查看历史信号，再发布用于回测或模拟。</p>
      </div>
      <RouterLink to="/strategy">返回策略中心 <ArrowUpRight :size="15" aria-hidden="true" /></RouterLink>
    </header>

    <nav class="guide-nav" aria-label="工作流步骤">
      <ol>
        <li v-for="(step,index) in steps" :key="step.id">
          <button type="button" :aria-current="stage===step.id?'step':undefined"
            :disabled="busy||(!editingReady&&step.id!=='choose'&&stage!==step.id)" @click="goTo(step.id)">
            <span aria-hidden="true">{{ index+1 }}</span>{{ step.label }}
          </button>
        </li>
      </ol>
    </nav>
    <div v-if="editingReady" class="current-workflow">
      <strong>{{ name || '未命名工作流' }}</strong>
      <span>{{ dirty ? '有未保存修改' : draft ? '已保存 · 修订 '+draft.revision : versions.length ? '已发布的规则副本' : '新草稿' }}</span>
    </div>
    <p v-if="error" role="alert" class="flow-error">{{ error }}</p>
    <p v-if="notice" role="status" class="flow-success">{{ notice }}</p>

    <section v-if="stage==='choose'" class="stage-card" aria-labelledby="workflow-stage-title">
      <header class="stage-heading">
        <h3 id="workflow-stage-title" ref="stageTitle" tabindex="-1">选策略或打开草稿</h3>
      </header>
      <div class="start-options">
        <section class="start-option">
          <h4>从模板开始</h4>
          <label>日线策略模板
            <select v-model="selectedTemplate" aria-label="工作流模板" :disabled="busy">
              <option v-for="(label,key) in presetNames" :key="key" :value="key">{{ label }}</option>
              <option value="CUSTOM">自定义 · 收盘价高于均线</option>
              <option :value="maTrendTemplateKey">{{ MA_TREND_NAME }} · 配置草稿</option>
            </select>
          </label>
          <button class="primary" type="button" :disabled="busy" @click="reset">使用模板 <ArrowRight :size="15" aria-hidden="true" /></button>
        </section>
        <section class="start-option">
          <h4>继续已存草稿</h4>
          <p v-if="listError" role="alert" class="flow-error">{{ listError }} <button type="button" @click="refresh">重试</button></p>
          <p v-else-if="!items.length">保存策略草稿后，可在这里重新打开。</p>
          <ul v-else class="draft-list" aria-label="已存草稿">
            <li v-for="item in items" :key="item.id">
              <button type="button" :disabled="busy" @click="open(item.id)">
                <strong>{{ item.name }}</strong>
                <small>{{ item.publishedVersion ? '已发布 v'+item.publishedVersion : '未发布' }} · 修订 {{ item.revision }}</small>
              </button>
            </li>
          </ul>
          <button v-if="editingReady&&!draft" type="button" :disabled="busy" @click="goTo('edit')">继续当前草稿</button>
        </section>
      </div>
      <div class="start-special">
        <div>
          <button type="button" :disabled="busy" @click="useMaTrendTemplate">打开「{{ MA_TREND_NAME }}」</button>
          <p>查看日线方向、下一个交易日的 15 分钟确认、MACD 和 DKX。</p>
        </div>
        <div>
          <button type="button" :disabled="busy" @click="newChan()">新建缠论草稿</button>
          <p>用已完成日线观察缠论候选。模拟盘使用历史回放。</p>
        </div>
        <div>
          <RouterLink class="workflow-template-entry" to="/strategy/self-developed-trinity">编辑「自研道氏-威科夫-缠论三位一体」模板 <ArrowUpRight :size="14" aria-hidden="true" /></RouterLink>
          <p>配置日线与分钟信号，启动独立回测或模拟盘。</p>
        </div>
      </div>
    </section>

    <section v-else-if="stage==='edit'" class="stage-card" aria-labelledby="workflow-stage-title">
      <header class="stage-heading edit-heading">
        <div>
          <h3 id="workflow-stage-title" ref="stageTitle" tabindex="-1">改交易规则</h3>
          <p>{{ maTrendDraft ? '可以核对规则、保存草稿，或查看历史信号。' : '填写策略名称，调整信号条件与仓位保护。' }}</p>
        </div>
        <button type="button" :disabled="busy" :aria-expanded="showCanvas" :aria-controls="showCanvas?'workflow-canvas-panel':undefined" @click="toggleCanvas">
          <GitBranch :size="15" aria-hidden="true" />{{ showCanvas ? '返回规则表单' : maTrendDraft ? '查看日线条件图' : '打开高级画布' }}
        </button>
      </header>
      <WorkflowReplayFeedback v-if="reviewSource" :context="reviewSource" />
      <fieldset class="workflow-info" :disabled="busy">
        <label>名称<input v-model="name" maxlength="120" aria-label="工作流名称" /></label>
        <label>说明（选填）<textarea v-model="description" maxlength="1000" rows="1" aria-label="工作流说明" /></label>
      </fieldset>
      <dl v-if="maTrendDraft&&!showCanvas" class="ma-trend-rules">
        <div><dt>日线方向和强弱</dt><dd>收盘价在 MA20 上方看多、下方看空。同方向越过 MA5 视为强势。</dd></div>
        <div><dt>日线买卖候选</dt><dd>MA5 上穿 MA20，候选买多或平空；下穿，候选买空或平多。多头中前 3 个交易日两线间距依次缩小且 MA5 保持在 MA20 上方，再上穿 MA10，候选买多或加多。</dd></div>
        <div><dt>下一个交易日择时</dt><dd>15 分钟收盘价在该周期 MA20 上方确认偏多，下方确认偏空。MACD(12,26,9) 金叉／死叉与 DKX(20)／MADKX(10) 单独显示。</dd></div>
        <div><dt>半仓和止盈</dt><dd>首次按半仓开仓，加仓用当时可用资金的一半。触发止盈后平掉当时持仓的一半。止盈触发条件和奇数手数的处理待配置。</dd></div>
      </dl>
      <WorkflowRuleForm v-else-if="!showCanvas" :graph="graph" :disabled="busy" @update:graph="change" />
      <div v-else id="workflow-canvas-panel" class="workflow-layout" :class="{'ma-trend-canvas':maTrendDraft}">
        <aside v-if="!maTrendDraft" class="node-library" aria-label="节点库">
          <h4>节点库 <small>{{ graph.nodes.length }} / 40</small></h4>
          <p>点击添加，或拖入画布。</p>
          <button v-for="(spec,type) in specs" v-show="type!=='CHAN_SIGNAL'" :key="type" type="button"
            :draggable="!busy" :disabled="busy" :title="spec.hint" @dragstart="dragPalette($event,type)" @click="add(type)">
            <i :style="{background:spec.color}" aria-hidden="true" /><span>{{ spec.name }}</span><Plus :size="13" aria-hidden="true" />
          </button>
        </aside>
        <div class="canvas-column">
          <WorkflowCanvas ref="canvas" :model-value="graph" v-model:selected="selected" :trace="trace" :disabled="busy||maTrendDraft"
            @update:model-value="change" @error="error=$event" />
          <p>{{ maTrendDraft ? '按住 Ctrl 滚动可缩放日线条件图。' : '点击连线后可按 Delete 删除，按住 Ctrl 滚动可缩放。' }}</p>
        </div>
        <aside v-if="!maTrendDraft" class="workflow-inspector">
          <fieldset v-if="node" :disabled="busy">
            <legend>{{ specs[node.type].name }}</legend>
            <p>{{ specs[node.type].hint }}</p>
            <label>节点名称<input :value="node.label" maxlength="80" @change="updateNode('label',($event.target as HTMLInputElement).value)" /></label>
            <label v-for="param in specs[node.type].params" :key="param.key">{{ param.label }}
              <select v-if="param.options" :value="node.params[param.key]" @change="updateNode(param.key,($event.target as HTMLSelectElement).value)">
                <option v-for="(label,key) in param.options" :key="key" :value="key">{{ label }}</option>
              </select>
              <input v-else type="number" :value="node.params[param.key]" :min="param.min" :max="param.max" :step="param.step"
                @change="updateNode(param.key,($event.target as HTMLInputElement).valueAsNumber)" />
            </label>
            <button class="danger" type="button" @click="canvas?.remove()">删除节点与相关连线</button>
          </fieldset>
          <p v-else>选择画布上的节点来修改参数。</p>
        </aside>
      </div>
      <footer class="stage-actions">
        <div class="action-group">
          <button type="button" :disabled="busy||!undo.length" aria-label="撤销" @click="travel(true)"><Undo2 :size="15" aria-hidden="true" />撤销</button>
          <button type="button" :disabled="busy||!redo.length" aria-label="重做" @click="travel(false)"><Redo2 :size="15" aria-hidden="true" />重做</button>
        </div>
        <div class="action-group">
          <button type="button" :disabled="busy" @click="save"><Save :size="15" aria-hidden="true" />保存草稿</button>
          <button class="primary" type="button" :disabled="busy" @click="goTo('preview')">去看信号 <ArrowRight :size="15" aria-hidden="true" /></button>
        </div>
      </footer>
    </section>

    <section v-else-if="stage==='preview'" class="stage-card" aria-labelledby="workflow-stage-title">
      <header class="stage-heading">
        <h3 id="workflow-stage-title" ref="stageTitle" tabindex="-1">查看历史信号</h3>
        <p>{{ maTrendDraft ? '检查日线触发之后，下一个交易日内哪些 15 分钟收盘达到确认条件。' : '选择品种、日期和假设持仓，用当时已完成的日线试算一次信号。' }}</p>
      </header>
      <MaTrendWorkflowPreview v-if="maTrendDraft" />
      <template v-else>
      <form class="debug-controls" @submit.prevent="runDebug">
        <label>品种
          <select v-model="symbol" :disabled="busy" @change="selectSymbol">
            <option v-for="row in history?.symbols??[]" :key="row.symbol" :value="row.symbol">{{ instrumentLabel(row.symbol) }}</option>
          </select>
        </label>
        <label>观测日期<input v-model="asOfDate" type="date" :min="testingSymbol?.startDate.slice(0,10)"
          :max="testingSymbol?.endDate.slice(0,10)||today" :disabled="busy" required /></label>
        <label>假设持仓
          <select v-model.number="direction" :disabled="busy"><option :value="0">空仓</option><option :value="1">持有多头</option><option :value="-1">持有空头</option></select>
        </label>
        <button class="primary" type="submit" :disabled="busy||!symbol"><Play :size="15" aria-hidden="true" />试算信号</button>
      </form>
      <p v-if="testingSymbol" class="data-coverage">可用日期 {{ testingSymbol.startDate.slice(0,10) }} 至 {{ testingSymbol.endDate.slice(0,10) }}</p>
      <p v-if="historyError" class="flow-error" role="alert">{{ historyError }}</p>
      <div v-if="debug" class="debug-result" aria-label="信号结果">
        <strong>{{ workflowSignalLabel(debug.signal) }}</strong>
        <p>{{ debug.reason }}</p>
        <p>已读取 {{ debug.historyCount }} 根日线，需 {{ debug.requiredBars }} 根<template v-if="debug.signalTime"> · 信号日期 {{ formatTradingDate(debug.signalTime) }}</template></p>
        <p v-if="debug.message">{{ debug.message }}</p>
        <details v-if="trace.length">
          <summary>查看计算依据</summary>
          <div class="trace-table">
            <table>
              <thead><tr><th scope="col">规则</th><th scope="col">结果</th><th scope="col">计算值</th><th scope="col">原因</th><th scope="col">画布</th></tr></thead>
              <tbody>
                <tr v-for="row in trace" :key="row.nodeId">
                  <td>{{ row.label }}</td><td>{{ workflowNodeStatusLabel(row.status) }}</td><td>{{ traceValue(row.value) }}</td><td>{{ row.reason }}</td>
                  <td><button type="button" :aria-label="'在画布定位 '+row.label" :disabled="busy" @click="inspectNode(row.nodeId)">定位</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </div>
      </template>
      <footer class="stage-actions">
        <button type="button" :disabled="busy" @click="goTo('edit')">返回改规则</button>
        <button v-if="maTrendDraft" type="button" :disabled="busy" @click="save"><Save :size="15" aria-hidden="true" />保存草稿</button>
        <button class="primary" type="button" :disabled="busy" @click="goTo('publish')">前往发布 <ArrowRight :size="15" aria-hidden="true" /></button>
      </footer>
    </section>

    <section v-else class="stage-card" aria-labelledby="workflow-stage-title">
      <header class="stage-heading">
        <h3 id="workflow-stage-title" ref="stageTitle" tabindex="-1">{{ editingReady ? '发布与模拟' : '查看模拟决策' }}</h3>
        <p v-if="editingReady&&!maTrendDraft">发布会固定当前规则、手数和保护参数，回测或模拟可选择任一发布版本。</p>
      </header>
      <WorkflowReplayFeedback v-if="reviewSource&&maTrendDraft" :context="reviewSource" />
      <div v-if="maTrendDraft" class="observation" aria-label="策略发布状态">
        <form @submit.prevent="publish">
          <h4>设置止盈目标并发布</h4>
          <label class="ma-profit-input">盈利目标（相对持仓均价，%）
            <input :value="graph.maTrendExecution?.takeProfitPct" type="number" min="0.01" max="50" step="0.01" required :disabled="busy" @change="setMaTakeProfit" />
          </label>
          <p>达到目标时平掉当时持仓的一半。手数向下取整，只有 1 手时不减仓。MACD 和 DKX 作参考。</p>
          <p>发布后可用已核验行情运行历史模拟。</p>
          <div class="action-group publish-actions">
            <button type="button" :disabled="busy" @click="goTo('preview')">返回看信号</button>
            <button type="button" :disabled="busy" @click="save"><Save :size="15" aria-hidden="true" />保存草稿</button>
            <button class="primary" type="submit" :disabled="busy"><Upload :size="15" aria-hidden="true" />发布历史模拟版本</button>
          </div>
        </form>
        <label v-if="maTrendVersions.length" class="ma-profit-input">选择运行版本
          <select v-model="versionId" aria-label="历史模拟版本" :disabled="busy">
            <option value="">选择已发布版本</option>
            <option v-for="v in maTrendVersions" :key="v.id" :value="v.id">v{{ v.version }} · 止盈 {{ v.definition.maTrendExecution?.takeProfitPct }}%</option>
          </select>
        </label>
        <MaTrendWorkflowReplay v-if="maTrendVersion" :version="maTrendVersion" :versions="maTrendVersions" :disabled="busy" />
      </div>
      <template v-else-if="editingReady">
        <div class="action-group publish-actions">
          <button type="button" :disabled="busy" @click="validate"><Check :size="15" aria-hidden="true" />校验规则</button>
          <button class="primary" type="button" :disabled="busy" @click="publish"><Upload :size="15" aria-hidden="true" />发布版本</button>
        </div>
        <p v-if="checked" class="check-info">已校验 {{ checked.nodeCount }} 个规则，预热需 {{ checked.requiredBars }} 根日线。固定 {{ checked.risk.lots }} 手，止损 {{ checked.risk.stopLossAtr }} 倍 ATR，止盈 {{ checked.risk.takeProfitAtr }} 倍 ATR。</p>
        <div v-if="versions.length" class="version-actions">
          <label>选择运行版本
            <select v-model="versionId" aria-label="发布版本" :disabled="busy" @change="selectVersion">
              <option value="">选择已发布版本</option>
              <option v-for="v in versions" :key="v.id" :value="v.id">{{ v.name }} · v{{ v.version }} · {{ v.lots }} 手</option>
            </select>
          </label>
          <template v-if="version">
            <RouterLink class="action-link" :to="{path:'/backtest',query:{workflowVersion:version.id,symbol:symbol||undefined}}">历史回测 <ArrowUpRight :size="14" aria-hidden="true" /></RouterLink>
            <RouterLink v-if="!isChanVersion" class="action-link" :to="{path:'/paper',query:{workflowVersion:version.id,symbol:symbol||undefined}}">配置模拟账户 <ArrowUpRight :size="14" aria-hidden="true" /></RouterLink>
          </template>
        </div>
        <p v-else>发布后可在这里选择版本，开始回测或模拟。</p>
      </template>

      <section v-if="isChanVersion||frozen" class="observation" aria-label="缠论冻结观察">
        <template v-if="isChanVersion">
          <h4>缠论历史模拟</h4>
          <p>先用选定发布版本归档一次空仓观察。观察须有至少 50 根日线，才能创建历史模拟账户。</p>
          <form class="debug-controls" @submit.prevent="archiveShadow">
            <label>观察品种
              <select v-model="symbol" :disabled="busy" @change="selectSymbol">
                <option v-for="row in history?.symbols??[]" :key="row.symbol" :value="row.symbol">{{ instrumentLabel(row.symbol) }}</option>
              </select>
            </label>
            <label>观察日期<input v-model="asOfDate" type="date" :min="testingSymbol?.startDate.slice(0,10)"
              :max="testingSymbol?.endDate.slice(0,10)||today" :disabled="busy" required /></label>
            <label>观察持仓
              <select v-model.number="direction" :disabled="busy"><option :value="0">空仓</option><option :value="1">持有多头</option><option :value="-1">持有空头</option></select>
            </label>
            <button type="submit" :disabled="busy||!canArchive">归档当前日期的观察</button>
          </form>
          <p v-if="historyError" role="alert">{{ historyError }}</p>
          <p v-if="dirty">请先保存草稿，或发布新版本后再归档。</p>
          <p v-if="direction!==0">这次选择了持仓观察，创建模拟账户时请选择空仓观察。</p>
          <p v-if="observationListError" role="alert">{{ observationListError }} <button type="button" @click="loadObservations">重试</button></p>
          <details v-if="recentShadows.length" class="archive-list">
            <summary>已归档的观察</summary>
            <div class="action-group">
              <button v-for="item in recentShadows" :key="item.id" type="button" :disabled="busy" @click="restoreShadow(item.id)">
                {{ formatTradingDate(item.signalTime) }} · {{ instrumentLabel(item.symbol) }} · {{ workflowSignalLabel(item.signal) }}
              </button>
            </div>
          </details>
        </template>
        <div v-if="shadow" class="debug-result">
          <strong>已归档 {{ instrumentLabel(shadow.symbol) }} · {{ formatTradingDate(shadow.signalTime) }}</strong>
          <p>{{ workflowSignalLabel(shadow.signal) }} · {{ shadow.reason }}</p>
          <RouterLink v-if="shadow.direction===0&&shadow.historyCount>=50" class="action-link"
            :to="{path:'/paper',query:{workflowVersion:shadow.workflowVersionId,shadow:shadow.id,symbol:shadow.symbol,startDate:formatTradingDate(shadow.signalTime)}}">创建历史模拟账户 <ArrowUpRight :size="14" aria-hidden="true" /></RouterLink>
          <p v-else>创建历史模拟账户需要空仓且不少于 50 根日线的观察。</p>
        </div>
        <div v-if="frozen" class="frozen-evidence">
          <p>{{ frozen.observationKind==='FROZEN_PAPER_DECISION'?'模拟账户当时决策':'历史观察依据' }} · {{ formatTradingDate(frozen.signalTime) }} · {{ frozen.reason }}</p>
          <TongdaxinChart v-if="frozenPoints.length" :key="shadow?.id??frozen.signalTime??''" :points="frozenPoints" :overlays="frozenOverlays" :symbol="frozen.symbol" :height="360" />
          <details>
            <summary>查看历史计算依据</summary>
            <div v-for="row in frozenTrace" :key="row.nodeId">
              <strong>{{ row.label }} · {{ workflowNodeStatusLabel(row.status) }}</strong>
              <p>{{ row.reason }}</p><pre>{{ traceValue(row.value) }}</pre>
            </div>
          </details>
          <button type="button" @click="showLesson=!showLesson">{{ showLesson ? '收起原文' : '查看原文第 20 课' }}</button>
          <ChanlunReader v-if="showLesson" :initial-chapter="20" />
        </div>
      </section>
    </section>
  </div>
</template>

<style scoped>
.workflow-page { min-width: 0; }
.workflow-heading, .stage-heading, .stage-actions { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.workflow-heading { margin: .65rem 0 1.3rem; }
.workflow-heading h2 { margin: 0; font: 500 clamp(1.4rem, 2.6vw, 2.15rem) / 1.4 var(--font-display); }
p { margin: .42rem 0; color: var(--color-ink-secondary); font-size: .77rem; line-height: 1.75; }
a { color: var(--color-accent); font-size: .76rem; }
.workflow-heading a, .workflow-template-entry, .action-link { display: inline-flex; align-items: center; gap: .35rem; text-decoration: none; }
.workflow-heading a { flex: 0 0 auto; margin-top: .38rem; }
a:hover { text-decoration: underline; }
button:focus-visible, a:focus-visible, summary:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 3px; }
button, select, input, textarea { font: inherit; }
button { display: inline-flex; align-items: center; justify-content: center; gap: .38rem; padding: .62rem .82rem; border-radius: .45rem; border: 1px solid var(--color-line); background: var(--color-surface-raised); color: var(--color-ink); font-size: .76rem; cursor: pointer; }
button:disabled { opacity: .55; cursor: default; }
button.primary { color: white; border-color: var(--color-accent); background: var(--color-accent); }
select, input, textarea { width: 100%; box-sizing: border-box; min-width: 0; padding: .63rem; border: 1px solid var(--color-line); border-radius: .42rem; background: var(--color-surface); color: var(--color-ink); font-size: .77rem; }
select:disabled, input:disabled, textarea:disabled { opacity: .65; }
label { display: grid; gap: .35rem; min-width: 0; color: var(--color-ink-secondary); font-size: .75rem; }
fieldset { min-width: 0; padding: 0; margin: 0; border: 0; }
.guide-nav ol { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); padding: 0; margin: 0; gap: .42rem; list-style: none; }
.guide-nav button { width: 100%; min-height: 3rem; justify-content: flex-start; gap: .55rem; text-align: left; white-space: normal; }
.guide-nav button[aria-current=step] { border-color: var(--color-accent); color: var(--color-accent); background: var(--color-accent-soft); font-weight: 700; }
.guide-nav button > span { display: grid; place-items: center; flex: 0 0 auto; width: 1.42rem; height: 1.42rem; border-radius: 50%; border: 1px solid currentColor; font: .68rem var(--font-numeric); }
.current-workflow { display: flex; align-items: center; flex-wrap: wrap; gap: .45rem 1rem; padding: .9rem 0 0; font-size: .77rem; }
.current-workflow strong { overflow-wrap: anywhere; }
.current-workflow span, .data-coverage { color: var(--color-ink-secondary); font-size: .7rem; }
.stage-card { margin: .95rem 0 1.3rem; padding: clamp(1rem,2vw,1.6rem); border: 1px solid var(--color-line); border-radius: .75rem; background: var(--color-surface-raised); }
.stage-heading { margin-bottom: 1rem; display: block; }
.stage-heading h3 { margin: 0; font-size: 1.08rem; }
.stage-heading h3:focus { outline: none; }
.edit-heading { display: flex; flex-wrap: wrap; }
.start-options { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 1rem; }
.start-option { padding: 1rem; min-width: 0; border: 1px solid var(--color-line); border-radius: .58rem; background: var(--color-surface); }
h4 { margin: 0 0 .65rem; font-size: .83rem; }
.start-option > .primary, .start-option > button { margin-top: .7rem; }
.start-special { display: grid; grid-template-columns: repeat(auto-fit,minmax(min(100%,14rem),1fr)); gap: 1rem; align-items: start; border-top: 1px solid var(--color-line); margin-top: 1rem; padding-top: 1rem; }
.workflow-layout.ma-trend-canvas { grid-template-columns: minmax(0,1fr); }
.ma-trend-rules { display: grid; margin: 1rem 0; border-top: 1px solid var(--color-line); }
.ma-trend-rules > div { display: grid; grid-template-columns: minmax(8rem,12rem) 1fr; gap: 1rem; padding: .85rem 0; border-bottom: 1px solid var(--color-line); font-size: .82rem; line-height: 1.65; }
.ma-trend-rules dt { font-weight: 650; }
.ma-trend-rules dd { margin: 0; color: var(--color-ink-secondary); }
.ma-profit-input { display: grid; gap: .4rem; max-width: 16rem; margin: .6rem 0; }
@media (max-width: 560px) { .ma-trend-rules > div { grid-template-columns: minmax(0,1fr); gap: .3rem; } }
.start-special a { min-height: 2rem; line-height: 1.65; }
.start-special a svg { flex-shrink: 0; }
.draft-list { max-height: 14rem; overflow: auto; display: grid; gap: .38rem; list-style: none; padding: 0; margin: 0; }
.draft-list button { width: 100%; display: grid; justify-content: stretch; text-align: left; overflow-wrap: anywhere; }
.draft-list small { color: var(--color-ink-secondary); }
.workflow-info { display: grid; grid-template-columns: 1fr 2fr; gap: .8rem 1rem; margin: 0 0 1rem; }
.workflow-info textarea { resize: vertical; }
.stage-actions { align-items: center; flex-wrap: wrap; margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid var(--color-line); }
.action-group { display: flex; align-items: center; flex-wrap: wrap; gap: .5rem; }
.workflow-layout { display: grid; grid-template-columns: 9.5rem minmax(0,1fr) 12rem; align-items: start; gap: .7rem; }
.node-library, .workflow-inspector { min-width: 0; padding: .72rem; border: 1px solid var(--color-line); border-radius: .55rem; background: var(--color-surface); }
.node-library h4 { display: flex; align-items: center; justify-content: space-between; gap: .3rem; }
.node-library h4 small { font: .68rem var(--font-numeric); }
.node-library > button { width: 100%; justify-content: flex-start; text-align: left; border-width: 0 0 1px; border-radius: 0; background: none; padding: .56rem .1rem; font-size: .72rem; }
.node-library button > span { flex: 1; }
.node-library button > i { width: .42rem; height: .42rem; border-radius: 50%; flex: 0 0 auto; }
.canvas-column { min-width: 0; }
.canvas-column > p { font-size: .68rem; }
.workflow-inspector legend { font-size: .78rem; font-weight: 650; }
.workflow-inspector label { margin: .55rem 0; font-size: .72rem; }
.workflow-inspector .danger { color: var(--color-warning); margin-top: .65rem; }
.flow-error, .flow-success { padding: .7rem .85rem; border-radius: .45rem; margin: .75rem 0; }
.flow-error { color: var(--color-warning); background: var(--color-warning-soft); }
.flow-success, .check-info { color: var(--color-accent); background: var(--color-accent-soft); }
.check-info { padding: .58rem .7rem; border-radius: .45rem; }
.debug-controls, .version-actions { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .65rem; }
.debug-controls label, .version-actions label { min-width: min(9rem,100%); }
.version-actions { margin: 1rem 0; }
.version-actions label { max-width: 100%; }
.debug-result, .observation { margin-top: 1rem; padding: .9rem; border: 1px solid var(--color-line); border-radius: .54rem; }
.debug-result strong { font-size: .88rem; }
.trace-table { overflow: auto; margin-top: .55rem; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: .72rem; }
th, td { padding: .58rem; border-bottom: 1px solid var(--color-line); vertical-align: top; }
th { color: var(--color-ink-secondary); white-space: nowrap; }
td:nth-child(3), pre { max-width: 26rem; overflow-wrap: anywhere; }
td button { padding: .36rem .5rem; }
summary { color: var(--color-accent); font-size: .75rem; cursor: pointer; padding: .35rem 0; }
.archive-list .action-group { padding: .5rem 0; }
.frozen-evidence { margin-top: .8rem; }
.frozen-evidence strong, pre { font-size: .7rem; }
pre { white-space: pre-wrap; }
.publish-actions, .observation .debug-controls { margin: .85rem 0; }
@media (max-width: 1360px) {
  .workflow-layout { grid-template-columns: 9rem minmax(0,1fr); }
  .workflow-inspector { grid-column: 1 / -1; }
}
@media (max-width: 680px) {
  .workflow-heading { flex-direction: column; gap: .25rem; }
  .guide-nav ol { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .start-options, .start-special, .workflow-info, .workflow-layout { grid-template-columns: minmax(0,1fr); }
  .node-library { display: flex; align-items: center; gap: .5rem; overflow: auto; }
  .node-library h4, .node-library p { display: none; }
  .node-library > button { flex: 0 0 auto; width: auto; border: 1px solid var(--color-line); border-radius: .4rem; padding: .45rem; }
}
</style>

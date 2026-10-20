<script setup lang="ts">
import {computed,onMounted,onUnmounted,reactive,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {BookOpen,Download,NotebookPen,Play,RefreshCw,ShieldCheck,Square,Target} from 'lucide-vue-next'
import {api,type BacktestPresets,type HistoryPoint,type PaperChart,type RecordPage} from '../services/api'
import {personalApi,type PersonalCreate,type PersonalEvent,type PersonalReflection,type PersonalRun,type PersonalRunSummary,type PersonalRules,type PersonalVersion,type PersonalStep} from '../services/personal'
import {originalSummary,strategySteps,interpretations,stateNames} from '../content/personalStrategy'
import {formatNumber,formatTradingDate} from '../utils/format'
import TongdaxinChart from '../components/TongdaxinChart.vue'
import Pagination from '../components/Pagination.vue'
import {usePagination} from '../composables/usePagination'

const route=useRoute(),router=useRouter()
const tab=ref<'original'|'strategy'|'training'|'review'>(route.query.run?'training':'strategy')
const versions=ref<PersonalVersion[]>([]),presets=ref<BacktestPresets|null>(null)
const {items:pagedVersions,page:versionPage,total:versionTotal}=usePagination(versions,6)
const archives=ref<Awaited<ReturnType<typeof api.replayStatus>>|null>(null)
const runs=ref<RecordPage<PersonalRunSummary>|null>(null),runPage=ref(1)
const current=ref<PersonalRun|null>(null),chart=ref<PaperChart|null>(null)
const events=ref<RecordPage<PersonalEvent>|null>(null),eventPage=ref(1)
const reflections=ref<RecordPage<PersonalReflection>|null>(null),reflectionPage=ref(1)
const loading=ref(true),working=ref(false),exporting=ref(false),batch=ref(false),error=ref(''),notice=ref(''),chartError=ref('')
const retryPending=ref(false)
const search=ref(''),selectedEvent=ref(''),runScope=ref(true)
const review=reactive({category:'EXECUTION',content:''})
const decision=reactive({action:'FOLLOW' as PersonalStep['action'],emotion:0,riskAccepted:false,stopAccepted:false,noRevenge:false,notes:''})
const create=reactive<PersonalCreate>({versionId:'',name:'耐心与执行 01',symbol:'M0',startDate:'',endDate:'',initialCash:100000,trainingMode:'GUIDED'})
const defaults:PersonalRules={riskPct:.5,maxMarginPct:20,volumeRatio:1.5,maxStopAtr:2,cooldownBars:3}
const versionDraft=reactive({parentId:'',title:'趋势回踩 · 改进候选',hypothesis:'',validationPlan:'',rules:{...defaults}})
let alive=true,generation=0,stepCommand:{id:string;body:PersonalStep}|null=null
const pageTabs=[{id:'original',title:'你的原文'},{id:'strategy',title:'策略说明'},{id:'training',title:'模拟训练'},{id:'review',title:'复盘与迭代'}] as const
const chosenVersion=computed(()=>versions.value.find(v=>v.id===create.versionId))
const runVersion=computed(()=>versions.value.find(v=>v.id===current.value?.versionId))
const products=computed(()=>presets.value?.symbols.filter(p=>archives.value?.symbols.some(a=>a.symbol===p.symbol))??[])
const filteredProducts=computed(()=>products.value.filter(p=>!search.value||[p.symbol,p.name,p.exchange,p.sector].some(v=>v?.toLowerCase().includes(search.value.trim().toLowerCase()))))
const selectedArchive=computed(()=>archives.value?.symbols.find(a=>a.symbol===create.symbol))
const points=computed<HistoryPoint[]>(()=>chart.value?.bars.map((b,i,bars)=>({...b,price:b.close,changePct:i?(b.close/bars[i-1].close-1)*100:0}))??[])
const canStep=computed(()=>current.value?.session.status==='ACTIVE'&&!working.value)
const money=(n?:number|null)=>n==null?'—':`¥${formatNumber(n,2)}`
const amount=(n?:number|null)=>n==null?'—':formatNumber(n,2)
const categoryNames:Record<string,string>={PRINCIPLE:'理念',EXECUTION:'执行',EMOTION:'情绪',TECHNICAL:'技术',IMPROVEMENT:'改进假设'}
const actionNames:Record<string,string>={FOLLOW:'按规则执行',WAIT:'选择观察',EXIT:'主动离场'}
function failure(e:unknown){error.value=e instanceof Error?e.message:'操作未完成，请重试'}
function setRange(){
  const a=selectedArchive.value;if(!a)return
  const first=new Date(a.startDate+'T00:00:00Z'),last=new Date(a.endDate+'T00:00:00Z')
  const start=new Date(Math.max(first.getTime()+180*86400000,last.getTime()-365*86400000))
  create.startDate=start.toISOString().slice(0,10);create.endDate=a.endDate
}
watch(()=>create.symbol,setRange)
async function loadRuns(){runs.value=await personalApi.runs(runPage.value)}
async function loadEvents(){
  if(!current.value){events.value=null;return}
  const id=current.value.session.id,p=eventPage.value
  const result=await personalApi.events(id,p)
  if(alive&&id===current.value?.session.id&&p===eventPage.value)events.value=result
}
async function loadReflections(){
  const id=runScope.value?current.value?.session.id:undefined,p=reflectionPage.value
  const result=await personalApi.reflections(id,p)
  if(alive&&p===reflectionPage.value&&id===(runScope.value?current.value?.session.id:undefined))reflections.value=result
}
async function refreshRunViews(){
  const id=current.value?.session.id,g=++generation;if(!id)return
  chart.value=null;chartError.value=''
  const results=await Promise.allSettled([api.paperChart(id,240),loadEvents(),loadReflections(),loadRuns()])
  if(!alive||g!==generation)return
  if(results[0].status==='fulfilled')chart.value=results[0].value
  else chartError.value='K线读取失败，可刷新重试；不会用生成行情补齐。'
  if(results.slice(1).some(r=>r.status==='rejected'))error.value='账户已读取，部分记录加载失败，请刷新重试。'
}
async function selectRun(id:string){
  if(working.value||batch.value)return
  working.value=true;error.value='';selectedEvent.value='';stepCommand=null;retryPending.value=false
  try{current.value=await personalApi.run(id);eventPage.value=1;reflectionPage.value=1;tab.value='training';await router.replace({path:'/personal',query:{run:id}});await refreshRunViews()}
  catch(e){failure(e)}finally{working.value=false}
}
async function createTraining(){
  if(!chosenVersion.value||!selectedArchive.value){error.value='请选择有真实回放数据的品种和策略版本';return}
  working.value=true;error.value='';notice.value=''
  try{
    current.value=await personalApi.create({...create});eventPage.value=1;reflectionPage.value=1;selectedEvent.value='';stepCommand=null;retryPending.value=false
    await router.replace({path:'/personal',query:{run:current.value.session.id}})
    await refreshRunViews();notice.value='已创建独立训练账户，版本与历史路径已冻结。预热期没有交易。'
  }catch(e){failure(e)}finally{working.value=false}
}
async function stepOnce(){
  const run=current.value;if(!run||working.value)return
  working.value=true;error.value='';notice.value=''
  const id=run.session.id
  const body:PersonalStep={commandId:crypto.randomUUID(),expectedBarIndex:run.session.currentBarIndex,
    action:run.trainingMode==='RULE_REPLAY'?'FOLLOW':decision.action,emotion:decision.emotion,
    riskAccepted:decision.riskAccepted,stopAccepted:decision.stopAccepted,noRevenge:decision.noRevenge,notes:decision.notes}
  // A response lost after commit is retried with the same identity and payload.
  if(!stepCommand||stepCommand.id!==id||stepCommand.body.expectedBarIndex!==body.expectedBarIndex)stepCommand={id,body}
  try{
    const sent=stepCommand.body
    current.value=await personalApi.step(id,sent);stepCommand=null;retryPending.value=false
    const rejected=current.value.session.orders.filter(o=>o.clientOrderId.endsWith(sent.commandId)&&o.rejectionReason)
    const checked=sent.stopAccepted&&sent.riskAccepted&&sent.noRevenge&&sent.emotion<3
    notice.value=rejected.length?rejected.map(o=>o.rejectionReason).join('；')
      :run.trainingMode==='GUIDED'&&run.plan.action==='ENTER'&&sent.action==='FOLLOW'&&!checked?'新开仓已拦截：检查单未完成或情绪过高。本次已按空仓观察记录，没有为了成交而放宽规则。'
      :'本次决定与执行结果已记录，已揭示下一根日线。以成交与委托记录为准，候选信号不保证实际成交。'
    decision.notes='';decision.riskAccepted=false;decision.stopAccepted=false;decision.noRevenge=false;decision.action='FOLLOW'
    eventPage.value=1
    if(!batch.value)await refreshRunViews()
  }catch(e){batch.value=false;retryPending.value=true;failure(e)}finally{working.value=false}
}
async function runBatch(){
  if(current.value?.trainingMode!=='RULE_REPLAY'||working.value)return
  batch.value=true
  try{
    for(let i=0;i<20&&batch.value&&alive&&current.value?.session.status==='ACTIVE';i++){
      if(current.value.riskHalted&&current.value.session.position.lots===0)break
      await stepOnce();if(error.value)break
    }
  }finally{batch.value=false;if(alive)await refreshRunViews()}
}
async function refresh(){
  if(working.value||batch.value)return
  working.value=true;error.value=''
  try{
    if(current.value)current.value=await personalApi.run(current.value.session.id)
    if(stepCommand&&current.value?.session.currentBarIndex!==stepCommand.body.expectedBarIndex){stepCommand=null;retryPending.value=false}
    await Promise.all([loadRuns(),loadReflections(),current.value?refreshRunViews():Promise.resolve()])
  }catch(e){failure(e)}finally{working.value=false}
}
async function saveReview(){
  if(!review.content.trim()){error.value='先写下事实、原因或下一次的具体动作';return}
  working.value=true;error.value=''
  const content=review.content,eventId=selectedEvent.value
  try{
    await personalApi.reflect({sessionId:runScope.value?current.value?.session.id:undefined,eventId:runScope.value?selectedEvent.value||undefined:undefined,category:review.category,content})
    if(review.content===content)review.content=''
    if(selectedEvent.value===eventId)selectedEvent.value=''
    reflectionPage.value=1;notice.value='复盘已追加到服务器，历史记录未被覆盖。';await loadReflections()
  }catch(e){failure(e)}finally{working.value=false}
}
function draftFromVersion(){const v=chosenVersion.value??versions.value[0];if(!v)return;versionDraft.parentId=v.id;versionDraft.rules={...v.rules};versionDraft.title=v.title+' · 改进候选'}
async function saveVersion(){
  working.value=true;error.value=''
  try{
    const priorIds=new Set(versions.value.map(v=>v.id))
    versions.value=await personalApi.createVersion({...versionDraft,rules:{...versionDraft.rules}})
    const added=versions.value.find(v=>!priorIds.has(v.id));if(added)create.versionId=added.id
    notice.value='已保存待验证的新版本。旧训练继续使用其原版参数，新版本不会自动获得“有效”结论。'
    versionDraft.hypothesis='';versionDraft.validationPlan=''
  }catch(e){failure(e)}finally{working.value=false}
}
async function allPages<T extends {id:string}>(load:(page:number)=>Promise<RecordPage<T>>){
  const first=await load(1),rows=[...first.items]
  for(let p=2;p<=Math.ceil(first.total/first.pageSize);p++)rows.push(...(await load(p)).items)
  if(rows.length!==first.total||new Set(rows.map(r=>r.id)).size!==rows.length)throw Error('导出时记录发生变化，请停止推进后重试')
  return rows
}
async function exportRun(){
  const run=current.value;if(!run||working.value||batch.value)return
  exporting.value=true;error.value=''
  try{
    const id=run.session.id
    const [decisions,notes,fills,orders]=await Promise.all([
      allPages(p=>personalApi.events(id,p,100)),allPages(p=>personalApi.reflections(id,p,100)),
      allPages(p=>api.paperFills(id,p,100)),allPages(p=>api.paperOrders(id,p,100)),
    ])
    const [latest,latestNotes]=await Promise.all([personalApi.run(id),personalApi.reflections(id,1,1)])
    if(latest.session.currentBarIndex!==run.session.currentBarIndex||latestNotes.total!==notes.length)throw Error('导出时模拟时点或复盘记录已变化，请停止推进后重试')
    const blob=new Blob([JSON.stringify({schemaVersion:1,exportedAt:new Date().toISOString(),strategyVersion:runVersion.value,run,decisions,reflections:notes,fills,orders},null,2)],{type:'application/json'})
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`个人总结-训练-${id}.json`;a.click();URL.revokeObjectURL(url)
    notice.value=`已导出全部 ${decisions.length} 条决策、${notes.length} 条复盘及完整成交与委托记录。`
  }catch(e){failure(e)}finally{exporting.value=false}
}
watch(runPage,()=>{runs.value=null;void loadRuns().catch(failure)})
watch(eventPage,()=>{events.value=null;void loadEvents().catch(failure)})
watch(reflectionPage,()=>{reflections.value=null;void loadReflections().catch(failure)})
watch(runScope,()=>{selectedEvent.value='';reflectionPage.value=1;void loadReflections().catch(failure)})
watch(tab,value=>{if(value!=='training')batch.value=false})
watch(()=>versionDraft.parentId,id=>{const v=versions.value.find(v=>v.id===id);if(v)versionDraft.rules={...v.rules}})
onMounted(async()=>{
  const results=await Promise.allSettled([personalApi.versions(),api.backtestPresets(),api.replayStatus(),loadRuns(),loadReflections()])
  if(results[0].status==='fulfilled'){versions.value=results[0].value;create.versionId=versions.value[0]?.id??'';draftFromVersion()}
  if(results[1].status==='fulfilled')presets.value=results[1].value
  if(results[2].status==='fulfilled')archives.value=results[2].value
  if(!products.value.some(p=>p.symbol===create.symbol))create.symbol=products.value[0]?.symbol??''
  setRange();loading.value=false
  if(results.some(r=>r.status==='rejected'))error.value='部分数据加载失败，请刷新重试；已有服务器记录未改变。'
  if(typeof route.query.run==='string')await selectRun(route.query.run)
})
onUnmounted(()=>{alive=false;batch.value=false;generation++})
</script>

<template>
  <div class="personal-page">
    <section class="personal-hero">
      <div><p class="eyebrow">PERSONAL PLAYBOOK / 生存、耐心与执行</p><h2>先把自己留在市场里。</h2><p>把你的总结变成能遵守、能训练、能复盘的规则。先问错了怎么办，再考虑值得不值得做。</p></div>
      <div class="hero-seal"><ShieldCheck :size="24"/><strong>生存优先 · 趋势突破回踩</strong><span>研究初版 · 收益优势待验证</span></div>
    </section>
    <div class="pillars"><span>不重仓</span><span>不逆势</span><span>不亏损加仓</span><span>入场必有保护</span><span>空仓也算执行</span></div>
    <nav class="personal-tabs" aria-label="个人总结栏目"><button v-for="item in pageTabs" :key="item.id" type="button" :aria-pressed="tab===item.id" @click="tab=item.id">{{item.title}}</button></nav>
    <p v-if="error" role="alert" class="alert">{{error}} <button type="button" @click="error=''">关闭</button></p>
    <p v-if="notice" role="status" class="notice">{{notice}}</p>

    <section v-if="tab==='original'" class="panel original">
      <div class="section-title"><BookOpen :size="20"/><div><h3>你的原文，完整保留</h3><p>以下是个人交易经验与自我要求；研究解释另列，不替换原意，也不把经验断言当作普遍规律。</p></div></div>
      <article v-for="section in originalSummary" :key="section.title"><h4>{{section.title}}</h4><ol><li v-for="line in section.lines" :key="line">{{line}}</li></ol></article>
      <div class="reading-note">新的感悟可以在“复盘与迭代”追加保存。原文、决策时的计划、事后复盘各自留档，避免事后改写自己的出发点。</div>
    </section>

    <section v-if="tab==='strategy'" class="strategy-content">
      <div class="interpretation panel"><div class="section-title"><Target :size="20"/><div><h3>从你的话，到可执行的选择</h3><p>执行保障系统的一致性；系统本身仍必须验证。严格执行无效系统，也可能持续亏损。</p></div></div><div class="mapping-grid"><article v-for="item in interpretations" :key="item.from"><h4>“{{item.from}}”</h4><p>{{item.to}}</p></article></div></div>
      <div class="step-grid"><article v-for="step in strategySteps" :key="step.title" class="panel strategy-step"><h3>{{step.title}}</h3><p>{{step.rule}}</p><div><strong>为什么这样做</strong><p>{{step.why}}</p></div></article></div>
      <section class="panel example"><h3>一笔交易，先算能不能错</h3><p>例如净值10万元，风险率0.5%，本笔预算500元。假设一手的结构止损损失300元，双边费用与滑点估算40元，则风险约束只允许 floor(500÷340)=1手。还要同时通过保证金占比与2倍名义敞口约束；其中任何一项不足一手，都选择不做。</p><p>500元是计划预算，遇到跳空或成交不足仍可能超出。盈利后浮盈可以回撤；本版用只能收紧的保护线和8%收盘回撤熔断约束自己，不宣称能锁住所有利润。</p><button class="primary" type="button" @click="tab='training'">用真实历史练一次 <Play :size="15"/></button></section>
      <details class="panel glossary"><summary>先读懂这几个词：均线、ATR、止损与保证金</summary><dl><dt>MA20 / MA60</dt><dd>最近20 / 60个已完成交易日收盘价的平均值，用来观察方向，不能提前知道趋势。</dd><dt>ATR14</dt><dd>近14日平均真实波幅，考虑高低价和相对前收盘的跳空，用来把不同品种的波动大小放在相近尺度比较。</dd><dt>做多 / 做空</dt><dd>多单通常随价格上涨获利，空单通常随价格下跌获利；方向相反会亏损，盈亏还受手数、合约乘数和费用影响。</dd><dt>结构止损</dt><dd>价格到了原交易理由不再成立的位置，按规则退出。止损是执行指令，不是保证一定能按那个价格成交。</dd><dt>保证金 / 名义敞口</dt><dd>保证金是持仓占用的资金，并不是最多只能亏这些钱；名义敞口=价格×乘数×手数，更接近你正在承受多大价格变动影响。</dd></dl></details>
      <section class="panel"><h3>怎么判断值得保留</h3><p>预先划分训练区间与留出区间，至少覆盖上涨、下跌、震荡和多个品种。分别看费用后盈亏、最大已观测回撤、实际止损与计划预算的偏差、频率和执行一致性。不能因一轮赚钱就宣布有效，也不能只因一次守规则的止损就推翻系统。至少20个完整交易只是开始审视的门槛，并不足以证明优势。</p><p>每次改进写清“改变什么、为何改变、如何证伪”，新建版本并进行独立训练。原版本与旧记录永不被新参数覆盖。规则回放的机器执行不代表人的执行能力。</p><p class="sources">风险与手数关系参考 <a href="https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size" target="_blank" rel="noopener noreferrer">CME 仓位管理教育</a>；止损成交限制参考 <a href="https://www.cftc.gov/sites/default/files/Stoploss_final_ada.pdf" target="_blank" rel="noopener noreferrer">CFTC 止损研究</a>。这些资料不验证本策略的技术阈值与盈利能力。</p></section>
    </section>

    <section v-if="tab==='training'" class="training-content">
      <details class="panel creation-details" :open="!current"><summary class="section-title"><Play :size="20"/><div><h3>创建一轮独立训练</h3><p>真实交割合约日线 · 历史逐步揭示 · 最多提前365天预热 · 不连接实盘账户</p></div></summary>
        <form class="create-training" @submit.prevent="createTraining">
          <label>训练名称<input v-model="create.name" maxlength="65" required/></label>
          <label>策略版本<select v-model="create.versionId" required><option v-for="v in versions" :key="v.id" :value="v.id">{{v.title}}</option></select></label>
          <label>训练方式<select v-model="create.trainingMode"><option value="GUIDED">自己做决策 · 练耐心与执行</option><option value="RULE_REPLAY">规则自动回放 · 研究策略表现</option></select></label>
          <label>搜索可回放品种<input v-model="search" type="search" placeholder="名称、代码或板块"/></label>
          <label>训练品种<select v-model="create.symbol" required><option v-for="p in filteredProducts" :key="p.symbol" :value="p.symbol">{{p.name}} · {{p.symbol}}</option></select></label>
          <label>虚拟初始资金（元）<input v-model.number="create.initialCash" type="number" min="10000" max="1000000000" step="10000" required/></label>
          <label>训练开始<input v-model="create.startDate" type="date" :min="selectedArchive?.startDate" :max="create.endDate" required/></label>
          <label>训练结束<input v-model="create.endDate" type="date" :min="create.startDate" :max="selectedArchive?.endDate" required/></label>
          <div class="create-note"><p v-if="selectedArchive">该品种真实数据 {{selectedArchive.startDate}} 至 {{selectedArchive.endDate}}，共{{selectedArchive.totalBars}}根日线。起点前需保留足够预热数据，缺失时拒绝创建。</p><p v-else>请先选择已有可执行历史的品种。</p><p v-if="chosenVersion">单笔风险 {{chosenVersion.rules.riskPct}}% · 保证金上限 {{chosenVersion.rules.maxMarginPct}}% · 放量 {{chosenVersion.rules.volumeRatio}}倍 · 止损上限 {{chosenVersion.rules.maxStopAtr}}ATR · 冷静期 {{chosenVersion.rules.cooldownBars}}日</p></div>
          <button class="primary" :disabled="working||loading||batch||!chosenVersion||!selectedArchive||!filteredProducts.some(p=>p.symbol===create.symbol)">创建并冻结本次训练</button>
        </form>
      </details>
      <details class="panel run-details" :open="!current"><summary>训练记录与账户切换 · {{runs?.total??0}}条</summary><div class="section-title"><NotebookPen :size="20"/><h3>训练记录</h3><button type="button" class="quiet" :disabled="working||batch" @click="refresh"><RefreshCw :size="14"/>刷新</button></div><div class="run-list"><button v-for="r in runs?.items" :key="r.id" type="button" :disabled="working||batch" :aria-pressed="current?.session.id===r.id" @click="selectRun(r.id)"><strong>{{r.name}}</strong><span>{{r.symbol}} · {{r.trainingMode==='GUIDED'?'自己决策':'规则回放'}} · {{r.versionTitle}}</span><small>{{formatTradingDate(r.currentMarketTime)}} · {{r.riskHalted?'回撤熔断':r.status}} · 净值 {{money(r.equity)}}</small></button></div><p v-if="runs&&!runs.total" class="empty">还没有训练。先用一个品种、一套固定规则开始，不急着扩大试验。</p><Pagination v-model:page="runPage" :total="runs?.total??0" :page-size="6" label="个人训练分页"/></details>

      <section v-if="current" class="panel current-training">
        <div class="section-title"><div><p class="eyebrow">{{current.trainingMode==='GUIDED'?'自己决策 · 人的执行练习':'规则回放 · 不计人的执行率'}}</p><h3>{{current.session.name}}</h3><p>{{runVersion?.title}} · 当前{{formatTradingDate(current.session.currentMarketTime)}} · {{current.session.currentContract}}</p></div><button class="quiet" type="button" :disabled="exporting||working||batch" @click="exportRun"><Download :size="14"/>{{exporting?'汇集全部记录…':'导出完整训练'}}</button></div>
        <div class="training-stats"><div><span>当前净值</span><strong>{{money(current.session.equity)}}</strong><small>净变化 {{money(current.session.equity-current.session.initialCash)}}，含未平浮盈亏</small></div><div><span>当前持仓</span><strong>{{current.session.position.direction>0?'多':current.session.position.direction<0?'空':'空仓'}} {{current.session.position.lots}}手</strong><small>保护价 {{amount(current.activeStop)}} · 浮动 {{money(current.session.position.unrealizedPnl)}}</small></div><div><span>人的执行一致性</span><strong>{{current.metrics.humanAdherencePct==null?'不评价':amount(current.metrics.humanAdherencePct)+'%'}}</strong><small>{{current.metrics.decisions}}次决策 · {{current.metrics.closedTradeCount}}次完整交易</small></div><div><span>最大已观测收盘回撤</span><strong>{{amount(current.metrics.maxDrawdownPct)}}%</strong><small>完整平仓净盈亏 {{money(current.metrics.closedNetPnl)}} · 超计划亏损 {{current.metrics.lossBeyondBudgetCount}}次</small></div></div>
        <p v-if="current.riskHalted" class="alert">本轮已触发8%收盘回撤熔断，禁止新开仓；未平持仓仍执行保护。先复盘，不通过重开账户回避回撤记录。</p>
        <p v-if="chartError" role="alert" class="alert">{{chartError}}</p>
        <TongdaxinChart v-if="points.length" :key="current.session.id" :points="points" :symbol="current.session.symbol" :display-name="current.session.currentContract" :height="390" default-theme="light" default-sub-chart="vol"/>
        <p class="subtle">图表截至当前已完成日线，不展示未来路径。图中是实际交割合约原始价格；策略均线使用截至当时已知换月价差平移，换月处两者可有差异。</p>
        <div class="decision-layout"><div class="plan-card"><span class="eyebrow">当前规则判断</span><h3>{{stateNames[current.plan.state]??current.plan.state}}</h3><ul><li v-for="reason in current.plan.reasons" :key="reason">{{reason}}</li></ul><dl><div><dt>下一日限价参考</dt><dd>{{current.plan.action==='ENTER'?amount(current.plan.entryPrice):'当前不新开仓'}}</dd></div><div><dt>结构 / 跟踪保护</dt><dd>{{amount(current.plan.stopPrice)}}</dd></div><div><dt>允许手数 / 预计损失</dt><dd>{{current.plan.maxLots}}手 / {{money(current.plan.plannedRisk)}}</dd></div><div><dt>本次风险预算</dt><dd>{{money(current.plan.riskBudget)}}</dd></div><div><dt>MA20 / MA60 / ATR14</dt><dd>{{amount(current.plan.ma20)}} / {{amount(current.plan.ma60)}} / {{amount(current.plan.atr)}}</dd></div></dl></div>
          <form class="decision-form" @submit.prevent="stepOnce">
            <template v-if="current.trainingMode==='GUIDED'"><h3>先决定，再揭示下一日</h3><label>我的决定<select v-model="decision.action" :disabled="working||retryPending"><option value="FOLLOW">按当前系统计划执行</option><option value="WAIT">选择观察 / 维持原有保护</option><option value="EXIT" :disabled="!current.session.position.lots">主动提前离场（记录执行偏差）</option></select></label><label>当前情绪强度（0平静，5失控）<input v-model.number="decision.emotion" :disabled="working||retryPending" type="range" min="0" max="5" step="1"/><span>{{decision.emotion}} / 5 · 达到3时禁止新开仓</span></label><div class="checklist"><label><input v-model="decision.stopAccepted" :disabled="working||retryPending" type="checkbox"/>我理解结构止损位置，不把它向亏损方向放宽</label><label><input v-model="decision.riskAccepted" :disabled="working||retryPending" type="checkbox"/>我能承担计划损失，并接受跳空超出预算的可能</label><label><input v-model="decision.noRevenge" :disabled="working||retryPending" type="checkbox"/>我不是为了翻本、刺激或害怕错过而交易</label></div><label>此刻的依据与犹豫<textarea v-model="decision.notes" :disabled="working||retryPending" maxlength="4000" placeholder="先记录，再看结果；空仓时也能练习等待。"/></label><p class="subtle">开仓需完成检查单。未确认时系统会拦截并记录，原有保护与必要退出不能取消。</p></template>
            <template v-else><h3>让冻结规则自己走一遍</h3><p>每根已完成日线作一次判断，下一根撮合。自动回放用于研究规则，不代替你练习克制与执行。</p></template>
            <p v-if="retryPending" class="subtle">上次响应未确认。重试会使用原命令与原决定，不重复下单；也可刷新查看最新结果。</p><div class="action-row"><button class="primary" :disabled="!canStep||batch">{{retryPending?'重试上次决定':'决策并推进下一日'}}</button><button v-if="current.trainingMode==='RULE_REPLAY'&&!batch" class="quiet" type="button" :disabled="!canStep" @click="runBatch"><Play :size="14"/>按规则推进20日</button><button v-if="batch" class="quiet" type="button" @click="batch=false"><Square :size="14"/>完成当前一步后停止</button></div>
            <p class="subtle">{{current.metrics.sampleWarning}}</p><p v-if="current.session.status==='PAUSED'" class="subtle">账户已暂停；可在<RouterLink to="/paper">模拟交易台</RouterLink>恢复后继续本模块训练。</p>
          </form>
        </div>
        <div class="journal-heading"><h3>每一次决定，都留下当时的依据</h3><button type="button" class="quiet" @click="tab='review'">写本次复盘 →</button></div>
        <article v-for="event in events?.items" :key="event.id" class="event"><header><strong>{{formatTradingDate(event.marketTime)}} · {{stateNames[event.plan.state]??event.plan.state}}</strong><span>{{actionNames[event.action]}} · {{event.outcome.automated?'机器回放':event.compliant?'遵守计划':'有执行偏差 / 被拦截'}}</span></header><p>净值 {{money(event.outcome.beforeEquity)}} → {{money(event.outcome.afterEquity)}} · 新开{{event.outcome.openedFillFragments}}个成交片段 / 平仓{{event.outcome.closedFillFragments}}个片段 · 情绪 {{event.emotion}}/5</p><p v-if="event.notes">当时写下：{{event.notes}}</p><ul v-if="event.outcome.notes.length"><li v-for="n in event.outcome.notes" :key="n">{{n}}</li></ul><p v-for="(o,i) in event.outcome.orders.filter(o=>o.rejection_reason)" :key="i">委托被拒绝：{{o.rejection_reason}}</p><details><summary>查看冻结的计划与规则判断</summary><p v-for="r in event.plan.reasons" :key="r">{{r}}</p><p>限价{{amount(event.plan.entryPrice)}} · 保护{{amount(event.plan.stopPrice)}} · 手数{{event.plan.maxLots}} · 预算{{money(event.plan.riskBudget)}}</p></details><button class="quiet" type="button" @click="selectedEvent=event.id;runScope=true;tab='review'">为这次决定追加复盘</button></article>
        <Pagination v-model:page="eventPage" :total="events?.total??0" :page-size="10" label="训练决策分页"/>
      </section>
    </section>

    <section v-if="tab==='review'" class="review-content">
      <section class="panel"><div class="section-title"><NotebookPen :size="20"/><div><h3>事实、执行、改进，分别写清</h3><p>记录保存到服务器，跨设备使用同一系统可读取。每次保存都追加新记录，不覆盖当时的判断。</p></div></div><form class="reflection-form" @submit.prevent="saveReview"><label v-if="current" class="inline-check"><input v-model="runScope" type="checkbox"/>关联当前训练：{{current.session.name}}</label><p v-if="selectedEvent">已关联一条历史决定。事后解释会独立保存，不修改原计划。</p><label>复盘主题<select v-model="review.category"><option v-for="(label,key) in categoryNames" :key="key" :value="key">{{label}}</option></select></label><label>我的总结<textarea v-model="review.content" maxlength="5000" required placeholder="发生了什么？是否按规则执行？亏损是正常成本还是执行偏差？下一次只改变什么？怎样证明这个改变不成立？"/></label><button class="primary" :disabled="working">追加保存复盘</button></form><p v-if="!reflections?.total" class="empty">从一次真实的决定开始记录，不必等到盈利以后。</p><article v-for="r in reflections?.items" :key="r.id" class="reflection"><header><strong>{{categoryNames[r.category]}}</strong><span>{{formatTradingDate(r.createdAt)}} · {{r.sessionId?'关联训练':'个人通用笔记'}}</span></header><p>{{r.content}}</p></article><Pagination v-model:page="reflectionPage" :total="reflections?.total??0" :page-size="10" label="个人复盘分页"/></section>
      <section class="panel version-lab"><h3>修改系统，另开版本</h3><p>一次只研究少量变化，先写假设和证伪方法，再调整阈值。不能把新参数套回旧日志，声称自己当时已经知道。四项致命错误始终受到服务器保护，不能通过调参放开满仓、不设止损、逆势加仓或亏损加仓。</p><form @submit.prevent="saveVersion"><label>父版本<select v-model="versionDraft.parentId"><option v-for="v in versions" :key="v.id" :value="v.id">{{v.title}}</option></select></label><button class="quiet" type="button" @click="draftFromVersion">从训练表单选中的版本复制参数</button><label>新版本名称<input v-model="versionDraft.title" maxlength="120" required/></label><label>改变与依据<textarea v-model="versionDraft.hypothesis" maxlength="4000" required placeholder="例如：只改变放量阈值。为何可能减少假突破？可能牺牲什么？"/></label><label>预先规定的验证与证伪方法<textarea v-model="versionDraft.validationPlan" maxlength="4000" required placeholder="写明品种、时间分割、留出样本、费用压力、回撤与执行容忍度。先定标准，后看结果。"/></label><div class="rule-inputs"><label>单笔风险（%）<input v-model.number="versionDraft.rules.riskPct" type="number" min="0.1" max="1" step="0.1" required/></label><label>保证金上限（%）<input v-model.number="versionDraft.rules.maxMarginPct" type="number" min="5" max="25" step="1" required/></label><label>放量倍数<input v-model.number="versionDraft.rules.volumeRatio" type="number" min="1.2" max="3" step="0.1" required/></label><label>最远止损（ATR）<input v-model.number="versionDraft.rules.maxStopAtr" type="number" min="1" max="3" step="0.1" required/></label><label>退出冷静期（日线）<input v-model.number="versionDraft.rules.cooldownBars" type="number" min="2" max="10" step="1" required/></label></div><button class="primary" :disabled="working||!versionDraft.parentId">保存为待验证的新版本</button></form>
        <details v-for="v in pagedVersions" :key="v.id" class="version"><summary>{{v.title}} · {{formatTradingDate(v.createdAt)}} · 待验证</summary><p>{{v.hypothesis}}</p><p>{{v.validationPlan}}</p><p>风险{{v.rules.riskPct}}% · 保证金{{v.rules.maxMarginPct}}% · 放量{{v.rules.volumeRatio}}倍 · 止损{{v.rules.maxStopAtr}}ATR · 冷静期{{v.rules.cooldownBars}}日</p><small>{{v.engineVersion}} · {{v.id}}</small></details><Pagination v-model:page="versionPage" :total="versionTotal" :page-size="6" label="策略版本分页"/>
      </section>
    </section>
  </div>
</template>

<style scoped>
.creation-details>summary{cursor:pointer;margin-bottom:0}.creation-details[open]>summary{margin-bottom:1rem}.creation-details>summary h3{margin-bottom:.2rem}.run-details>summary,.glossary>summary{cursor:pointer;font-size:.8rem;color:var(--color-accent);line-height:1.8}.run-details[open]>summary{margin-bottom:1rem}.glossary dt{font-size:.8rem;font-weight:650;margin-top:1rem}.glossary dd{font-size:.75rem;line-height:1.8;color:var(--color-ink-secondary);margin:.4rem 0}
.personal-page{display:grid;gap:1rem;min-width:0}.personal-hero{display:flex;justify-content:space-between;align-items:center;gap:2rem;padding:1.6rem 1.8rem;background:#1f302d;border-radius:1.1rem;color:#fff}.personal-hero h2{font-size:1.9rem;margin:.45rem 0 .8rem}.personal-hero p{font-size:.8rem;line-height:1.8;max-width:44rem;margin:.3rem 0;color:#d7e4de}.eyebrow{font-size:.65rem;letter-spacing:.1em;color:var(--color-accent);margin:0 0 .5rem}.personal-hero .eyebrow{color:#b7cbbf}.hero-seal{display:grid;gap:.6rem;min-width:13rem;padding:1rem;border:1px solid #577367;border-radius:.75rem}.hero-seal strong{font-size:.85rem}.hero-seal span{font-size:.68rem;color:#c7d5ce}.pillars{display:flex;flex-wrap:wrap;gap:.5rem}.pillars span{border:1px solid var(--color-line);padding:.5rem .8rem;border-radius:2rem;font-size:.7rem;background:var(--color-surface)}.personal-tabs{display:flex;gap:.3rem;border-bottom:1px solid var(--color-line);overflow:auto}.personal-tabs button{padding:.9rem 1rem;white-space:nowrap;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--color-ink-secondary);font-size:.8rem;cursor:pointer}.personal-tabs button[aria-pressed=true]{color:var(--color-accent);border-bottom-color:var(--color-accent);font-weight:700}.panel{min-width:0;border:1px solid var(--color-line);border-radius:.95rem;padding:1.5rem;background:var(--color-surface)}h3{font-size:1.05rem;margin:.2rem 0 .8rem}h4{font-size:.86rem;margin:.5rem 0}p,li{font-size:.76rem;line-height:1.9;color:var(--color-ink-secondary)}.section-title{display:flex;align-items:flex-start;gap:.7rem;margin-bottom:1.1rem;color:var(--color-accent)}.section-title h3{color:var(--color-ink)}.section-title p{margin:.1rem 0}.section-title>.quiet{margin-left:auto}.original article{margin-top:1.4rem}.original ol{padding-left:1.3rem}.original li{padding:.35rem 0}.reading-note,.notice{padding:1rem;border-radius:.6rem;background:#eaf2ed;color:#315749;font-size:.75rem;line-height:1.8}.strategy-content,.training-content,.review-content{display:grid;gap:1rem}.mapping-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.9rem}.mapping-grid article{padding:1rem;background:var(--color-canvas);border-radius:.65rem}.step-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.strategy-step>div{border-top:1px solid var(--color-line);margin-top:.9rem;padding-top:.9rem}.strategy-step strong{font-size:.7rem;color:var(--color-accent)}.strategy-step p{margin:.5rem 0}.sources{font-size:.68rem}.primary,.quiet{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;min-height:2.5rem;padding:.65rem 1rem;border-radius:.5rem;font-size:.75rem;cursor:pointer}.primary{border:1px solid var(--color-accent);background:var(--color-accent);color:#fff}.quiet{border:1px solid var(--color-line);background:transparent;color:var(--color-accent)}button:disabled{opacity:.5;cursor:not-allowed}button:focus-visible,a:focus-visible{outline:2px solid var(--color-accent);outline-offset:3px}.create-training{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem}.create-note{grid-column:1/-1}.create-note p{font-size:.69rem;margin:.2rem 0}label{display:grid;gap:.45rem;font-size:.72rem;color:var(--color-ink-secondary);min-width:0}input,select,textarea{box-sizing:border-box;width:100%;min-width:0;border:1px solid var(--color-line-strong,var(--color-line));background:var(--color-surface);border-radius:.5rem;padding:.65rem;color:var(--color-ink);font:inherit}input:focus,select:focus,textarea:focus{outline:2px solid var(--color-accent);outline-offset:2px}textarea{min-height:5.5rem;resize:vertical;line-height:1.8}.alert{padding:.8rem 1rem;border-radius:.55rem;background:#fff0e8;color:#8a3e25}.alert button{border:0;background:transparent;color:inherit;margin-left:.6rem;cursor:pointer}.run-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem}.run-list button{display:grid;text-align:left;gap:.5rem;padding:.85rem;border:1px solid var(--color-line);border-radius:.55rem;background:transparent;cursor:pointer;color:var(--color-ink);min-width:0}.run-list button[aria-pressed=true]{background:#edf4ef;border-color:var(--color-accent)}.run-list strong{font-size:.8rem;overflow-wrap:anywhere}.run-list span,.run-list small{font-size:.65rem;line-height:1.7;color:var(--color-ink-secondary)}.training-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem;margin:1rem 0}.training-stats>div{display:grid;gap:.5rem;padding:1rem;border:1px solid var(--color-line);border-radius:.65rem}.training-stats span,.training-stats small{font-size:.66rem;color:var(--color-ink-secondary)}.training-stats strong{font-size:1.15rem;font-variant-numeric:tabular-nums}.subtle{font-size:.68rem;line-height:1.85}.decision-layout{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-top:1rem}.plan-card{padding:1.25rem;background:#edf3ef;border-radius:.7rem}.plan-card h3{font-size:1.2rem}.plan-card ul{padding-left:1.1rem}.plan-card dl{margin:0}.plan-card dl>div{display:flex;justify-content:space-between;gap:1rem;border-top:1px solid #d3e0d6;padding:.75rem 0;font-size:.69rem}.plan-card dt{color:var(--color-ink-secondary)}.plan-card dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}.decision-form{display:grid;align-content:start;gap:1rem}.checklist{display:grid;gap:.6rem}.checklist label,.inline-check{display:flex;align-items:flex-start;gap:.5rem;line-height:1.7}.checklist input,.inline-check input{width:1rem;min-width:1rem;margin-top:.1rem}.action-row{display:flex;flex-wrap:wrap;gap:.5rem}.journal-heading{display:flex;justify-content:space-between;gap:1rem;align-items:center;margin-top:1.5rem}.event,.reflection{border:1px solid var(--color-line);border-radius:.7rem;padding:1rem;margin-top:.8rem}.event header,.reflection header{display:flex;justify-content:space-between;gap:.8rem;flex-wrap:wrap}.event header strong,.reflection strong{font-size:.77rem}.event header span,.reflection header span{font-size:.66rem;color:var(--color-ink-secondary)}.event summary,.version summary{cursor:pointer;font-size:.72rem;line-height:1.7;color:var(--color-accent)}.event .quiet{margin-top:.8rem;min-height:2rem;padding:.4rem .6rem;font-size:.68rem}.reflection p{white-space:pre-wrap;overflow-wrap:anywhere}.reflection-form,.version-lab form{display:grid;gap:1rem}.version-lab form{padding:1rem 0;border-bottom:1px solid var(--color-line);margin-bottom:1rem}.rule-inputs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.7rem}.version{padding:.8rem 0;border-bottom:1px solid var(--color-line)}.version small{font-size:.62rem;overflow-wrap:anywhere}.empty{padding:1rem 0;color:var(--color-ink-tertiary)}a{color:var(--color-accent)}@media(max-width:1050px){.create-training{grid-template-columns:repeat(2,minmax(0,1fr))}.run-list{grid-template-columns:repeat(2,minmax(0,1fr))}.rule-inputs{grid-template-columns:repeat(3,minmax(0,1fr))}.personal-hero{gap:1rem}.personal-hero h2{font-size:1.6rem}}@media(max-width:720px){.personal-hero{align-items:stretch;flex-direction:column;padding:1.25rem}.hero-seal{min-width:0}.mapping-grid,.step-grid,.decision-layout{grid-template-columns:1fr}.panel{padding:1.1rem}.training-stats{grid-template-columns:1fr}.run-list{grid-template-columns:1fr}.rule-inputs{grid-template-columns:1fr 1fr}.journal-heading{align-items:flex-start}.section-title{flex-wrap:wrap}}@media(max-width:430px){.create-training{grid-template-columns:1fr}.personal-tabs button{padding:.8rem .65rem}.plan-card dl>div{display:grid;gap:.4rem}.plan-card dd{text-align:left}}
</style>

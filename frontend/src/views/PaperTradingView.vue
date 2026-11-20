<script setup lang="ts">
import {instrumentLabel} from '../utils/instrumentNames'
import {
  Activity, AlertTriangle, ArrowDown, ArrowUp, CirclePause, Clock3, Database,
  FastForward, Gauge, History, LoaderCircle, Pause, Play, Plus, RefreshCw,
  RotateCcw, ShieldCheck, StepForward, Trash2, WalletCards, X,
} from 'lucide-vue-next'
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {routeLocationKey,routerKey} from 'vue-router'
import {workflowTrialsApi,workflowsApi,type WorkflowTrial,type WorkflowTrialDetail,type WorkflowVersion} from '../services/workflows'
import {useExperience} from '../composables/useExperience'
const {isSimple}=useExperience()

import {
  api,
  type BacktestPresets,
  type CreatePaperSessionRequest,
  type ReplayStatus,
  type MarketMicrostructure,
  type PaperSession,
  type PaperSessionSummary,
  type PlacePaperOrderRequest,
} from '../services/api'
import { formatNumber, formatTime, formatTradingDate } from '../utils/format'
import TongdaxinChart from '../components/TongdaxinChart.vue'
import Pagination from '../components/Pagination.vue'
import PaperStrategyPanel from '../components/PaperStrategyPanel.vue'
import PaperFillJournal from '../components/PaperFillJournal.vue'
import PaperIntradayChart from '../components/PaperIntradayChart.vue'
import PaperPortfolioPanel from '../components/PaperPortfolioPanel.vue'
import PaperAutomationPanel from '../components/PaperAutomationPanel.vue'
import MaTrendWorkflowReplay from '../components/MaTrendWorkflowReplay.vue'
import ReplayReviewPanel from '../components/ReplayReviewPanel.vue'
import type {PaperPortfolioPosition} from '../services/api'
import type {IntradayCatalog} from '../services/api'
import type {WorkflowShadow} from '../services/workflows'
import {requestId} from '../utils/requestId'
import {decisionsApi} from '../services/decisions'
import {authState,hasPermission} from '../services/auth'
import {paperStrategyId,PAPER_STRATEGIES} from '../utils/paperStrategies'
import {isTrinityPaperContract,readTrinityPaperLaunch,TRINITY_STRATEGY_ID} from '../utils/personalTrinity'
import {paperChartTrades} from '../utils/paperChartTrades'
import {usePagination} from '../composables/usePagination'
import type {PaperChart,PaperFill,PaperOrder,RecordPage,HistoryPoint} from '../services/api'
import type {ReplayReviewContext,ReplayReviewTarget} from '../services/replayReviews'

const chart=ref<PaperChart|null>(null),chartError=ref(''),chartLoading=ref(false),chartLimit=ref(240)
const chartView=ref<'intraday'|'candle'>('intraday'),chartPeriod=ref(60)
const showDkx=ref(true)
const showSubChart=ref(false)
const liveNow=ref(Date.now())
let liveChartTimer:number|undefined,chartClockTimer:number|undefined,lastChartTarget=''
const chartPeriods=[{seconds:60,label:'1分钟'},{seconds:180,label:'3分钟'},{seconds:300,label:'5分钟'},{seconds:900,label:'15分钟'},{seconds:1800,label:'30分钟'},{seconds:3600,label:'60分钟'},{seconds:86400,label:'日线'}]
const fillsPage=ref(1),ordersPage=ref(1)
const fillRecords=ref<RecordPage<PaperFill>|null>(null),orderRecords=ref<RecordPage<PaperOrder>|null>(null),recordsError=ref('')
let chartGeneration=0,recordsGeneration=0
const chartPoints=computed<HistoryPoint[]>(()=>chart.value?.bars.map((bar,index,bars)=>({
  ...bar,price:bar.close,changePct:index&&bars[index-1].close>0?(bar.close/bars[index-1].close-1)*100:0,
}))??[])
const chartExecutions=computed(()=>paperChartTrades(chartPoints.value,chart.value?.fills??[],chart.value?.asOf??'',current.value?.mode??'HISTORICAL',chart.value?.barSeconds??current.value?.barSeconds??86400))
const selectedFill=ref<PaperFill|null>(null)
const intraday=ref<IntradayCatalog|null>(null)
const isMinute=computed(()=>!!current.value&&!!current.value.barSeconds&&current.value.barSeconds!==86400)
const isLive=computed(()=>current.value?.mode==='LIVE')
const canSwitchChart=computed(()=>isLive.value||isMinute.value)
const liveFresh=computed(()=>{
 const age=chart.value?.dataTimestamp?(liveNow.value-Date.parse(chart.value.dataTimestamp))/1000:Infinity
 return isLive.value&&!chartError.value&&chart.value?.snapshotKind==='LIVE'&&chart.value.contextStatus==='READY'&&chart.value.connected&&chart.value.dataStatus==='FRESH'&&age>=-10&&age<=60
})
const liveStatus=computed(()=>chartError.value?'图表刷新失败':!chart.value?'实时行情订阅中':liveFresh.value?'实时更新 · 每2秒刷新':chart.value?.marketState==='CLOSED_CACHE'?'休市 · 最近收到的行情':chart.value?.contextStatus==='UNAVAILABLE'?'实时行情订阅中 / 暂不可用':chart.value?.connected?'行情延迟 / 数据过期':'行情连接中断')
const displayPrice=computed(()=>isLive.value?(chart.value?.lastPrice&&chart.value.lastPrice>0?chart.value.lastPrice:undefined):current.value?.currentPrice)
const creatingMinute=computed(()=>createForm.value.mode==='HISTORICAL'&&createForm.value.barSeconds!==86400)
function editFill(fill:PaperFill){stopAutoplay();selectedFill.value=fill}
async function refreshChart(){
  const session=current.value,generation=++chartGeneration
  window.clearTimeout(liveChartTimer);liveChartTimer=undefined
  const seconds=chartView.value==='intraday'?60:chartPeriod.value
  const target=session?`${session.id}:${session.currentContract}:${canSwitchChart.value?seconds:86400}`:''
  if(target!==lastChartTarget||!isLive.value)chart.value=null
  lastChartTarget=target;chartError.value='';liveNow.value=Date.now()
  if(!session)return
  chartLoading.value=!chart.value
  try{const result=canSwitchChart.value?await api.paperChart(session.id,chartView.value==='intraday'?720:chartLimit.value,seconds):await api.paperChart(session.id,chartLimit.value);if(generation===chartGeneration)chart.value=result}
  catch(e){if(generation===chartGeneration)chartError.value=e instanceof Error?e.message:'K线暂不可用'}
  finally{if(generation===chartGeneration){chartLoading.value=false;scheduleLiveChart(generation)}}
}
function scheduleLiveChart(generation:number){
 if(disposed||generation!==chartGeneration||!isLive.value)return
 liveChartTimer=window.setTimeout(()=>{if(document.hidden)scheduleLiveChart(generation);else void refreshChart()},2000)
}
function resumeChart(){if(!document.hidden&&isLive.value)void refreshChart()}
async function refreshRecords(){
  const session=current.value,generation=++recordsGeneration
  if(!session)return
  recordsError.value='';fillRecords.value=null;orderRecords.value=null
  const results=await Promise.allSettled([api.paperFills(session.id,fillsPage.value),api.paperOrders(session.id,ordersPage.value)])
  if(generation!==recordsGeneration)return
  if(results[0].status==='fulfilled')fillRecords.value=results[0].value
  if(results[1].status==='fulfilled')orderRecords.value=results[1].value
  if(results.some(r=>r.status==='rejected'))recordsError.value='流水分页读取失败，请重试；账户快照仍保留最近记录。'
}


const sessions = ref<PaperSessionSummary[]>([])
const current = ref<PaperSession | null>(null)
const workflowTrials = ref<WorkflowTrial[]>([])
const activeWorkflowTrial = ref<WorkflowTrialDetail | null>(null)
const workflowTrialsError = ref('')
const savingWorkflowTrial = ref(false)
const reviewingReplay=ref(false)
const reviewContext=computed<ReplayReviewContext|null>(()=>{
  const session=current.value
  return session?.mode==='HISTORICAL'?{kind:'session',id:session.id}:null
})
const reviewFills=computed<ReplayReviewTarget[]>(()=>(fillRecords.value?.items??current.value?.fills??[]).slice(0,20).map(fill=>({
  id:fill.id,at:fill.marketTime,label:`${formatTime(fill.marketTime)} · ${fill.side==='BUY'?'买':'卖'}${fill.offset==='OPEN'?'开':'平'} ${fill.quantity} 手`,
})))
const decisionSource=ref<{caseId?:string;planId?:string;version?:number}|null>(null)
let decisionGeneration=0
watch(()=>current.value?.id,async id=>{
 const ticket=++decisionGeneration;decisionSource.value=null
 if(!selecting.value)syncSessionRoute()
 if(!id||!hasPermission('market.read'))return
 try{const source=await decisionsApi.forSession(id);if(ticket===decisionGeneration)decisionSource.value=source}catch{/* No source is shown unless the authoritative link is readable. */}
})
const presets = ref<BacktestPresets | null>(null)
const history = ref<ReplayStatus | null>(null)
const historyError=ref('')
const presetsError=ref('')
const symbolSearch=ref(''),sectorFilter=ref('全部板块'),historyRefreshing=ref(false)
const loading = ref(true)
const working = ref(false)
const selecting = ref(false)
let selectionGeneration = 0
let disposed=false
const error = ref('')
const showCreate = ref(false)
const strategyPicker=ref<HTMLSelectElement>()
async function openCreate(){
 if(savingWorkflowTrial.value)return
 showCreate.value=true
 stopAutoplay()
 await nextTick()
 strategyPicker.value?.closest('.create-panel')?.scrollIntoView?.({block:'start'})
 strategyPicker.value?.focus({preventScroll:true})
}
const autoplay = ref(false)
let autoplayTimer: number | undefined
const microstructure = ref<MarketMicrostructure | null>(null)
const microError = ref('')
const microLoading = ref(false)
const showDeleteConfirm = ref(false)
let microTimer: number | undefined
let microGeneration = 0

const createForm = ref<CreatePaperSessionRequest>({
  name: '玻璃分时手动练习', mode: 'HISTORICAL', symbol: 'FG701', initialCash: 100_000,
  barSeconds:60,stopLossTicks:10,intradayOnly:true,
  marginRate: 0.12, feeRate: 0.0001, slippageTicks: 1,
  maxParticipationRate: 0.1, autoRoll: false,
  strategyId:'MANUAL',strategyLots:1,stopLossAtr:2,takeProfitAtr:3,
})
const route=inject(routeLocationKey,undefined),router=inject(routerKey,undefined)
const requestedAutomation=computed(()=>paperStrategyId(route?.query.automation))
const requestedAutomationName=computed(()=>PAPER_STRATEGIES.find(item=>item.id===requestedAutomation.value)?.name)
const requestedTrinity=computed(()=>{
  if(requestedAutomation.value!==TRINITY_STRATEGY_ID||!authState.user)return null
  return readTrinityPaperLaunch(route?.query.trinity)
})
const trinityLaunchMissing=computed(()=>requestedAutomation.value===TRINITY_STRATEGY_ID&&route?.query.trinity!==undefined&&!requestedTrinity.value)
let sessionRouteReady=false
function syncSessionRoute(push=false){if(!router||!sessionRouteReady||!current.value||!route?.query.trial&&route?.query.session===current.value.id&&route?.query.contract===(current.value.currentContract||current.value.symbol))return;const q={...route?.query,session:current.value.id,contract:current.value.currentContract||current.value.symbol};for(const k of ['case','plan','decision','monitor','trial'])delete (q as Record<string,unknown>)[k];void router[push?'push':'replace']({path:'/paper',query:q,hash:route?.hash})}
watch(()=>current.value?.currentContract,()=>{if(!selecting.value)syncSessionRoute()})
watch(()=>route?.query.session,id=>{if(!sessionRouteReady||selecting.value)return;if(typeof id==='string'&&id!==current.value?.id)void selectSession(id);else if(id===undefined)syncSessionRoute()})
watch(()=>route?.query.trial,id=>{
 if(sessionRouteReady&&typeof id==='string'&&id!==activeWorkflowTrial.value?.trial.id&&!selecting.value)void selectWorkflowTrial(id)
})
const workflowVersions=ref<WorkflowVersion[]>([]),workflowError=ref(''),workflowLoading=ref(false)
const maReplayVersions=ref<WorkflowVersion[]>([])
const workflowShadows=ref<WorkflowShadow[]>([])
const workflowShadowError=ref('')
const chosenWorkflow=computed(()=>workflowVersions.value.find(v=>v.id===createForm.value.workflowVersionId))
const maReplayVersion=computed(()=>createForm.value.mode==='HISTORICAL'
 ? maReplayVersions.value.find(v=>v.id===createForm.value.workflowVersionId) : undefined)
const hasWorkflowVersions=computed(()=>workflowVersions.value.length>0
 || (createForm.value.mode==='HISTORICAL' && maReplayVersions.value.length>0))
async function loadWorkflows(){
 if(workflowLoading.value)return
 workflowLoading.value=true
 workflowError.value=''
 try{
  const [daily,minute]=await Promise.allSettled([workflowsApi.versions(),workflowsApi.maTrendVersions()])
  if(daily.status==='fulfilled')workflowVersions.value=daily.value
  if(minute.status==='fulfilled')maReplayVersions.value=minute.value
  const failedCatalogs=[
   daily.status==='rejected'?'日线策略':'',
   minute.status==='rejected'?'15 分钟均线策略':'',
  ].filter(Boolean)
  if(failedCatalogs.length)workflowError.value=`${failedCatalogs.join('和')}版本读取失败，请重试。`
 }finally{workflowLoading.value=false}
}
const createStrategySelection=computed({
 get:()=>createForm.value.strategyId??'MANUAL',
 set:(value:string)=>{
  const switchedToDaily=creatingMinute.value&&value!=='MANUAL'
  createForm.value.strategyId=value
  if(switchedToDaily){symbolSearch.value='';sectorFilter.value='全部板块'}
  selectCreateStrategy()
 },
})
watch(()=>createForm.value.strategyId,value=>{if(value!=='MANUAL')createForm.value.barSeconds=86400;if(value==='WORKFLOW')void loadWorkflows();else {delete createForm.value.workflowVersionId;delete createForm.value.workflowShadowId;workflowShadows.value=[]}})
watch(chosenWorkflow,async (version,previous,onCleanup)=>{
 workflowShadows.value=[]
 workflowShadowError.value=''
 if(previous)delete createForm.value.workflowShadowId
 if(!version)return
 createForm.value.strategyLots=version.lots
 createForm.value.stopLossAtr=version.stopLossAtr
 createForm.value.takeProfitAtr=version.takeProfitAtr
 if(version.engineVersion!=='workflow-daily-v2')return
 createForm.value.mode='HISTORICAL'
 let current=true
 onCleanup(()=>{current=false})
 try{
  const shadows=await workflowsApi.shadows(version.id)
  if(current)workflowShadows.value=shadows
 }catch(e){
  if(current)workflowShadowError.value=e instanceof Error?e.message:'观察列表读取失败'
 }
})
const order = ref<PlacePaperOrderRequest>({
  clientOrderId: '', side: 'BUY', offset: 'OPEN', orderType: 'MARKET', quantity: 1,
})

const isHistorical = computed(() => current.value?.mode === 'HISTORICAL')
const isStrategy = computed(()=>!!current.value?.strategyId&&current.value.strategyId!=='MANUAL')
const canUsePortfolio=computed(()=>isLive.value&&!isStrategy.value&&!current.value?.decisionGuarded&&!current.value?.managedTraining)
const canSeeAutomation=computed(()=>!!current.value&&canUsePortfolio.value&&hasPermission('market.read'))
const automationLocked=ref(false)
async function refreshAutomationAccount(){
 const snapshot=current.value
 if(!snapshot||working.value||selecting.value)return
 try{const updated=await api.paperSession(snapshot.id)
  if(current.value?.id===snapshot.id&&current.value.currentContract===snapshot.currentContract&&!working.value&&!selecting.value&&updated.version>=current.value.version)updateSession(updated)
 }catch{/* The automation panel retains its independent status and retries. */}
}
const totalMargin=computed(()=>current.value?.totalMargin??current.value?.position.marginOccupied??0)
const totalUnrealized=computed(()=>current.value?.totalUnrealized??current.value?.position.unrealizedPnl??0)
let orderAttempt:{signature:string;id:string}|null=null
function selectCreateStrategy(){
  const preset=presets.value?.strategies?.find(s=>s.id===createForm.value.strategyId)
  if(preset?.recommendedParams){createForm.value.stopLossAtr=preset.recommendedParams.stopLossAtr;createForm.value.takeProfitAtr=preset.recommendedParams.takeProfitAtr}
}
function compareStrategy(){stopAutoplay();showCreate.value=true;createStrategySelection.value='BOLLINGER_REVERSAL'}
const availableCash = computed(() => current.value
  ? current.value.availableCash??current.value.equity-totalMargin.value : 0)
const returnPct = computed(() => current.value
  ? (current.value.equity / current.value.initialCash - 1) * 100 : 0)
const progressPct = computed(() => {
  if (!current.value?.totalBars) return 0
  return Math.min(100, current.value.currentBarIndex / Math.max(1, current.value.totalBars - 1) * 100)
})
const selectedHistory = computed(() => (creatingMinute.value?intraday.value?.symbols:history.value?.symbols)?.find(item => item.symbol === createForm.value.symbol))
const availableSymbols=computed(()=>creatingMinute.value?intraday.value?.symbols??[]:createForm.value.mode==='HISTORICAL'
  ? presets.value?.symbols.filter(item=>history.value?.symbols.some(row=>row.symbol===item.symbol))??[]
  : presets.value?.symbols??[])
function prepareAutomationAccount(){
  stopAutoplay()
  showCreate.value=true
  createForm.value.mode='LIVE'
  createForm.value.strategyId='MANUAL'
  createForm.value.autoRoll=false
  createForm.value.name=requestedAutomationName.value?`${requestedAutomationName.value} · 模拟盘`:'量化模拟盘'
  symbolSearch.value=''
  sectorFilter.value='全部板块'
  if(requestedAutomation.value===TRINITY_STRATEGY_ID){
    const desired=requestedTrinity.value?.config.symbol
    const root=desired?.replace(/\d+$/,'')
    const matching=availableSymbols.value.find(item=>item.symbol===desired||item.symbol===`${root}M`||item.symbol===`${root}0`)
    const fallback=availableSymbols.value.find(item=>isTrinityPaperContract(item.symbol)||/^(FG|SA|AP|CJ)[M0]$/.test(item.symbol))
    const preferred=matching??fallback
    if(preferred)createForm.value.symbol=preferred.symbol
  }
}
const sectors=computed(()=>['全部板块',...new Set(availableSymbols.value.map(item=>item.sector).filter(Boolean))])
const filteredSymbols=computed(()=>{
  const query=symbolSearch.value.trim().toLowerCase()
  return availableSymbols.value.filter(item=>(sectorFilter.value==='全部板块'||item.sector===sectorFilter.value)
    &&(!query||[item.symbol,item.name,item.exchange,item.sector].some(value=>value?.toLowerCase().includes(query))))
})
const symbolGroups=computed(()=>[...new Set(filteredSymbols.value.map(item=>item.exchange||'其他'))].map(exchange=>({
  exchange,items:filteredSymbols.value.filter(item=>(item.exchange||'其他')===exchange),
})))
const exchangeNames:Record<string,string>={SHFE:'上期所',INE:'上海国际能源交易中心',DCE:'大商所',CZCE:'郑商所',CFFEX:'中金所',GFEX:'广期所'}
async function refreshHistory(){
  if(historyRefreshing.value)return
  historyRefreshing.value=true;historyError.value=''
  const previous=selectedHistory.value
  try{
    if(creatingMinute.value)intraday.value=await api.intradayCatalog()
    else history.value=await api.replayStatus()
    if(createForm.value.mode==='HISTORICAL'&&previous?.symbol===createForm.value.symbol
      &&createForm.value.startDate===previous.startDate&&createForm.value.endDate===previous.endDate)
      applyHistoryRange()
  }
  catch{historyError.value='回放目录刷新失败，已加载的品种仍可使用。'}
  finally{historyRefreshing.value=false}
}
const activeOrders = computed(() => current.value?.activeOrders??current.value?.orders.filter(item => ['PENDING', 'PARTIAL'].includes(item.status)) ?? [])
const experimentTabs=computed(()=>[
 ...workflowTrials.value.map(trial=>({...trial,mode:'HISTORICAL',status:'ACTIVE',kind:'workflow' as const})),
 ...sessions.value.map(session=>({...session,kind:'session' as const})),
])
const {items:pagedSessions,page:sessionPage,total:sessionTotal}=usePagination(experimentTabs,6)

async function loadWorkflowTrials(){
 workflowTrialsError.value=''
 try{
  const saved=await workflowTrialsApi.list()
  if(disposed)return
  const active=activeWorkflowTrial.value?.trial
  workflowTrials.value=active&&!saved.some(item=>item.id===active.id)?[active,...saved]:saved
 }catch{
  if(!disposed)workflowTrialsError.value='已保存的策略试验暂时无法读取。'
 }
}

function activateWorkflowTrial(detail:WorkflowTrialDetail){
 if(disposed)return
 stopAutoplay()
 stopMicrostructure()
 current.value=null
 showDeleteConfirm.value=false
 activeWorkflowTrial.value=detail
 if(!workflowTrials.value.some(item=>item.id===detail.trial.id))workflowTrials.value.unshift(detail.trial)
 showCreate.value=false
 const index=experimentTabs.value.findIndex(item=>item.kind==='workflow'&&item.id===detail.trial.id)
 sessionPage.value=Math.floor(index/6)+1
 if(router&&route?.query.trial!==detail.trial.id)void router.push({path:'/paper',query:{trial:detail.trial.id}})
 if(!maReplayVersions.value.length)void loadWorkflows()
}

async function selectWorkflowTrial(id:string){
 if(disposed||working.value||savingWorkflowTrial.value)return
 const generation=++selectionGeneration
 selecting.value=true
 stopAutoplay()
 error.value=''
 try{
  const detail=await workflowTrialsApi.get(id)
  if(generation===selectionGeneration)activateWorkflowTrial(detail)
 }catch(cause){
  if(generation===selectionGeneration)setError(cause,'读取历史策略试验失败')
 }finally{
  if(generation===selectionGeneration)selecting.value=false
 }
}
const {items:pagedActive,page:activePage,total:activeTotal}=usePagination(activeOrders,6,[()=>current.value?.id])
const asksDescending = computed(() => [...(microstructure.value?.asks ?? [])].sort((a, b) => b.level - a.level))
const depthMaxVolume = computed(() => Math.max(1, ...[
  ...(microstructure.value?.bids ?? []), ...(microstructure.value?.asks ?? []),
].map(item => item.volume)))

function money(value?: number) {
  return `¥${formatNumber(value, 2)}`
}
function signedMoney(value?: number) {
  if (value == null) return '—'
  return `${value >= 0 ? '+' : '−'}¥${formatNumber(Math.abs(value), 2)}`
}
function setError(cause: unknown, fallback: string) {
  error.value = cause instanceof Error ? cause.message : fallback
}
function updateSession(session: PaperSession) {
  if(disposed)return
  current.value = session
  const index = sessions.value.findIndex(item => item.id === session.id)
  if (index >= 0) sessions.value[index] = session
  else sessions.value.unshift(session)
}

async function selectSession(id: string) {
  if(disposed)return
  if (working.value||savingWorkflowTrial.value) return
  const generation = ++selectionGeneration
  selecting.value = true
  stopAutoplay()
  stopMicrostructure()
  showDeleteConfirm.value = false
  activeWorkflowTrial.value = null
  current.value = null
  error.value = ''
  try {
    const session = await api.paperSession(id)
    if (generation === selectionGeneration) current.value = session
  }
  catch (cause) { if (generation === selectionGeneration) setError(cause, '读取模拟账户失败') }
  finally { if (generation === selectionGeneration) {selecting.value = false;syncSessionRoute(true)} }
}

function applyHistoryRange() {
  const range = selectedHistory.value
  if (!range) return
  createForm.value.startDate = range.startDate
  createForm.value.endDate = range.endDate
}

async function createSession() {
  if (working.value || selecting.value) return
  if(!filteredSymbols.value.some(item=>item.symbol===createForm.value.symbol)){error.value='请先选择有可用数据的期货品种';return}
  if(createForm.value.mode==='HISTORICAL'&&!selectedHistory.value){error.value='所选品种尚无真实合约回放数据，请先选择已备齐数据的品种';return}
  if(createForm.value.strategyId==='WORKFLOW'&&!chosenWorkflow.value){error.value='请选择已发布的工作流版本';return}
  working.value = true
  error.value = ''
  try {
    const body = { ...createForm.value }
    if(body.strategyId==='WORKFLOW'&&chosenWorkflow.value?.engineVersion==='workflow-daily-v2'&&!body.workflowShadowId)throw new Error('请先选择该版本的空仓观察记录')
    if (body.mode === 'LIVE') {
      delete body.startDate
      delete body.endDate
      if(body.strategyId==='MANUAL')body.autoRoll=false
    }
    const created = await api.createPaperSession(body)
    updateSession(created)
    showCreate.value = false
    if(created.mode==='LIVE'&&created.strategyId==='MANUAL'&&!created.decisionGuarded&&!created.managedTraining) {
      try {updateSession(await api.selectPaperInstrument(created.id,created.currentContract))}
      catch(cause){error.value=`账户已创建，初始品种载入失败：${cause instanceof Error?cause.message:'请稍后重试'}。可在当前账户添加或切换品种。`}
    }
  } catch (cause) { setError(cause, '创建模拟账户失败') }
  finally { working.value = false }
}

async function placeOrder() {
  if (!current.value || working.value || selecting.value) return
  working.value = true
  error.value = ''
  try {
    const signature=JSON.stringify({session:current.value.id,...order.value,contract:current.value.currentContract,clientOrderId:undefined})
    if(!orderAttempt||orderAttempt.signature!==signature)orderAttempt={signature,id:requestId()}
    const payload: PlacePaperOrderRequest = {
      ...order.value,
      contract:current.value.currentContract,
      clientOrderId: orderAttempt.id,
      quantity: Math.max(1, Math.trunc(order.value.quantity)),
    }
    if (payload.orderType !== 'LIMIT') delete payload.limitPrice
    if (payload.orderType !== 'STOP') delete payload.stopPrice
    updateSession(await api.placePaperOrder(current.value.id, payload))
    orderAttempt=null
  } catch (cause) { setError(cause, '委托提交失败') }
  finally { working.value = false }
}

async function selectInstrument(symbol:string,close?:PaperPortfolioPosition) {
  const account=current.value
  if(!account||working.value||selecting.value||!canUsePortfolio.value)return
  working.value=true;error.value='';stopAutoplay()
  try {
    const selected=await api.selectPaperInstrument(account.id,symbol)
    if(disposed||current.value?.id!==account.id)return
    updateSession(selected)
    await nextTick()
    if(close) {
      const position=selected.positions?.find(p=>p.contract===close.contract)
      if(position?.lots) {
        order.value={clientOrderId:'',contract:position.contract,side:position.direction>0?'SELL':'BUY',offset:'CLOSE',orderType:'MARKET',quantity:position.lots}
        document.querySelector('.order-ticket')?.scrollIntoView?.({behavior:'smooth',block:'center'})
      }
    }
  } catch(cause){setError(cause,'切换品种失败，原持仓仍保留')}
  finally{working.value=false}
}

async function advance(steps = 1) {
  if (!current.value || working.value || selecting.value || reviewingReplay.value) return
  const id=current.value.id
  working.value = true
  error.value = ''
  try {
    const updated = await api.advancePaperSession(id, steps)
    if(current.value?.id!==id)return
    updateSession(updated)
    if (updated.status !== 'ACTIVE') stopAutoplay()
  } catch (cause) {
    stopAutoplay()
    setError(cause, '推进模拟时间失败')
  } finally { working.value = false }
}

function startAutoplay() {
  if (!current.value || current.value.status !== 'ACTIVE' || reviewingReplay.value) return
  autoplay.value = true
  window.clearInterval(autoplayTimer)
  autoplayTimer = window.setInterval(() => {if(!document.hidden)void advance(1)}, isHistorical.value?900:10000)
}
function stopAutoplay() {
  autoplay.value = false
  window.clearInterval(autoplayTimer)
  autoplayTimer = undefined
}
async function togglePaused() {
  if (!current.value || working.value || selecting.value) return
  working.value = true
  error.value = ''
  try {
    const updated = current.value.status === 'PAUSED'
      ? await api.resumePaperSession(current.value.id)
      : await api.pausePaperSession(current.value.id)
    updateSession(updated)
    if (updated.status !== 'ACTIVE') stopAutoplay()
  } catch (cause) { setError(cause, '状态切换失败') }
  finally { working.value = false }
}
async function cancelOrder(orderId: string) {
  if (!current.value || working.value || selecting.value) return
  working.value = true
  try { updateSession(await api.cancelPaperOrder(current.value.id, orderId)) }
  catch (cause) { setError(cause, '撤单失败') }
  finally { working.value = false }
}

function stopMicrostructure() {
  microGeneration += 1
  window.clearTimeout(microTimer)
  microTimer = undefined
  microLoading.value = false
}

async function refreshMicrostructure(generation: number, contract: string) {
  if (generation !== microGeneration) return
  microLoading.value = !microstructure.value
  try {
    const snapshot = await api.microstructure(contract)
    if (generation === microGeneration) {
      microstructure.value = snapshot
      microError.value = ''
    }
  } catch (cause) {
    if (generation === microGeneration) {
      microError.value = cause instanceof Error ? cause.message : '实时盘口暂不可用'
    }
  } finally {
    if (generation === microGeneration) {
      microLoading.value = false
      microTimer = window.setTimeout(() => void refreshMicrostructure(generation, contract), 1000)
    }
  }
}

function restartMicrostructure() {
  stopMicrostructure()
  microstructure.value = null
  microError.value = ''
  if (current.value?.mode !== 'LIVE') return
  const generation = microGeneration
  void refreshMicrostructure(generation, current.value.currentContract)
}

async function deleteSession() {
  if (!current.value || working.value || selecting.value) return
  const deletedId = current.value.id
  working.value = true
  error.value = ''
  stopAutoplay()
  stopMicrostructure()
  try {
    await api.deletePaperSession(deletedId)
    sessions.value = sessions.value.filter(item => item.id !== deletedId)
    showDeleteConfirm.value = false
    current.value = sessions.value.length ? await api.paperSession(sessions.value[0].id) : null
    if (!current.value) showCreate.value = true
  } catch (cause) { setError(cause, '删除试验失败') }
  finally { working.value = false }
}

watch(() => createForm.value.symbol, applyHistoryRange)
watch(()=>createForm.value.barSeconds,()=>{if(creatingMinute.value){createForm.value.strategyId='MANUAL';createForm.value.autoRoll=false}applyHistoryRange()})
watch(filteredSymbols,items=>{
  if(!items.some(item=>item.symbol===createForm.value.symbol))createForm.value.symbol=items[0]?.symbol??''
})
watch(()=>createForm.value.mode,()=>{
  if(createForm.value.mode==='LIVE'){
    if(maReplayVersions.value.some(v=>v.id===createForm.value.workflowVersionId))delete createForm.value.workflowVersionId
    createForm.value.barSeconds=86400
  }
  if(!availableSymbols.value.some(item=>item.symbol===createForm.value.symbol))
    createForm.value.symbol=availableSymbols.value[0]?.symbol??''
  applyHistoryRange()
})
watch([() => current.value?.id, () => current.value?.currentContract], () => {
  orderAttempt=null
  const value = current.value
  if (!value) return
  order.value = {clientOrderId: '', side: value.planGuard?.ownerVisible&&value.planGuard.side==='SHORT'?'SELL':'BUY', offset: 'OPEN', orderType: 'MARKET', quantity: 1,
    limitPrice: value.currentPrice, stopPrice: value.currentPrice}
})
watch([() => current.value?.id, () => current.value?.mode, () => current.value?.currentContract], restartMicrostructure)
watch(()=>current.value?.id,()=>{fillsPage.value=1;ordersPage.value=1;selectedFill.value=null;chartPeriod.value=current.value?.mode==='LIVE'?60:current.value?.barSeconds??60;chartView.value='intraday'})
watch([chartView,chartPeriod],()=>{if(isHistorical.value)stopAutoplay()})
watch(()=>[current.value?.id,current.value?.currentMarketTime,current.value?.currentBarIndex,current.value?.version,chartLimit.value,chartView.value,chartPeriod.value],()=>void refreshChart())
watch([current,fillsPage,ordersPage],()=>void refreshRecords())

async function initialize() {
  loading.value=true;presetsError.value=''
  try {
    const results = await Promise.allSettled([
      api.paperSessions(), api.backtestPresets(), api.replayStatus().catch(()=>{historyError.value='日线回放目录暂不可用。';return null}),
      api.intradayCatalog(),
    ])
    const loadedSessions=results[0].status==='fulfilled'?results[0].value:[]
    const loadedPresets=results[1].status==='fulfilled'?results[1].value:null
    const loadedHistory=results[2].status==='fulfilled'?results[2].value:null
    if(results[1].status==='rejected')presetsError.value='策略与品种目录暂不可用，已有账户可继续使用。'
    if(results[0].status==='rejected')setError(results[0].reason,'账户列表读取失败，请重试')
    sessions.value = loadedSessions
    presets.value = loadedPresets
    history.value = loadedHistory
    intraday.value=results[3].status==='fulfilled'?results[3].value:null
    if(!intraday.value?.symbols.length){createForm.value.barSeconds=86400;createForm.value.autoRoll=true}
    if(!availableSymbols.value.some(item=>item.symbol===createForm.value.symbol))
      createForm.value.symbol=availableSymbols.value[0]?.symbol??''
    applyHistoryRange()
    if(!route?.query.trial&&!activeWorkflowTrial.value&&!selecting.value){
      if(loadedSessions.length&&!current.value){
        const first=await api.paperSession(loadedSessions[0].id)
        if(!activeWorkflowTrial.value&&!selecting.value&&!current.value)current.value=first
      }else if(!loadedSessions.length&&!workflowTrials.value.length)showCreate.value=true
    }
  } catch (cause) { setError(cause, '模拟交易台初始化失败') }
  finally { loading.value = false }
}
onMounted(()=>{chartClockTimer=window.setInterval(()=>{liveNow.value=Date.now()},1000);document.addEventListener('visibilitychange',resumeChart)})
onMounted(()=>void loadWorkflowTrials())
onMounted(async()=>{const requestedSession=route?.query.session;const requestedTrial=route?.query.trial;await initialize();if(disposed)return;if(typeof requestedTrial==='string'){sessionRouteReady=true;await selectWorkflowTrial(requestedTrial);return}if(typeof requestedSession==='string'&&!activeWorkflowTrial.value)await selectSession(requestedSession);if(disposed)return;sessionRouteReady=true;syncSessionRoute();if(typeof route?.query.workflowVersion==='string'){
 showCreate.value=true;createForm.value.workflowVersionId=route.query.workflowVersion;createForm.value.strategyId='WORKFLOW'
 if(typeof route.query.symbol==='string'){const key=route.query.symbol.toUpperCase().replace(/0$/,'M');const matching=availableSymbols.value.find(s=>s.symbol.toUpperCase().replace(/0$/,'M')===key);if(matching){createForm.value.symbol=matching.symbol;applyHistoryRange()}}
 if(typeof route.query.shadow==='string'){createForm.value.workflowShadowId=route.query.shadow;createForm.value.mode='HISTORICAL';if(typeof route.query.startDate==='string')createForm.value.startDate=route.query.startDate}
} else if(requestedAutomation.value){
 if(!current.value&&hasPermission('paper.write')&&hasPermission('market.read'))prepareAutomationAccount()
 await nextTick()
 document.getElementById('paper-automation')?.scrollIntoView?.({block:'start'})
}})
onUnmounted(() => {
  disposed=true;decisionGeneration++
  selectionGeneration++
  chartGeneration++;recordsGeneration++
  window.clearTimeout(liveChartTimer);window.clearInterval(chartClockTimer);document.removeEventListener('visibilitychange',resumeChart)
  stopAutoplay()
  stopMicrostructure()
})
</script>

<template>
  <div class="paper-page">
    <div class="experiment-actions">
      <button class="new-session primary" type="button" :aria-expanded="showCreate" aria-controls="create-experiment"
        :disabled="working||savingWorkflowTrial" @click="openCreate"><Plus :size="16" />新建试验</button>
      <small class="universe-count" v-if="history||intraday">日线 {{history?.totalSymbols??0}} 个品种 · 分时 {{intraday?.symbols.length??0}} 个合约</small>
    </div>
    <p v-if="decisionSource?.caseId"><RouterLink :to="{path:'/paper/decisions/'+decisionSource.caseId,query:{plan:decisionSource.planId}}">返回计划 v{{decisionSource.version}} 与私人复盘 ↗</RouterLink> · 本账户为手动模拟，下单与新增开仓成交受冻结计划约束。</p>
    <section v-if="current?.planGuard?.enabled" class="plan-guard" aria-label="计划开仓约束">
      <strong>计划开仓约束<span v-if="current.planGuard.ownerVisible"> · v{{current.planGuard.version}}</span></strong>
      <p>{{current.planGuard.message}}</p>
      <p v-if="current.planGuard.ownerVisible">{{current.planGuard.side==='LONG'?'仅多头开仓':'仅空头开仓'}} · 持仓与开仓挂单合计最多 {{current.planGuard.lots}} 手 · 风险预算 {{money(current.planGuard.budget??0)}}。</p>
      <p>保护价用于开仓风险试算，不会自动止损或止盈。</p>
      <details><summary>预算口径与成交边界</summary><p v-if="current.planGuard.ownerVisible">已发生亏损和手续费持续占用预算，盈利不冲抵已发生亏损。</p><p>跳空、滑点可能使实际损失超过预算。开仓挂单需计划本人刷新且通过重新核验后才可成交，平仓与撤单沿用原权限。</p></details>
    </section>
    <section class="trust-strip">
      <div><ShieldCheck :size="17" /><strong>仅模拟，不连接实盘交易账户</strong></div>
      <span>行情与历史路径来自 TqSdk；成交、手续费、滑点、保证金和换月独立记账。</span>
    </section>

    <p v-if="isSimple" class="practice-intro">第一次使用？先了解保证金、做多与做空，再用虚拟资金创建练习；历史回放可逐步查看每次操作的结果。<RouterLink to="/learn#example">查看金额与风险示例 ↗</RouterLink></p>

    <div v-if="error" class="error-banner" role="alert">
      <AlertTriangle :size="17" /><span>{{ error }}</span>
      <button type="button" aria-label="关闭错误提示" @click="error = ''"><X :size="15" /></button>
    </div>
    <p v-if="presetsError" class="practice-intro" role="alert">{{presetsError}} <button type="button" @click="initialize">重新读取目录</button></p>

    <p v-if="workflowTrialsError" class="practice-intro" role="alert">{{workflowTrialsError}} <button type="button" @click="loadWorkflowTrials">重试</button></p>

    <div class="experiment-workspace">
      <section class="session-rail">
        <div class="session-tabs" role="tablist" aria-label="模拟账户">
          <button
            v-for="item in pagedSessions" :key="item.id" type="button" role="tab"
            :aria-selected="(item.kind==='workflow'?activeWorkflowTrial?.trial.id:current?.id) === item.id"
            :class="{ active: (item.kind==='workflow'?activeWorkflowTrial?.trial.id:current?.id) === item.id }"
            :disabled="working||savingWorkflowTrial"
            @click="item.kind==='workflow'?selectWorkflowTrial(item.id):selectSession(item.id)"
          >
            <span class="status-dot" :class="item.status.toLowerCase()" />
            <span><strong>{{ item.name }}</strong><small>{{instrumentLabel(item.symbol)}} · {{ item.kind==='workflow' ? '策略回放' : item.mode==='LIVE' ? '实时' : '历史' }}</small></span>
          </button>
        </div>
      </section>
      <PaperStrategyPanel v-if="current" :current="current" :presets="presets" :sessions="sessions" @compare="compareStrategy" />
      <section v-if="requestedAutomation&&!canSeeAutomation" id="paper-automation" class="create-panel" aria-label="配置量化模拟盘">
        <h2>{{requestedAutomationName}} · 模拟盘</h2>
        <p>在上方选择一个普通实时模拟账户，或创建一个新账户后切换到要执行的实际交割合约。</p>
        <button v-if="hasPermission('paper.write')&&hasPermission('market.read')" class="new-session" type="button" @click="prepareAutomationAccount"><Plus :size="16" />配置实时模拟账户</button>
      </section>

      <Pagination v-if="sessionTotal>6" v-model:page="sessionPage" :page-size="6" :total="sessionTotal" label="模拟账户分页" />
      <div v-if="loading" class="loading-state" role="status"><LoaderCircle class="spin" :size="24" />载入模拟账本与历史品种…</div>
      <section v-if="showCreate" id="create-experiment" class="create-panel" aria-labelledby="create-experiment-title">
        <div class="panel-heading"><h2 id="create-experiment-title">新建试验</h2><button type="button" aria-label="关闭新建试验" :disabled="savingWorkflowTrial" @click="showCreate = false"><X :size="17" /></button></div>
        <div class="mode-bar">
          <label class="mode-select"><span>时间模式</span><select v-model="createForm.mode" :disabled="savingWorkflowTrial"><option value="HISTORICAL">历史时点回放</option><option value="LIVE" :disabled="chosenWorkflow?.engineVersion==='workflow-daily-v2'">实时仿真</option></select></label>
          <div class="mode-tabs" role="group" aria-label="切换时间模式">
            <button type="button" :class="{active: createForm.mode === 'LIVE'}" :disabled="savingWorkflowTrial||chosenWorkflow?.engineVersion==='workflow-daily-v2'" @click="createForm.mode = 'LIVE'">⚡ 实时仿真（全量87个品种）</button>
            <button type="button" :class="{active: createForm.mode === 'HISTORICAL'}" @click="createForm.mode = 'HISTORICAL'">⏳ 历史时点回放</button>
          </div>
        </div>
        <div class="create-strategy-picker">
          <label><span>模拟策略</span>
            <select ref="strategyPicker" v-model="createStrategySelection" aria-label="模拟策略" :disabled="savingWorkflowTrial">
              <option value="MANUAL">手动交易 · 自己提交委托</option>
              <option value="WORKFLOW">已发布工作流</option>
              <option v-for="item in presets?.strategies??[]" :key="item.id" :value="item.id">{{item.name}}</option>
            </select>
          </label>
          <p v-if="createForm.mode==='HISTORICAL'&&createStrategySelection==='MANUAL'">分钟回放默认手动交易。要让程序自动执行，请在这里选择策略。</p>
          <label v-if="createForm.strategyId==='WORKFLOW'"><span>已发布的工作流版本</span>
            <select v-model="createForm.workflowVersionId" aria-label="模拟工作流版本" :disabled="savingWorkflowTrial||workflowLoading||!hasWorkflowVersions">
              <option :value="undefined">{{workflowLoading?'正在读取版本…':'请选择已发布版本'}}</option>
              <optgroup v-if="createForm.mode==='HISTORICAL'&&maReplayVersions.length" label="日线定方向 · 15 分钟确认">
                <option v-for="version in maReplayVersions" :key="version.id" :value="version.id">{{version.name}} · v{{version.version}}</option>
              </optgroup>
              <optgroup v-if="workflowVersions.length" label="日线自动策略">
                <option v-for="version in workflowVersions" :key="version.id" :value="version.id">{{version.name}} · v{{version.version}}</option>
              </optgroup>
            </select>
          </label>
          <template v-if="createForm.strategyId==='WORKFLOW'">
            <p v-if="workflowError" role="alert">{{workflowError}} <button type="button" @click="loadWorkflows">重试</button></p>
            <p v-else-if="!workflowLoading&&!hasWorkflowVersions">此模式下暂无可用版本。可到<RouterLink to="/strategy/workflows">策略工作流</RouterLink>的「发布与模拟」发布策略。</p>
          </template>
          <p v-if="createForm.mode==='HISTORICAL'&&createStrategySelection!=='MANUAL'&&!maReplayVersion&&(createForm.strategyId!=='WORKFLOW'||chosenWorkflow)">此策略使用已完成日线。创建账户后，点击「播放」可自动推进并执行策略。</p>
        </div>
        <section v-if="createForm.strategyId==='WORKFLOW'&&maReplayVersion" class="create-ma-replay" aria-label="从已发布的 15 分钟策略回放">
          <MaTrendWorkflowReplay :key="maReplayVersion.id" :version="maReplayVersion" create-trial
            @saving-trial="savingWorkflowTrial=$event" @created-trial="activateWorkflowTrial" />
        </section>
        <form v-else-if="createForm.strategyId!=='WORKFLOW'||chosenWorkflow" @submit.prevent="createSession">
        <section class="symbol-discovery" aria-label="模拟品种筛选">
          <div class="symbol-discovery-head"><strong>{{createForm.mode==='HISTORICAL'?'可回放品种':'实时仿真品种'}} {{availableSymbols.length}} / {{presets?.symbols.length??0}}</strong><button type="button" :disabled="historyRefreshing" @click="refreshHistory"><RefreshCw :size="13" :class="{spin:historyRefreshing}" />{{historyRefreshing?'刷新中…':'刷新数据目录'}}</button></div>
          <label><span>搜索品种</span><input v-model="symbolSearch" type="search" placeholder="名称、代码、交易所或板块，如 白银 / AG / 化工" /></label>
          <div class="sector-filters" role="group" aria-label="按板块筛选品种"><button v-for="sector in sectors" :key="sector" type="button" :aria-pressed="sectorFilter===sector" @click="sectorFilter=sector">{{sector}}</button></div>
          <p aria-live="polite">筛选结果 {{filteredSymbols.length}} 个<span v-if="!filteredSymbols.length">，请调整关键词或板块。</span><template v-if="createForm.mode==='HISTORICAL'"> · 其余 {{Math.max(0,(presets?.symbols.length??0)-availableSymbols.length)}} 个尚缺完整执行数据，后台正在持续下载补齐，刷新即可载入。</template><template v-else> · 包含五大交易所全部 87 个活跃主力期货，已全量支持实时仿真。</template></p>
        </section>
        <div class="form-grid">
          <label v-if="createForm.mode==='HISTORICAL'"><span>K线周期</span><select v-model.number="createForm.barSeconds" aria-label="回放K线周期" :disabled="createForm.strategyId!=='MANUAL'"><option :value="60">1分钟 · 分时手动模拟</option><option :value="180">3分钟</option><option :value="300">5分钟</option><option :value="900">15分钟</option><option :value="86400">日线</option></select></label>
          <template v-if="creatingMinute"><label><span>固定止损（跳，0为关闭）</span><input v-model.number="createForm.stopLossTicks" aria-label="固定止损跳数" type="number" min="0" max="10000" required /></label><label><span>日内交易</span><input v-model="createForm.intradayOnly" type="checkbox" />每个交易日收盘清仓</label><p class="practice-intro">真实分钟行情，逐根推进；手动决定买卖，可为每笔成交记录心得。止损可选，无自动止盈、无自动反手。手续费与滑点计入账户。</p></template>
          <label><span>试验名称</span><input v-model.trim="createForm.name" maxlength="80" required /></label>
          <template v-if="chosenWorkflow"><label v-if="chosenWorkflow.engineVersion==='workflow-daily-v2'"><span>空仓观察记录（仅历史模拟）</span><select v-model="createForm.workflowShadowId" aria-label="缠论观察记录" required><option :value="undefined">先在工作流页归档空仓观察</option><option v-for="item in workflowShadows.filter(s=>s.direction===0&&s.historyCount>=50)" :key="item.id" :value="item.id">{{formatTradingDate(item.signalTime)}} · {{instrumentLabel(item.symbol)}}</option></select></label><p v-if="workflowShadowError" role="alert">{{workflowShadowError}}</p><p class="practice-intro">使用固定发布版本的规则、手数与保护参数。<RouterLink to="/strategy/workflows">编辑工作流 ↗</RouterLink></p></template>
          <template v-if="createForm.strategyId!=='MANUAL'"><label><span>策略每次开仓手数</span><input v-model.number="createForm.strategyLots" :disabled="createForm.strategyId==='WORKFLOW'" aria-label="策略开仓手数" type="number" min="1" max="1000000" step="1" required /></label><template v-if="createForm.strategyId!=='BUY_AND_HOLD'"><label><span>保护止损（ATR倍数）</span><input v-model.number="createForm.stopLossAtr" :disabled="createForm.strategyId==='WORKFLOW'" type="number" min="0.1" max="20" step="0.1" required /></label><label><span>保护止盈（ATR倍数）</span><input v-model.number="createForm.takeProfitAtr" :disabled="createForm.strategyId==='WORKFLOW'" type="number" min="0.1" max="50" step="0.1" required /></label></template><p class="practice-intro">策略在单步、播放或实时刷新时自动生成模拟委托，参数在创建时固定。请用相同品种、区间和资金建立不同策略的对照试验。</p></template>
          <label><span>期货品种</span><select v-model="createForm.symbol" aria-label="期货品种" required :disabled="!filteredSymbols.length"><optgroup v-for="group in symbolGroups" :key="group.exchange" :label="exchangeNames[group.exchange]??group.exchange"><option v-for="item in group.items" :key="item.symbol" :value="item.symbol">{{instrumentLabel(item.symbol)}} · {{ item.name }}</option></optgroup></select></label>
          <label><span>初始资金</span><input v-model.number="createForm.initialCash" type="number" min="1000" step="1000" required /></label>
          <label v-if="createForm.mode === 'HISTORICAL'"><span>开始日期</span><input v-model="createForm.startDate" type="date" :min="selectedHistory?.startDate" :max="selectedHistory?.endDate" required /></label>
          <label v-if="createForm.mode === 'HISTORICAL'"><span>结束日期</span><input v-model="createForm.endDate" type="date" :min="selectedHistory?.startDate" :max="selectedHistory?.endDate" required /></label>
          <label><span>保证金率</span><input v-model.number="createForm.marginRate" type="number" min="0.01" max="1" step="0.01" /></label>
          <label><span>滑点（tick）</span><input v-model.number="createForm.slippageTicks" type="number" min="0" max="100" step="0.5" /></label>
        </div>
        <label v-if="!creatingMinute&&!(createForm.mode==='LIVE'&&createForm.strategyId==='MANUAL')" class="check"><input v-model="createForm.autoRoll" type="checkbox" /><span><strong>主力切换时自动移仓</strong><small>使用新旧合约真实价格分别平仓、开仓，并计入双边成本</small></span></label>
        <p v-if="createForm.mode==='HISTORICAL'" class="practice-intro">历史回放仅提供已备齐真实交割合约及换月数据的品种，日期范围以这些数据为准。<span v-if="historyError" role="alert">{{historyError}}</span><span v-else-if="!availableSymbols.length">暂无可用回放数据，请先拉取真实合约历史数据。</span></p>
        <p v-if="createForm.mode==='LIVE'" class="practice-intro">实时账户可在休市时准备；不依赖完整历史回放档案。成交需要有效近时行情，休市或过期时仅显示真实观测与估值。</p>
        <div class="create-actions"><span v-if="selectedHistory&&createForm.mode==='HISTORICAL'">可用真实合约数据：{{ selectedHistory.startDate }} — {{ selectedHistory.endDate }} · {{ selectedHistory.totalBars }} 条</span><button class="primary" :disabled="working||!filteredSymbols.length||(createForm.mode==='HISTORICAL'&&!selectedHistory)"><LoaderCircle v-if="working" class="spin" :size="15" />创建账户</button></div>
        </form>
      </section>

      <section v-if="activeWorkflowTrial" class="create-panel" aria-label="已保存的历史试验">
        <h2>{{activeWorkflowTrial.trial.name}}</h2>
        <MaTrendWorkflowReplay :key="activeWorkflowTrial.trial.id" :version="activeWorkflowTrial.version"
          :versions="maReplayVersions" :saved-trial="activeWorkflowTrial" />
      </section>
      <p v-if="current?.managedTraining" class="practice-intro">此账户属于个人策略受控训练，此处可查看行情、流水和暂停/恢复。请到<RouterLink :to="{path:'/personal',query:{run:current.id}}">个人总结继续决策与复盘 →</RouterLink>，保护规则不能从普通委托绕过。</p>
      <PaperPortfolioPanel v-if="current&&canUsePortfolio" :session="current" :presets="presets" :busy="working||selecting" @select="selectInstrument" @close="position=>selectInstrument(position.contract,position)" />
      <PaperAutomationPanel v-if="current&&canSeeAutomation" :key="current.id" :session="current" :presets="presets" :busy="working||selecting" :initial-strategy="requestedAutomation" :selected-trinity="requestedTrinity" :trinity-launch-missing="trinityLaunchMissing" @locked="automationLocked=$event" @refresh="refreshAutomationAccount" />
      <div v-if="current" class="terminal-grid" :class="{managed:current.managedTraining,'strategy-terminal':isStrategy}">
        <main class="ledger">
          <header class="market-header">
            <div>
              <div class="market-title"><span class="mode-badge">{{ current.mode === 'LIVE' ? 'LIVE PAPER' : 'HISTORICAL' }}</span><span class="state-badge" :class="current.status.toLowerCase()">{{ current.status }}</span></div>
              <h2>{{ current.currentContract }} <strong>{{ formatNumber(displayPrice, 2) }}</strong></h2>
              <p v-if="isLive"><Database :size="14" />{{chart?.source??'天勤实时行情'}} · 行情时间 {{chart?.dataTimestamp?formatTime(chart.dataTimestamp):'尚未收到有效行情'}}</p>
              <p v-else><Database :size="14" />{{ current.dataSource }} · {{ isHistorical&&!isMinute?formatTradingDate(current.currentMarketTime)+' · 该交易日日线已完成':new Date(current.currentMarketTime).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}) }}</p>
            </div>
            <div class="playback">
              <button v-if="isHistorical" type="button" title="推进一根K线" :disabled="working || reviewingReplay || current.status !== 'ACTIVE'||current.managedTraining" @click="advance(1)"><StepForward :size="17" />单步</button>
              <button v-if="isHistorical" type="button" title="推进五根K线" :disabled="working || reviewingReplay || current.status !== 'ACTIVE'||current.managedTraining" @click="advance(5)"><FastForward :size="17" />5步</button>
              <button v-if="isHistorical" type="button" :disabled="current.status !== 'ACTIVE'||current.managedTraining||reviewingReplay" @click="autoplay ? stopAutoplay() : startAutoplay()"><Pause v-if="autoplay" :size="17" /><Play v-else :size="17" />{{ autoplay ? '停止' : '播放' }}</button>
              <button v-else type="button" :disabled="working" @click="advance(1)"><RefreshCw :class="{ spin: working }" :size="17" />刷新账户估值</button>
              <button v-if="!isHistorical&&isStrategy" type="button" :disabled="current.status!=='ACTIVE'" @click="autoplay?stopAutoplay():startAutoplay()"><Pause v-if="autoplay" :size="17"/><Play v-else :size="17"/>{{autoplay?'停止策略监测':'启动策略监测'}}</button>
              <button v-if="['ACTIVE', 'PAUSED'].includes(current.status)" type="button" @click="togglePaused"><Play v-if="current.status === 'PAUSED'" :size="17" /><CirclePause v-else :size="17" />{{ current.status === 'PAUSED' ? '恢复' : '暂停' }}</button>
              <button v-if="!current.managedTraining" class="delete-trigger" type="button" title="删除当前试验" @click="showDeleteConfirm = true"><Trash2 :size="16" />删除</button>
            </div>
          </header>
          <ReplayReviewPanel v-if="reviewContext" :key="reviewContext.id" :context="reviewContext"
            :at="current.currentMarketTime" :fills="reviewFills" :busy="working||selecting"
            :preset="current.strategyId" @pause="stopAutoplay" @editing="reviewingReplay=$event" />

          <div v-if="isHistorical" class="timeline"><span :style="{ width: `${progressPct}%` }" /><div><small>{{ current.currentBarIndex + 1 }} / {{ current.totalBars }}</small><small>{{ progressPct.toFixed(1) }}%</small></div></div>
          <section class="paper-chart" aria-label="模拟交易K线">
            <div class="section-title"><div><span>{{isLive?'LIVE MARKET':'PRICE CONTEXT'}}</span><h3>{{canSwitchChart?(chartView==='intraday'?(isLive?'实时分时 · 当前合约':'当日分时 · 手动模拟'):(chartPeriods.find(p=>p.seconds===chartPeriod)?.label??'K线')+(isLive?' · 实时行情':' · 手动回放')):'回放时点 K 线'}}</h3></div><label v-if="!canSwitchChart||chartView==='candle'">显示数量 <select v-model.number="chartLimit" aria-label="模拟K线数量"><option :value="120">120 根</option><option :value="240">240 根</option><option :value="720">720 根</option></select></label><button type="button" :disabled="chartLoading" @click="refreshChart">刷新图表</button></div>
            <p v-if="chartLoading" role="status">{{isLive?'正在订阅当前合约实时行情…':'正在读取当前时点已完成的K线…'}}</p><p v-if="chartError" role="alert">{{chartError}}</p>
            <div v-if="canSwitchChart" class="replay-chart-controls"><div role="group" aria-label="模拟图表类型"><button type="button" :aria-pressed="chartView==='intraday'" @click="chartView='intraday'">分时图</button><button type="button" :aria-pressed="chartView==='candle'" @click="chartView='candle'">K线图</button></div><label v-if="chartView==='candle'">K线周期 <select v-model.number="chartPeriod" aria-label="图表K线周期"><option v-for="p in chartPeriods" :key="p.seconds" :value="p.seconds">{{p.label}}</option></select></label><small>{{isLive?'行情自动刷新 · 图表刷新不提交委托':'每步推进 '+(current.barSeconds??60)/60+' 分钟 · 切换图表不改变账户'}}</small></div>
            <p v-if="isLive" class="live-chart-status" :class="{fresh:liveFresh}" aria-label="实时行情状态"><strong>{{liveStatus}}</strong><span>行情时间 {{chart?.dataTimestamp?formatTime(chart.dataTimestamp):'—'}} · {{current.currentContract}}</span><span v-if="chart?.lastBarProvisional">末根K线形成中，随行情更新</span></p>
            <label class="dkx-toggle" title="MID=(3×收盘+开盘+最高+最低)/6；DKX为最近20根MID加权均值，权重20至1；MADKX为DKX的10周期均值。"><input v-model="showDkx" type="checkbox" aria-label="显示 DKX 指标" /> DKX(20) / MADKX(10)<small>{{canSwitchChart&&chartView==='intraday'?'按1分钟计算':'按所选K线周期计算'}}</small></label>
            <PaperIntradayChart v-if="canSwitchChart&&chartView==='intraday'&&chart" :points="chartPoints" :fills="chart.fills??[]" :as-of="chart.asOf" :show-dkx="showDkx" :live="isLive" :trading-day="isLive?chart.displayTradingDate??undefined:undefined" :trading-sessions="chart.tradingSessions??undefined" @trade="editFill" />
            <TongdaxinChart v-else-if="chartPoints.length" :key="current.id+'-'+chartPeriod+'-'+chartView" v-model:show-sub-chart="showSubChart" :points="chartPoints" :show-dkx="showDkx" :trades="chartExecutions.trades" :symbol="current.symbol" :display-name="current.currentContract" :height="440" :preserve-viewport-on-append="isLive" :time-label-mode="canSwitchChart&&chartPeriod!==86400?'datetime':'date'" default-theme="light" default-sub-chart="vol" />
            <p v-else-if="chart&&!chartLoading">{{isLive?'实时K线尚未就绪，正在自动重试。':'此时点暂无可展示的已完成K线。'}}</p>
            <p v-if="isMinute" class="chart-note">{{current.stopLossTicks?'固定止损 '+current.stopLossTicks+' 跳':'固定止损已关闭'}} · {{current.intradayOnly?'交易日收盘清仓':'允许跨交易日持仓'}} · 模拟手续费每边至少 {{money(current.commissionPerLot)}}/手，按档案假设或账户费率计算值取较大者，另计滑点。</p>
            <p v-if="isMinute&&chart?.dailyContext" class="chart-note">已完成日线MACD · DIF {{formatNumber(chart.dailyContext.dif,3)}} / DEA {{formatNumber(chart.dailyContext.dea,3)}} · {{chart.dailyContext.dif>chart.dailyContext.dea?'多头方向':'空头方向'}}（仅作手动判断参考）</p><p v-if="chart" class="chart-note">买卖点表示实际模拟成交（含滑点），不代表策略预告信号。买开多 / 买平空，卖开空 / 卖平多；点击标记查看成交价和原因。同根多笔合并展示，拖动或缩放可查看更早成交。</p>
            <details v-if="chartExecutions.unplaced.length" class="unplaced-trades"><summary>{{chartExecutions.unplaced.length}} 笔成交暂无对应合约日线（未完成交易日或换月另一腿），未标到其他 K 线上</summary><p v-for="fill in chartExecutions.unplaced" :key="fill.id">{{formatTime(fill.marketTime)}} · {{instrumentLabel(fill.contract)}} · {{fill.side==='BUY'?'买':'卖'}}{{fill.offset==='OPEN'?'开':'平'}} {{fill.quantity}} 手 @ {{formatNumber(fill.fillPrice)}} · {{fill.reason}}</p></details>
            <p v-if="chart" class="chart-note">{{isHistorical&&!isMinute?'回放交易日 '+formatTradingDate(chart.asOf)+'（该日线已完成）':'读取于 '+new Date(chart.asOf).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}} · {{chart.bars.length}} 根 · {{chart.source}}。{{chart.message}}<span v-if="isHistorical&&!isMinute"> 日期为交易日标签，按该日收盘后观察、下一根日线撮合，不表示盘中逐笔回放。</span><span v-if="isHistorical&&chart.contextStatus!=='READY'"> 开户前背景数据暂不可用。</span></p>
            <p v-if="isLive" class="chart-note">账户估值时间 {{formatTime(current.currentMarketTime)}}；图表独立更新行情，“刷新账户估值”沿用现有撮合和估值规则。</p>
            <details v-if="chart?.bars.length"><summary>核对最新行情与合约</summary><p>{{instrumentLabel(chart.bars.at(-1)?.contract)}} · {{chart.bars.at(-1)?.timestamp}} · 开 {{chart.bars.at(-1)?.open}} / 高 {{chart.bars.at(-1)?.high}} / 低 {{chart.bars.at(-1)?.low}} / 收 {{chart.bars.at(-1)?.close}}</p></details>
          </section>


          <section class="metrics">
            <article><span><WalletCards :size="15" />账户权益</span><strong>{{ money(current.equity) }}</strong><small :class="returnPct >= 0 ? 'up' : 'down'">{{ returnPct >= 0 ? '+' : '' }}{{ returnPct.toFixed(2) }}%</small></article>
            <article><span><Gauge :size="15" />可用资金</span><strong>{{ money(availableCash) }}</strong><small>全部持仓占用 {{ money(totalMargin) }}<template v-if="current.reservedCash"> · 挂单预留 {{money(current.reservedCash)}}</template></small></article>
            <article><span><Activity :size="15" />浮动盈亏</span><strong :class="totalUnrealized >= 0 ? 'up' : 'down'">{{ signedMoney(totalUnrealized) }}</strong><small>已实现 {{ signedMoney(current.realizedPnl) }}</small></article>
            <article><span><RotateCcw :size="15" />交易成本</span><strong>{{ money(current.commissionPaid + current.slippagePaid) }}</strong><small>手续费 + 滑点</small></article>
          </section>

          <section v-if="current.mode === 'LIVE'" class="microstructure-section">
            <div class="section-title micro-title">
              <div><span>LIVE MICROSTRUCTURE</span><h3>五档盘口与成交明细</h3></div>
              <small v-if="microstructure"><i :class="microstructure.dataStatus.toLowerCase()" />{{ microstructure.source }} · {{ formatTime(microstructure.dataTimestamp) }}</small>
              <small v-else><LoaderCircle v-if="microLoading" class="spin" :size="13" />{{ microError || '正在订阅天勤实时盘口…' }}</small>
            </div>
            <div class="micro-grid">
              <article class="depth-panel">
                <header><span>档位</span><span>价格</span><span>挂单量</span></header>
                <div v-for="level in asksDescending" :key="`ask-${level.level}`" class="depth-row ask">
                  <i :style="{ width: `${level.volume / depthMaxVolume * 100}%` }" />
                  <span>卖{{ level.level }}</span><strong>{{ level.price == null ? '—' : formatNumber(level.price, 2) }}</strong><b>{{ level.volume || '—' }}</b>
                </div>
                <div class="last-price"><span>最新</span><strong>{{ formatNumber(microstructure?.lastPrice, 2) }}</strong><small>{{ current.currentContract }}</small></div>
                <div v-for="level in microstructure?.bids ?? []" :key="`bid-${level.level}`" class="depth-row bid">
                  <i :style="{ width: `${level.volume / depthMaxVolume * 100}%` }" />
                  <span>买{{ level.level }}</span><strong>{{ level.price == null ? '—' : formatNumber(level.price, 2) }}</strong><b>{{ level.volume || '—' }}</b>
                </div>
                <div v-if="!microstructure" class="micro-placeholder">{{ microError || '等待第一帧真实盘口' }}</div>
              </article>
              <article class="tape-panel">
                <header><span>时间</span><span>价格</span><span>成交量</span><span>增仓</span></header>
                <div class="tape-scroll">
                  <div v-for="trade in microstructure?.trades ?? []" :key="`${trade.id}-${trade.timestamp}`" class="tape-row" :class="trade.side.toLowerCase()">
                    <time>{{ new Date(trade.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) }}</time>
                    <strong>{{ formatNumber(trade.price, 2) }}</strong>
                    <b>{{ trade.volume }}</b>
                    <span :class="trade.openInterestChange >= 0 ? 'up' : 'down'">{{ trade.openInterestChange > 0 ? '+' : '' }}{{ trade.openInterestChange }}</span>
                  </div>
                  <div v-if="microstructure && !microstructure.trades.length" class="micro-placeholder">当前时段尚无新增成交</div>
                  <div v-else-if="!microstructure" class="micro-placeholder">逐笔成交将在订阅完成后出现</div>
                </div>
              </article>
            </div>
            <p class="micro-footnote">成交方向依据该 Tick 成交价相对当时买一/卖一推断；无法可靠判断时显示为中性。所有空档均保持为空，不补造价格。</p>
          </section>

          <section v-else class="historical-depth-note">
            <Database :size="16" /><div><strong>历史模式不伪造五档盘口</strong><span>历史交易使用实际合约K线；实时五档和逐笔仅在实时仿真账户中提供。</span></div>
          </section>

          <section class="position-card">
            <div class="section-title"><div><span>POSITION</span><h3>{{current.multiInstrument?'所选合约持仓':'当前持仓'}}</h3></div><small>合约乘数 {{ current.volumeMultiple }} · 最小变动 {{ current.priceTick }}</small></div>
            <div v-if="current.position.lots" class="position-row">
              <span class="direction" :class="current.position.direction > 0 ? 'long' : 'short'">{{ current.position.direction > 0 ? '多' : '空' }}</span>
              <strong>{{instrumentLabel(current.position.contract)}}</strong><span>{{ current.position.lots }} 手</span><span>均价 {{ formatNumber(current.position.averagePrice, 2) }}</span><span>市价 {{ formatNumber(current.currentPrice, 2) }}</span><b :class="current.position.unrealizedPnl >= 0 ? 'up' : 'down'">{{ signedMoney(current.position.unrealizedPnl) }}</b>
            </div>
            <div v-else class="empty-line">当前无持仓。委托在真实行情路径上按撮合规则执行。</div>
          </section>

          <section class="records">
            <div class="section-title"><div><span>EXECUTIONS</span><h3>成交与换月流水</h3></div><small>按时间倒序 · 每页20条</small></div>
            <div class="table-wrap"><table><thead><tr><th>时间</th><th>事件</th><th>合约</th><th>方向</th><th>手数</th><th>行情价</th><th>成交价</th><th>费用</th><th>已实现盈亏</th><th>心得</th></tr></thead>
              <tbody><tr v-for="fill in fillRecords?.items??current.fills.slice(0,20)" :key="fill.id"><td>{{ formatTime(fill.marketTime) }}</td><td><span class="event-tag" :class="{ roll: fill.eventType === 'ROLL' }">{{ fill.eventType === 'ROLL' ? '换月' : '成交' }}</span></td><td>{{instrumentLabel(fill.contract)}}</td><td :class="fill.side === 'BUY' ? 'up' : 'down'">{{ fill.side === 'BUY' ? '买' : '卖' }} / {{ fill.offset === 'OPEN' ? '开' : '平' }}</td><td>{{ fill.quantity }}</td><td>{{ formatNumber(fill.marketPrice, 2) }}</td><td>{{ formatNumber(fill.fillPrice, 2) }}</td><td>{{ money(fill.fee + fill.slippageCost) }}</td><td :class="fill.realizedPnl >= 0 ? 'up' : 'down'">{{ signedMoney(fill.realizedPnl) }}</td><td><button type="button" @click="editFill(fill)">记录心得</button></td></tr>
              <tr v-if="!(fillRecords?.items??current.fills).length"><td colspan="10" class="empty-cell">尚无成交记录</td></tr></tbody></table></div>
            <Pagination v-if="fillRecords" v-model:page="fillsPage" :page-size="20" :total="fillRecords.total" label="成交流水分页" />
            <p v-if="recordsError" role="alert">{{recordsError}} <button type="button" @click="refreshRecords">重试流水</button></p>
            <PaperFillJournal v-if="selectedFill" :key="current.id" :session-id="current.id" :fill="selectedFill" />
            <details class="order-history"><summary>全部委托记录</summary><div class="table-wrap"><table>
              <thead><tr><th>提交时间</th><th>实际合约</th><th>方向</th><th>类型</th><th>手数 / 剩余</th><th>状态</th><th>说明</th></tr></thead>
              <tbody><tr v-for="item in orderRecords?.items??[]" :key="item.id"><td>{{formatTime(item.createdAt)}}</td><td>{{item.contract??'—'}}</td><td>{{item.side}} / {{item.offset}}</td><td>{{item.orderType}}</td><td>{{item.quantity}} / {{item.remainingQuantity}}</td><td>{{item.status}}</td><td>{{item.rejectionReason||'—'}} <RouterLink v-if="current.workflowShadowId&&item.clientOrderId.startsWith('strategy:')" :to="{path:'/strategy/workflows',query:{session:current.id,decision:item.clientOrderId.slice(9)}}">信号图表与节点 ↗</RouterLink> <button v-if="['PENDING','PARTIAL'].includes(item.status)" type="button" @click="cancelOrder(item.id)">撤单</button></td></tr></tbody>
            </table></div><Pagination v-if="orderRecords" v-model:page="ordersPage" :page-size="20" :total="orderRecords.total" label="委托记录分页" /></details>
          </section>
        </main>

        <aside v-if="!current.managedTraining&&!isStrategy" class="order-ticket">
          <div class="ticket-head"><div><span>ORDER TICKET</span><h3>模拟下单</h3></div><Clock3 :size="18" /></div>
          <div class="segmented"><button type="button" :class="{ selected: order.side === 'BUY' }" @click="order.side = 'BUY'"><ArrowUp :size="15" />买入</button><button type="button" :class="{ selected: order.side === 'SELL' }" @click="order.side = 'SELL'"><ArrowDown :size="15" />卖出</button></div>
          <div class="segmented subtle"><button type="button" :class="{ selected: order.offset === 'OPEN' }" @click="order.offset = 'OPEN'">开仓</button><button type="button" :class="{ selected: order.offset === 'CLOSE' }" @click="order.offset = 'CLOSE'">平仓</button></div>
          <label><span>委托类型</span><select v-model="order.orderType"><option value="MARKET">市价单</option><option value="LIMIT">限价单</option><option value="STOP">止损触发单</option></select></label>
          <label><span>手数</span><input v-model.number="order.quantity" type="number" min="1" max="1000000" /></label>
          <label v-if="order.orderType === 'LIMIT'"><span>限价</span><input v-model.number="order.limitPrice" type="number" min="0" :step="current.priceTick" /></label>
          <label v-if="order.orderType === 'STOP'"><span>触发价</span><input v-model.number="order.stopPrice" type="number" min="0" :step="current.priceTick" /></label>
          <div class="estimate"><span>当前合约</span><strong>{{ current.currentContract }}</strong><span>参考价</span><strong>{{ formatNumber(current.currentPrice, 2) }}</strong><span>每手保证金参考</span><strong>{{ money(Math.max(current.marginPerLot, current.currentPrice * current.volumeMultiple * current.marginRate)) }}</strong></div>
          <button class="submit-order" :class="order.side.toLowerCase()" type="button" :disabled="working || automationLocked || current.status !== 'ACTIVE' || order.offset==='OPEN'&&current.planGuard?.enabled&&!current.planGuard.openingAllowed" @click="placeOrder"><LoaderCircle v-if="working" class="spin" :size="16" />{{ order.side === 'BUY' ? '提交买入' : '提交卖出' }}{{ order.offset === 'OPEN' ? '开仓' : '平仓' }}</button>
          <p v-if="automationLocked" class="execution-note">该合约正在量化执行或读取状态；停止该合约策略后可手动下单。</p>
          <p class="execution-note">{{ isHistorical ? '历史模式下，委托最早从下一根 K 线撮合，避免使用下单时不可知的未来价格。' : '实时模式使用天勤当前行情模拟成交，始终不会向真实经纪账户发送委托。' }}</p>

          <div class="pending"><div class="pending-title"><span>全部品种待成交委托</span><b>{{ activeOrders.length }}</b></div><article v-for="item in pagedActive" :key="item.id"><div><strong>{{item.contract??'未绑定合约'}} · {{ item.side === 'BUY' ? '买' : '卖' }}{{ item.offset === 'OPEN' ? '开' : '平' }} · {{ item.orderType }}</strong><small>{{ item.remainingQuantity }}/{{ item.quantity }} 手<span v-if="item.reservedCash"> · 预留 {{money(item.reservedCash)}}</span></small></div><button type="button" @click="cancelOrder(item.id)">撤单</button></article><Pagination v-if="activeTotal>6" v-model:page="activePage" :page-size="6" :total="activeTotal" label="活动委托分页" /><p v-if="!activeOrders.length">暂无活动委托</p></div>
        </aside>
      </div>

      <p v-else-if="selecting" role="status">正在读取所选模拟账户…</p>
      <section v-else-if="!showCreate&&!activeWorkflowTrial&&!loading&&!selecting" class="empty-state"><History :size="28" /><h2>{{ sessionTotal ? '请选择模拟试验' : '还没有模拟试验' }}</h2><p>创建一个实时仿真或指定历史时点的独立试验。</p><button class="primary" type="button" @click="openCreate"><Plus :size="16" />新建试验</button></section>
    </div>

    <div v-if="showDeleteConfirm && current" class="modal-backdrop" role="presentation" @click.self="showDeleteConfirm = false">
      <section class="delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title">
        <div class="delete-icon"><Trash2 :size="20" /></div>
        <div><span>IRREVERSIBLE ACTION</span><h2 id="delete-title">删除“{{ current.name }}”？</h2></div>
        <p>此操作会永久删除该试验的行情路径、委托、持仓、成交与换月流水，无法恢复。</p>
        <div class="dialog-actions"><button type="button" @click="showDeleteConfirm = false">取消</button><button class="confirm-delete" type="button" :disabled="working" @click="deleteSession"><LoaderCircle v-if="working" class="spin" :size="15" />永久删除</button></div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.paper-chart .dkx-toggle{display:flex;align-items:center;flex-wrap:wrap;gap:.5rem;font-size:.75rem;margin:.7rem 0;color:#9245a7}.dkx-toggle small{color:var(--color-ink-secondary)}.dkx-toggle input[type=checkbox]{width:1rem;height:1rem;min-height:1rem;flex:0 0 auto;padding:0;margin:0;accent-color:#9245a7}
.live-chart-status{display:flex;flex-wrap:wrap;gap:.6rem;padding:.7rem .9rem;border:1px solid #dfc9a6;border-radius:.5rem;background:#fff6e8;color:#875c25}.live-chart-status.fresh{background:#edf7f1;border-color:#b7d5c3;color:#286347}
.replay-chart-controls{display:flex;align-items:center;flex-wrap:wrap;gap:.8rem;padding:.8rem 0 1rem}.replay-chart-controls>div{display:flex;gap:.3rem}.replay-chart-controls button{padding:.5rem .85rem;border:1px solid var(--color-line);border-radius:.4rem;background:white;color:var(--color-ink);cursor:pointer}.replay-chart-controls button[aria-pressed=true]{background:#e6f0ec;border-color:#71998a;color:#255b49}.replay-chart-controls small{font-size:.7rem;color:var(--color-ink-secondary)}
.plan-guard { display: grid; gap: .45rem; margin: 1rem 0; padding: 1rem 1.2rem; border: 1px solid var(--color-line); border-left: 3px solid #477f93; border-radius: .8rem; background: #f0f5f5; font-size: .75rem; line-height: 1.65; }
.plan-guard p { margin: 0; color: var(--color-ink-secondary); }.plan-guard summary { cursor: pointer; color: #315f75; }
.terminal-grid.managed{grid-template-columns:1fr}
.terminal-grid.strategy-terminal{grid-template-columns:minmax(0,1fr)}
.form-grid>.practice-intro{grid-column:1/-1;margin:0}
.universe-count{color:var(--color-ink-secondary);font-size:.72rem;white-space:nowrap}
.mode-bar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.8rem;margin-bottom:1rem;padding:.75rem 1rem;background:#f0f5f3;border:1px solid #c9ded6;border-radius:.75rem}
.mode-bar .mode-select{display:flex;align-items:center;gap:.5rem;font-size:.78rem;font-weight:600;color:#1e3d33}
.mode-bar .mode-select select{font-size:.74rem;font-weight:650;padding:.35rem .65rem;border-radius:.45rem;border:1px solid #a4c9bc;background:white;color:#1b4b3b;cursor:pointer}
.create-strategy-picker,.create-ma-replay{padding:.8rem 1rem;margin-bottom:1rem;border:1px solid var(--color-line);border-radius:.65rem}
.create-strategy-picker label{display:grid;max-width:32rem;gap:.35rem;font-size:.8rem;font-weight:650}
.create-strategy-picker label+label{margin-top:.75rem}
.create-strategy-picker p{margin:.5rem 0 0;font-size:.75rem;line-height:1.55;color:var(--color-ink-secondary)}
.create-strategy-picker select{min-width:0;max-width:100%;padding:.45rem;border:1px solid var(--color-line);border-radius:.42rem;background:var(--color-surface-raised);color:var(--color-ink);font:inherit}
#create-experiment{scroll-margin-top:1rem}
.mode-tabs{display:flex;flex-wrap:wrap;gap:.4rem}
.mode-tabs button{padding:.4rem .75rem;border:1px solid #b7d5c9;border-radius:.5rem;background:white;color:#355c4e;font-size:.7rem;font-weight:600;cursor:pointer;transition:all .15s}
.mode-tabs button.active{background:#235848;border-color:#235848;color:white;box-shadow:0 2px 8px rgb(35 88 72 / 20%)}
.symbol-discovery{display:grid;gap:.7rem;margin-bottom:1rem;padding:1rem;background:#f6f7f4;border:1px solid var(--color-line);border-radius:.7rem}.symbol-discovery-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.6rem;font-size:.78rem}.symbol-discovery-head button{display:inline-flex;align-items:center;gap:.35rem}.symbol-discovery button{padding:.35rem .65rem;border:1px solid var(--color-line);border-radius:.4rem;background:white;color:var(--color-ink-secondary);cursor:pointer;font-size:.66rem}.sector-filters{display:flex;flex-wrap:wrap;gap:.35rem}.sector-filters button[aria-pressed="true"]{background:#e1ece7;border-color:#82a99a;color:#254b3e}.symbol-discovery p{margin:0;color:var(--color-ink-secondary);font-size:.68rem;line-height:1.6}
.paper-chart{padding:1rem 1.25rem;border-bottom:1px solid var(--color-line);min-width:0}.paper-chart .section-title{flex-wrap:wrap;gap:.5rem}.paper-chart label,.paper-chart p,.paper-chart details{font-size:.68rem;line-height:1.7}.paper-chart select{padding:.25rem;border:1px solid var(--color-line);border-radius:.3rem}.chart-note{color:var(--color-ink-secondary)}.order-history{margin-top:.8rem}.order-history summary{cursor:pointer}

.paper-page,.experiment-workspace { display: grid; grid-template-columns: minmax(0, 1fr); gap: 1rem; min-width: 0; }
.experiment-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .8rem; }
.experiment-actions .new-session { min-height: 2.6rem; }
.practice-intro { margin:0;font-size:.76rem;line-height:1.9;color:var(--color-ink-secondary);padding:.5rem .2rem; }.practice-intro a {color:var(--color-accent);margin-left:.6rem;white-space:nowrap;}
.trust-strip { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .75rem 1rem; color: #405259; border: 1px solid #cfdcdf; border-radius: .8rem; background: #edf4f4; font-size: .75rem; }
.trust-strip div { display: flex; align-items: center; gap: .45rem; color: #183a45; }
.error-banner { display: flex; align-items: center; gap: .6rem; padding: .8rem 1rem; color: #7b2f28; border: 1px solid #e8c1bb; border-radius: .8rem; background: #fff0ed; font-size: .78rem; }
.error-banner span { flex: 1; }.error-banner button,.panel-heading button { display: grid; place-items: center; padding: .3rem; border: 0; background: transparent; cursor: pointer; }
.loading-state,.empty-state { display: grid; min-height: 20rem; place-items: center; align-content: center; gap: .8rem; color: var(--color-ink-secondary); }
.session-rail { display: flex; align-items: stretch; gap: .8rem; min-width: 0; }
.session-tabs { display: flex; flex: 1; gap: .45rem; min-width: 0; overflow-x: auto; scrollbar-width: thin; }
.session-tabs button { display: flex; flex: 0 0 auto; min-width: 11rem; align-items: center; gap: .6rem; padding: .7rem .85rem; color: var(--color-ink-secondary); border: 1px solid var(--color-line); border-radius: .75rem; background: rgb(255 255 255 / 45%); cursor: pointer; text-align: left; }
.session-tabs button.active { color: var(--color-ink); border-color: #aebfc8; background: white; box-shadow: 0 5px 16px rgb(20 35 44 / 7%); }.session-tabs button span:nth-child(2) { display: grid; gap: .12rem; }.session-tabs strong { font-size: .76rem; }.session-tabs small { color: var(--color-ink-tertiary); font-size: .63rem; }
.status-dot { width: .44rem; height: .44rem; border-radius: 50%; background: #8b8d90; }.status-dot.active { background: var(--color-success); box-shadow: 0 0 0 3px var(--color-success-soft); }.status-dot.error { background: #b33d33; }.status-dot.paused { background: #b1842d; }
.new-session,.playback button { display: inline-flex; align-items: center; justify-content: center; gap: .4rem; padding: .7rem .85rem; color: #263239; border: 1px solid var(--color-line); border-radius: .7rem; background: white; cursor: pointer; font-size: .72rem; font-weight: 650; white-space: nowrap; }
.create-panel,.ledger,.order-ticket { border: 1px solid var(--color-line); border-radius: 1rem; background: var(--color-surface-raised); box-shadow: var(--shadow-raised); }
.create-panel { padding: 1.25rem; }.panel-heading,.section-title,.ticket-head { display: flex; align-items: center; justify-content: space-between; }.panel-heading span,.section-title span,.ticket-head span { color: var(--color-ink-tertiary); font: 650 .58rem var(--font-numeric); letter-spacing: .13em; }.panel-heading h2,.section-title h3,.ticket-head h3 { margin: .2rem 0 0; font: 500 1.15rem var(--font-display); }
.form-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .85rem; margin-top: 1rem; }.form-grid label,.order-ticket > label { display: grid; gap: .35rem; color: var(--color-ink-secondary); font-size: .68rem; }
input,select { width: 100%; min-height: 2.45rem; padding: 0 .7rem; color: var(--color-ink); border: 1px solid var(--color-line); border-radius: .55rem; outline: none; background: #fafaf8; font: 500 .75rem var(--font-sans); } input:focus,select:focus { border-color: var(--color-accent); box-shadow: var(--shadow-focus); }
.check { display: flex; align-items: center; gap: .65rem; margin-top: 1rem; }.check input { width: 1rem; min-height: 1rem; }.check span { display: grid; gap: .1rem; }.check strong { font-size: .73rem; }.check small { color: var(--color-ink-tertiary); font-size: .64rem; }.create-actions { display: flex; align-items: center; justify-content: space-between; margin-top: 1rem; color: var(--color-ink-tertiary); font-size: .65rem; }
.primary { display: inline-flex; align-items: center; gap: .4rem; padding: .7rem 1rem; color: white; border: 0; border-radius: .65rem; background: #245b79; cursor: pointer; font-size: .72rem; font-weight: 700; }
.terminal-grid { display: grid; grid-template-columns: minmax(0, 1fr) 18rem; align-items: start; gap: 1rem; }.ledger { min-width: 0; overflow: hidden; }.market-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1.25rem; border-bottom: 1px solid var(--color-line); }.market-title { display: flex; gap: .4rem; }.mode-badge,.state-badge,.event-tag { display: inline-flex; padding: .2rem .42rem; border-radius: .3rem; background: #e8eef1; font: 700 .52rem var(--font-numeric); letter-spacing: .06em; }.state-badge.active { color: #236039; background: #e5f2e8; }.state-badge.paused { color: #75591e; background: #f4eacc; }.state-badge.error { color: #903a32; background: #f7dfdc; }
.market-header h2 { display: flex; align-items: baseline; gap: .7rem; margin: .5rem 0 .2rem; font: 600 1rem var(--font-numeric); }.market-header h2 strong { font-size: 1.85rem; }.market-header p { display: flex; align-items: center; gap: .35rem; margin: 0; color: var(--color-ink-tertiary); font-size: .66rem; }.playback { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .4rem; }.playback button { padding: .52rem .65rem; }.playback button:disabled,.submit-order:disabled,.primary:disabled { opacity: .45; cursor: not-allowed; }
.playback .delete-trigger { color: #8a342d; border-color: #e3c5c1; background: #fff8f6; }
.timeline { height: 2px; background: #e8e7e2; }.timeline > span { display: block; height: 100%; background: var(--color-accent); transition: width .25s; }.timeline div { display: flex; justify-content: space-between; padding: .35rem 1.25rem; color: var(--color-ink-tertiary); font: .56rem var(--font-numeric); }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); padding: 1.5rem 1.25rem 1rem; }.metrics article { display: grid; gap: .32rem; padding: .1rem 1rem; border-right: 1px solid var(--color-line); }.metrics article:first-child { padding-left: 0; }.metrics article:last-child { border: 0; }.metrics span { display: flex; align-items: center; gap: .35rem; color: var(--color-ink-tertiary); font-size: .64rem; }.metrics strong { font: 650 1.1rem var(--font-numeric); }.metrics small { color: var(--color-ink-tertiary); font-size: .6rem; }
.microstructure-section { margin: 1.1rem 1.25rem; padding-top: 1.1rem; border-top: 1px solid var(--color-line); }.micro-title small { display: flex; align-items: center; gap: .35rem; }.micro-title small i { width: .42rem; height: .42rem; border-radius: 50%; background: #96989b; }.micro-title small i.fresh { background: var(--color-success); box-shadow: 0 0 0 3px var(--color-success-soft); }.micro-grid { display: grid; grid-template-columns: minmax(17rem, .9fr) minmax(20rem, 1.35fr); gap: .8rem; margin-top: .8rem; }.depth-panel,.tape-panel { min-width: 0; overflow: hidden; border: 1px solid var(--color-line); border-radius: .72rem; background: #fbfbf9; }.depth-panel header,.tape-panel header { display: grid; padding: .48rem .65rem; color: var(--color-ink-tertiary); border-bottom: 1px solid var(--color-line); background: #f1f1ee; font: 600 .55rem var(--font-numeric); }.depth-panel header { grid-template-columns: 3rem 1fr 4.2rem; text-align: right; }.depth-panel header span:first-child { text-align: left; }.depth-row { position: relative; display: grid; grid-template-columns: 3rem 1fr 4.2rem; min-height: 1.62rem; align-items: center; padding: 0 .65rem; font: .61rem var(--font-numeric); }.depth-row i { position: absolute; z-index: 0; top: 2px; right: 0; bottom: 2px; opacity: .48; }.depth-row.ask i { background: var(--color-negative-soft); }.depth-row.bid i { background: var(--color-positive-soft); }.depth-row span,.depth-row strong,.depth-row b { position: relative; z-index: 1; }.depth-row span { color: var(--color-ink-tertiary); }.depth-row strong,.depth-row b { text-align: right; }.depth-row.ask strong { color: var(--color-negative); }.depth-row.bid strong { color: var(--color-positive); }.last-price { display: grid; grid-template-columns: 3rem 1fr 4.2rem; align-items: baseline; padding: .52rem .65rem; border-block: 1px solid var(--color-line); background: white; }.last-price span,.last-price small { color: var(--color-ink-tertiary); font-size: .57rem; }.last-price strong { text-align: right; font: 700 .86rem var(--font-numeric); }.last-price small { text-align: right; }.tape-panel header { grid-template-columns: 1.4fr 1fr .8fr .8fr; text-align: right; }.tape-panel header span:first-child { text-align: left; }.tape-scroll { max-height: 19rem; overflow-y: auto; }.tape-row { display: grid; grid-template-columns: 1.4fr 1fr .8fr .8fr; align-items: center; min-height: 1.75rem; padding: 0 .65rem; border-bottom: 1px solid #efeee9; font: .59rem var(--font-numeric); text-align: right; }.tape-row time { color: var(--color-ink-tertiary); text-align: left; }.tape-row.buy strong { color: var(--color-positive); }.tape-row.sell strong { color: var(--color-negative); }.tape-row.neutral strong { color: var(--color-ink-secondary); }.micro-placeholder { display: grid; min-height: 5rem; place-items: center; padding: 1rem; color: var(--color-ink-tertiary); font-size: .64rem; text-align: center; }.micro-footnote { margin: .65rem 0 0; color: var(--color-ink-tertiary); font-size: .58rem; line-height: 1.55; }.historical-depth-note { display: flex; align-items: flex-start; gap: .6rem; margin: 1.1rem 1.25rem; padding: .8rem; color: #516168; border: 1px solid #d7e0e1; border-radius: .7rem; background: #f2f6f6; }.historical-depth-note div { display: grid; gap: .18rem; }.historical-depth-note strong { font-size: .68rem; }.historical-depth-note span { color: #748086; font-size: .6rem; line-height: 1.5; }
.position-card,.records { margin: 1.1rem 1.25rem; padding-top: 1.1rem; border-top: 1px solid var(--color-line); }.section-title small { color: var(--color-ink-tertiary); font-size: .61rem; }.position-row { display: grid; grid-template-columns: 2rem 1fr repeat(4, auto); align-items: center; gap: 1rem; margin-top: .85rem; padding: .8rem; border-radius: .7rem; background: #f7f6f2; font: .7rem var(--font-numeric); }.direction { display: grid; width: 1.6rem; height: 1.6rem; place-items: center; color: white; border-radius: .38rem; font: 700 .64rem var(--font-sans); }.direction.long { background: var(--color-positive); }.direction.short { background: var(--color-negative); }.empty-line { margin-top: .8rem; padding: 1rem; color: var(--color-ink-tertiary); border: 1px dashed var(--color-line-strong); border-radius: .7rem; font-size: .7rem; text-align: center; }
.table-wrap { margin-top: .75rem; overflow-x: auto; }table { width: 100%; border-collapse: collapse; white-space: nowrap; }th { padding: .55rem .6rem; color: var(--color-ink-tertiary); border-bottom: 1px solid var(--color-line); font-size: .57rem; font-weight: 650; text-align: right; }th:first-child,th:nth-child(2),th:nth-child(3),td:first-child,td:nth-child(2),td:nth-child(3) { text-align: left; }td { padding: .68rem .6rem; border-bottom: 1px solid #efeee9; font: .61rem var(--font-numeric); text-align: right; }.event-tag.roll { color: #654c20; background: #f3e6c7; }.empty-cell { color: var(--color-ink-tertiary); text-align: center !important; }
.order-ticket { position: sticky; top: 1rem; display: grid; gap: .8rem; padding: 1rem; }.ticket-head { padding-bottom: .25rem; }.segmented { display: grid; grid-template-columns: 1fr 1fr; padding: .2rem; border-radius: .65rem; background: #eff0ef; }.segmented button { display: flex; min-height: 2.25rem; align-items: center; justify-content: center; gap: .35rem; color: var(--color-ink-secondary); border: 0; border-radius: .48rem; background: transparent; cursor: pointer; font-size: .71rem; font-weight: 650; }.segmented button.selected { color: var(--color-ink); background: white; box-shadow: 0 1px 5px rgb(0 0 0 / 9%); }.segmented:not(.subtle) button:first-child.selected { color: var(--color-positive); }.segmented:not(.subtle) button:last-child.selected { color: var(--color-negative); }.estimate { display: grid; grid-template-columns: 1fr auto; gap: .4rem; padding: .75rem; border-radius: .65rem; background: #f6f5f1; font-size: .63rem; }.estimate span { color: var(--color-ink-tertiary); }.estimate strong { font-family: var(--font-numeric); font-size: .64rem; }.submit-order { display: flex; min-height: 2.7rem; align-items: center; justify-content: center; gap: .4rem; color: white; border: 0; border-radius: .65rem; cursor: pointer; font-size: .75rem; font-weight: 700; }.submit-order.buy { background: var(--color-positive); }.submit-order.sell { background: var(--color-negative); }.execution-note { margin: 0; color: var(--color-ink-tertiary); font-size: .6rem; line-height: 1.55; }.pending { display: grid; gap: .5rem; padding-top: .8rem; border-top: 1px solid var(--color-line); }.pending-title { display: flex; justify-content: space-between; color: var(--color-ink-secondary); font-size: .68rem; }.pending-title b { font-family: var(--font-numeric); }.pending article { display: flex; align-items: center; justify-content: space-between; padding: .6rem; border: 1px solid var(--color-line); border-radius: .55rem; }.pending article div { display: grid; gap: .15rem; }.pending article strong { font-size: .65rem; }.pending article small,.pending > p { margin: 0; color: var(--color-ink-tertiary); font-size: .58rem; }.pending article button { padding: .25rem .4rem; color: #8a342d; border: 1px solid #e4c4c0; border-radius: .35rem; background: #fff5f3; cursor: pointer; font-size: .58rem; }
.up { color: var(--color-positive) !important; }.down { color: var(--color-negative) !important; }.spin { animation: spin .8s linear infinite; }@keyframes spin { to { transform: rotate(360deg); } }
.modal-backdrop { position: fixed; z-index: 100; inset: 0; display: grid; place-items: center; padding: 1rem; background: rgb(20 22 24 / 48%); backdrop-filter: blur(5px); }.delete-dialog { display: grid; width: min(100%, 27rem); gap: 1rem; padding: 1.4rem; border: 1px solid #d8c5c1; border-radius: 1rem; background: #fffdfa; box-shadow: 0 24px 70px rgb(20 22 24 / 28%); }.delete-icon { display: grid; width: 2.3rem; height: 2.3rem; place-items: center; color: #973d34; border-radius: .65rem; background: #f8e5e1; }.delete-dialog span { color: #a36d65; font: 700 .55rem var(--font-numeric); letter-spacing: .12em; }.delete-dialog h2 { margin: .25rem 0 0; font: 500 1.35rem var(--font-display); }.delete-dialog p { margin: 0; color: var(--color-ink-secondary); font-size: .72rem; line-height: 1.65; }.dialog-actions { display: flex; justify-content: flex-end; gap: .5rem; }.dialog-actions button { display: inline-flex; min-height: 2.35rem; align-items: center; gap: .4rem; padding: 0 .8rem; border: 1px solid var(--color-line); border-radius: .55rem; background: white; cursor: pointer; font-size: .68rem; font-weight: 650; }.dialog-actions .confirm-delete { color: white; border-color: #963e35; background: #963e35; }
@media (max-width: 1100px) { .terminal-grid { grid-template-columns: 1fr; }.order-ticket { position: static; grid-template-columns: repeat(2, 1fr); }.ticket-head,.submit-order,.execution-note,.pending { grid-column: 1 / -1; }.form-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 900px) { .micro-grid { grid-template-columns: 1fr; }.tape-scroll { max-height: 14rem; } }
@media (max-width: 760px) { .trust-strip { align-items: flex-start; flex-direction: column; }.session-rail,.market-header,.create-actions { align-items: stretch; flex-direction: column; }.new-session { min-height: 2.6rem; }.metrics { grid-template-columns: repeat(2, 1fr); gap: 1rem; }.metrics article:nth-child(2) { border: 0; }.position-row { grid-template-columns: 2rem 1fr auto; }.position-row span:nth-of-type(n+3),.position-row b { grid-column: span 1; }.order-ticket { grid-template-columns: 1fr; }.ticket-head,.submit-order,.execution-note,.pending { grid-column: auto; } }
@media (max-width: 520px) { .form-grid,.metrics { grid-template-columns: 1fr; }.metrics article { padding: .6rem 0; border-right: 0; border-bottom: 1px solid var(--color-line); }.market-header h2 strong { font-size: 1.5rem; }.playback { justify-content: flex-start; }.position-row { grid-template-columns: 2rem 1fr; } }
</style>

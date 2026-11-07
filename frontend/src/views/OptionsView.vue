<script setup lang="ts">
import {instrumentLabel,instrumentName} from '../utils/instrumentNames'
import {computed,inject,nextTick,onMounted,onUnmounted,ref,watch} from 'vue'
import {routeLocationKey,routerKey} from 'vue-router'
import {ArrowLeftRight,RefreshCw} from 'lucide-vue-next'
import {RefreshSchedule} from '../utils/refreshSchedule'
import {optionsApi} from '../services/options'
import type {OptionCatalog,OptionChainSnapshot,OptionContract,OptionScenario,OptionStatus} from '../types/options'
import {optionFuture,optionQuery,optionSelection} from '../utils/optionContext'
import {contextUuid,contextPeriod} from '../utils/tradingContext'
import {decisionsApi} from '../services/decisions'
import {decisionDetail} from '../utils/decisionResponses'
import {authState,hasPermission} from '../services/auth'

const route=inject(routeLocationKey,undefined),router=inject(routerKey,undefined)
const contextLoading=ref(false),contextIssue=ref(''),contextNotice=ref(''),wantedOption=ref('')
let applyingRoute=true,routeVersion=0,selectionReady=false,lastQueued=''
let navigation=Promise.resolve()
const internalQueries=new Set<string>()
let contextQuery:import('vue-router').LocationQuery|undefined
const querySignature=(q:unknown)=>JSON.stringify(q)

const catalog=ref<OptionCatalog|null>(null),snapshot=ref<OptionChainSnapshot|null>(null),scenario=ref<OptionScenario|null>(null)
const error=ref(''),catalogError=ref(''),scenarioError=ref(''),loading=ref(false),catalogLoading=ref(false),scenarioLoading=ref(false)
const exchange=ref(''),search=ref(''),chainId=ref(''),selectedSymbol=ref(''),side=ref<'BUY'|'SELL'>('BUY'),lots=ref(1)
const ratePct=ref(2),dividendPct=ref(0),rate=ref(.02),dividend=ref(0)
const exchanges=computed(()=>[...new Set(catalog.value?.chains.map(c=>c.exchange)??[])])
const chains=computed(()=>catalog.value?.chains.filter(c=>(!exchange.value||c.exchange===exchange.value)&&(!search.value||`${instrumentLabel(c.underlyingSymbol)} ${c.product}`.toLowerCase().includes(search.value.trim().toLowerCase())))??[])
const selected=computed(()=>snapshot.value?.contracts.find(c=>c.symbol===selectedSymbol.value)??null)
const states:Record<OptionStatus,string>={FRESH:'近时快照',CACHED:'缓存快照',WARMING:'正在准备',UNAVAILABLE:'数据不可用'}
const status=(s:OptionStatus)=>states[s]
const n=(v:number|null|undefined,d=2)=>v==null?'—':v.toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d})
const pct=(v:number|null|undefined)=>v==null?'—':`${n(v*100)}%`
const date=(v:string)=>new Date(v).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'})
const time=(v?:string|null)=>v?new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未取得'
const basis=(v?:string|null)=>v==='MID'?'双边中间价':v==='LAST'?'最新成交价':'无可用报价'
const rows=computed(()=>{
  const groups=new Map<number,{calls:OptionContract[];puts:OptionContract[]}>()
  for(const c of snapshot.value?.contracts??[]){const g=groups.get(c.strike)??{calls:[],puts:[]};(c.optionClass==='CALL'?g.calls:g.puts).push(c);groups.set(c.strike,g)}
  return [...groups].sort(([a],[b])=>a-b).flatMap(([strike,g])=>Array.from({length:Math.max(g.calls.length,g.puts.length)},(_,i)=>({strike,call:g.calls[i],put:g.puts[i],key:`${strike}-${i}`})))
})
const nearest=computed(()=>{
  const price=snapshot.value?.underlying.lastPrice
  return price==null||!rows.value.length?null:rows.value.reduce((a,b)=>Math.abs(a.strike-price)<Math.abs(b.strike-price)?a:b).strike
})
const assumptionsValid=computed(()=>Number.isFinite(ratePct.value)&&ratePct.value>=-10&&ratePct.value<=50&&Number.isFinite(dividendPct.value)&&dividendPct.value>=0&&dividendPct.value<=50)
const lotsValid=computed(()=>Number.isInteger(lots.value)&&lots.value>=1&&lots.value<=10000)
const chart=computed(()=>{
  const points=scenario.value?.points??[]
  if(!points.length)return null
  const xmax=Math.max(...points.map(p=>p.underlyingPrice)),lo=Math.min(0,...points.map(p=>p.pnl)),hi=Math.max(0,...points.map(p=>p.pnl))
  const pad=Math.max((hi-lo)*.12,1),ymin=lo-pad,ymax=hi+pad
  const x=(p:number)=>58+p/xmax*550,y=(p:number)=>205-(p-ymin)/(ymax-ymin)*180
  return {line:points.map(p=>`${x(p.underlyingPrice)},${y(p.pnl)}`).join(' '),zero:y(0),xmax,lo,hi,y,
    breakeven:scenario.value?.breakeven==null?null:x(scenario.value.breakeven)}
})
let alive=true,chainVersion=0,scenarioVersion=0,timer:number|undefined
const catalogSchedule=new RefreshSchedule(5000,60000),chainSchedule=new RefreshSchedule(5000)
function clearChain(){++chainVersion;++scenarioVersion;snapshot.value=null;scenario.value=null;selectedSymbol.value='';loading.value=false;scenarioLoading.value=false;error.value='';scenarioError.value='';chainSchedule.reset()}
async function applyRoute(){
  if(!catalog.value)return
  const version=++routeVersion;applyingRoute=true;contextQuery=undefined;contextLoading.value=true;contextIssue.value='';contextNotice.value='';clearChain()
  const q=route?.query??{},parsed=optionQuery(q)
  try{
    if(parsed.errors.length)throw new Error(parsed.errors.join(' '))
    if(authState.user&&!hasPermission('options.read'))throw new Error('当前身份没有期权读取权限。')
    let target=parsed.symbol,period=String(parsed.frequency),cid='',pid=''
    if(q.case!==undefined){
      if(!hasPermission('market.read')||!hasPermission('paper.read'))throw new Error('当前身份不能核验关联档案。')
      cid=contextUuid(q.case);const item=decisionDetail(await decisionsApi.detail(cid),cid)
      if(!alive||version!==routeVersion)return
      const plan=q.plan===undefined?item.plans.find(p=>p.version===item.version):item.plans.find(p=>p.id===contextUuid(q.plan))
      if(q.plan!==undefined&&!plan)throw new Error('指定计划版本不在此档案中。')
      pid=plan?.id??'';if(!target)target=item.symbol
      if(target!==item.symbol)throw new Error('期权标的与原计划不是同一交割月，请先解除关联或返回原计划。')
      if(q.period===undefined&&q.seconds===undefined)period=String(contextPeriod(String(item.origin.evidence?.triggerSeconds))??(Number(item.origin.evidence?.triggerSeconds)===86400?'DAY':60))
    }
    const entry=parsed.chain?catalog.value.chains.find(c=>c.id===parsed.chain):target?catalog.value.chains.find(c=>optionFuture(c)===target):catalog.value.chains[0]
    if(!entry&&(parsed.chain||target)){chainId.value=parsed.chain;throw new Error('指定月份或期权链不在当前目录，保留原请求，不自动替换其他月份。')}
    if(entry&&target&&optionFuture(entry)!==target)throw new Error('期权链与请求的实际期货合约不一致，已停止加载。')
    exchange.value='';search.value='';chainId.value=entry?.id??'';wantedOption.value=parsed.option
    side.value=parsed.side;lots.value=parsed.lots;rate.value=parsed.rate;dividend.value=parsed.dividend;ratePct.value=Number((parsed.rate*100).toPrecision(12));dividendPct.value=Number((parsed.dividend*100).toPrecision(12))
    selectionReady=!!entry
    await nextTick();if(!alive||version!==routeVersion)return
    applyingRoute=false;contextLoading.value=false
    const canonical={...q,symbol:entry?optionFuture(entry):'',period,...cid?{case:cid,...pid?{plan:pid}:{}}:{}}
    syncRoute(false,canonical)
    if(chainId.value)void loadChain()
  }catch(e){if(alive&&version===routeVersion){clearChain();selectionReady=false;contextIssue.value=e instanceof Error?e.message:'期权上下文无法恢复。';contextLoading.value=false;await nextTick();if(version===routeVersion)applyingRoute=false}}
}
function syncRoute(push=true,source=contextQuery??route?.query??{}){
  if(!router||applyingRoute||contextIssue.value||!selectionReady||!lotsValid.value||!assumptionsValid.value)return
  const entry=catalog.value?.chains.find(c=>c.id===chainId.value),q=optionSelection(source,entry,wantedOption.value,side.value,lots.value,rate.value,dividend.value)
  contextQuery=Object.fromEntries(Object.entries(q).filter(([,value])=>typeof value==='string')) as import('vue-router').LocationQuery
  const signature=querySignature(q),version=routeVersion
  if(signature===lastQueued||signature===querySignature(route?.query)&&!lastQueued)return
  lastQueued=signature
  navigation=navigation.then(async()=>{
    if(!alive||version!==routeVersion)return
    internalQueries.add(signature)
    try{await router[push?'push':'replace']({path:'/options',query:q});await nextTick()}
    finally{internalQueries.delete(signature);if(lastQueued===signature)lastQueued=''}
  }).catch(()=>{if(alive)contextNotice.value='链接同步失败，请重新选择合约后重试。'})
}
function selectContract(){
  if(!snapshot.value)return
  if(wantedOption.value){
    if(!snapshot.value.contracts.some(c=>c.symbol===wantedOption.value)){selectedSymbol.value='';scenario.value=null;error.value='指定期权合约不在本链快照中，保留原请求，不自动选择其他行权价或认购认沽。';return}
    selectedSymbol.value=wantedOption.value;error.value='';return
  }
  const price=snapshot.value.underlying.lastPrice
  selectedSymbol.value=price!=null&&price>0?[...snapshot.value.contracts].sort((a,b)=>Math.abs(a.strike-price)-Math.abs(b.strike-price))[0]?.symbol??'':''
  wantedOption.value=selectedSymbol.value;syncRoute(false)
}
async function loadCatalog(){
  if(catalogLoading.value)return
  catalogLoading.value=true;catalogError.value=''
  try{const data=await optionsApi.catalog();if(!alive)return;catalog.value=data;data.chains.length?catalogSchedule.defer(60000):catalogSchedule.received('WARMING');if(!selectionReady||chainId.value&&!data.chains.some(c=>c.id===chainId.value))await applyRoute()}
  catch(e){if(alive){catalogError.value=e instanceof Error?e.message:'期权目录获取失败';catalogSchedule.failed()}}
  finally{if(alive)catalogLoading.value=false}
}
async function loadChain(){
  if(!chainId.value||loading.value||applyingRoute||contextIssue.value||contextLoading.value)return
  const version=++chainVersion,id=chainId.value;loading.value=true;error.value=''
  try{
    const data=await optionsApi.chain(id,rate.value,dividend.value)
    if(!alive||version!==chainVersion||id!==chainId.value)return
    const expected=catalog.value?.chains.find(c=>c.id===id)
    if(!expected||data.chain.id!==id||data.chain.underlyingSymbol!==expected.underlyingSymbol||data.chain.underlyingType!==expected.underlyingType||data.chain.expiry!==expected.expiry)throw new Error('期权快照的链、标的或到期日不匹配，已停止展示。')
    snapshot.value=data;chainSchedule.received(data.dataStatus)
    selectContract()
  }catch(e){if(alive&&version===chainVersion){chainSchedule.failed();error.value=e instanceof Error?e.message:'期权链获取失败';snapshot.value=null;selectedSymbol.value=''}}
  finally{if(alive&&version===chainVersion)loading.value=false}
}
async function loadScenario(){
  const version=++scenarioVersion,c=selected.value
  scenario.value=null;scenarioError.value='';scenarioLoading.value=false
  if(applyingRoute||contextIssue.value||!c||!lotsValid.value||c.risk.referencePrice==null||!c.volumeMultiple||!snapshot.value?.underlying.lastPrice)return
  scenarioLoading.value=true
  const body={chainId:chainId.value,symbol:c.symbol,side:side.value,lots:lots.value}
  try{const data=await optionsApi.scenario(body);if(alive&&version===scenarioVersion){if(data.symbol!==body.symbol||data.side!==body.side||data.lots!==body.lots)throw new Error('情景响应与所选合约、方向或手数不一致。');scenario.value=data}}
  catch(e){if(alive&&version===scenarioVersion)scenarioError.value=e instanceof Error?e.message:'情景暂不可用'}
  finally{if(alive&&version===scenarioVersion)scenarioLoading.value=false}
}
function applyAssumptions(){if(!assumptionsValid.value||contextLoading.value)return;++chainVersion;loading.value=false;chainSchedule.reset();rate.value=ratePct.value/100;dividend.value=dividendPct.value/100;syncRoute();void loadChain()}
watch([exchange,search],()=>{if(!applyingRoute&&!chains.value.some(c=>c.id===chainId.value))chainId.value=chains.value[0]?.id??''})
watch(chainId,()=>{if(applyingRoute)return;const before=snapshot.value?.chain;clearChain();wantedOption.value='';contextIssue.value='';selectionReady=true;const entry=catalog.value?.chains.find(c=>c.id===chainId.value);if(before&&optionFuture(before)!==optionFuture(entry)&&(route?.query.case||route?.query.plan))contextNotice.value='已切换期权标的，解除原计划关联；原计划未被修改。';syncRoute();if(chainId.value)void loadChain()})
watch(selectedSymbol,()=>{if(!applyingRoute&&selectedSymbol.value){wantedOption.value=selectedSymbol.value;error.value='';syncRoute()}})
watch([selected,side,lots],()=>{if(!applyingRoute){syncRoute();void loadScenario()}})
watch(()=>route?.fullPath,()=>{if(internalQueries.has(querySignature(route?.query)))return;lastQueued='';if(catalog.value)void applyRoute()})
watch(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId,authState.user?.permissions]),()=>{if(catalog.value)void applyRoute()})
function visibility(){if(!document.hidden){catalogSchedule.reset();chainSchedule.reset();void loadCatalog();void loadChain()}}
onMounted(()=>{void loadCatalog();document.addEventListener('visibilitychange',visibility);timer=window.setInterval(()=>{if(document.hidden)return;if(catalogSchedule.due())void loadCatalog();if(chainSchedule.due())void loadChain()},1000)})
onUnmounted(()=>{document.removeEventListener('visibilitychange',visibility);alive=false;++chainVersion;++scenarioVersion;++routeVersion;window.clearInterval(timer)})
</script>

<template>
  <div class="options-workspace">
    <header class="options-intro"><div><p class="kicker">OPTIONS / 国内期权研究</p><h2>沿着行权价，看清权利与风险。</h2><p>商品与金融期权 · 真实合约链 · 波动率与单腿到期情景</p></div><button class="refresh" :disabled="catalogLoading||loading" @click="loadCatalog();loadChain()"><RefreshCw :size="15"/>刷新行情</button></header>
    <p v-if="contextLoading" class="notice" role="status">正在核验期权标的与原计划…</p><p v-if="contextIssue" class="notice" role="alert">{{contextIssue}}</p><p v-if="contextNotice" class="notice" role="status">{{contextNotice}}</p>
    <p class="source-note">本页展示当前期权快照；看盘周期仅用于返回期货行情，不改变期权链和到期情景。期货计划仅作参考关联，不会转成期权仓位或执行资格。</p>
    <p v-if="catalogError" class="notice" role="alert">{{catalogError}} <button @click="loadCatalog">重试目录</button></p>
    <p v-if="catalog?.message" class="notice" role="status">{{catalog.message}}</p>
    <section class="chain-panel" aria-label="期权链">
      <form class="filters" @submit.prevent>
        <label>交易所<select :disabled="contextLoading" v-model="exchange" aria-label="期权交易所"><option value="">全部交易所</option><option v-for="item in exchanges" :key="item">{{item}}</option></select></label>
        <label>搜索标的<input :disabled="contextLoading" v-model="search" type="search" aria-label="搜索期权标的" placeholder="例如 cu、m、000300"/></label>
        <label class="chain-select">标的 / 到期日<select v-model="chainId" aria-label="期权链选择" :disabled="contextLoading||!chains.length"><option v-if="!chains.length" value="">暂无匹配的真实合约链</option><option v-if="chainId&&!chains.some(c=>c.id===chainId)" :value="chainId">{{chainId}} · 目录未包含</option><option v-for="chain in chains" :key="chain.id" :value="chain.id">{{instrumentLabel(chain.underlyingSymbol)}} · {{date(chain.expiry)}} · {{chain.contractCount}} 个合约</option></select></label>
      </form>
      <div v-if="snapshot" class="underlying-strip"><div><small>{{snapshot.chain.underlyingType==='INDEX'?'标的指数':'标的期货'}}</small><strong>{{instrumentLabel(snapshot.chain.underlyingSymbol)}}</strong><b>{{n(snapshot.underlying.lastPrice)}}</b></div><div><span class="state" :class="snapshot.underlying.dataStatus">{{status(snapshot.underlying.dataStatus)}}</span><small>{{time(snapshot.underlying.dataTimestamp)}}</small></div><p>到期 {{time(snapshot.chain.expiry)}} · {{snapshot.source}}<br/>每 5 秒刷新快照，休市期间保留真实报价时点</p></div>
      <p v-if="error" class="notice" role="alert">{{error}} <button @click="loadChain">重试期权链</button></p>
      <p v-if="loading&&!snapshot" class="empty" role="status">正在读取真实期权链…</p>
      <p v-else-if="!snapshot&&!error" class="empty" role="status">{{catalogLoading?'正在读取期权目录…':catalog?.chains.length?'请选择或调整筛选，查看期权链。':'暂无可用期权合约。配置天勤账户及期权数据权限后，目录将自动刷新。'}}</p>
      <template v-if="snapshot">
        <p v-if="snapshot.message" class="notice" role="status">{{snapshot.message}}</p>
        <div class="chain-scroll"><table class="chain-table"><caption>认购在左，认沽在右；点击报价查看风险。浅色行是最接近平值的行权价。缺失数据以 — 显示。</caption><thead><tr class="side-heading"><th colspan="5">认购期权</th><th rowspan="2" class="strike">行权价</th><th colspan="5">认沽期权</th></tr><tr><th>参考 IV</th><th>买一</th><th>卖一</th><th>最新价 / 合约</th><th>状态</th><th>状态</th><th>最新价 / 合约</th><th>买一</th><th>卖一</th><th>参考 IV</th></tr></thead>
          <tbody><tr v-for="row in rows" :key="row.key" :class="{atm:row.strike===nearest}"><td>{{pct(row.call?.risk.iv)}}</td><td>{{n(row.call?.bidPrice)}}</td><td>{{n(row.call?.askPrice)}}</td><td><button v-if="row.call" class="contract" :aria-pressed="selectedSymbol===row.call.symbol" :aria-label="`查看 ${instrumentLabel(row.call.symbol,row.call.name)} 风险`" @click="selectedSymbol=row.call.symbol"><b>{{n(row.call.lastPrice)}}</b><small>{{instrumentLabel(row.call.symbol,row.call.name)}}</small></button><span v-else>—</span></td><td><span v-if="row.call" class="state" :class="row.call.dataStatus">{{status(row.call.dataStatus)}}</span></td><th class="strike">{{n(row.strike)}}<small v-if="row.strike===nearest">近似平值</small></th><td><span v-if="row.put" class="state" :class="row.put.dataStatus">{{status(row.put.dataStatus)}}</span></td><td><button v-if="row.put" class="contract" :aria-pressed="selectedSymbol===row.put.symbol" :aria-label="`查看 ${instrumentLabel(row.put.symbol,row.put.name)} 风险`" @click="selectedSymbol=row.put.symbol"><b>{{n(row.put.lastPrice)}}</b><small>{{instrumentLabel(row.put.symbol,row.put.name)}}</small></button><span v-else>—</span></td><td>{{n(row.put?.bidPrice)}}</td><td>{{n(row.put?.askPrice)}}</td><td>{{pct(row.put?.risk.iv)}}</td></tr></tbody>
        </table></div>
      </template>
    </section>
    <div v-if="selected&&snapshot" class="risk-layout">
      <section class="risk-panel" aria-label="合约风险分析"><div class="panel-heading"><div><p class="kicker">CONTRACT / 风险参考</p><h3>{{instrumentName(selected.symbol,selected.name)}}</h3><span>{{selected.symbol}} · {{selected.optionClass==='CALL'?'认购':'认沽'}} · {{selected.exerciseType==='A'?'美式':selected.exerciseType==='E'?'欧式':'行权方式未取得'}}</span></div><ArrowLeftRight :size="21"/></div>
        <p class="quote-time">报价 {{time(selected.dataTimestamp)}} · {{status(selected.dataStatus)}}<br/>模型估值时点 {{time(selected.risk.valuationTimestamp)}}</p>
        <div class="reference"><span>{{basis(selected.risk.priceBasis)}}<small>每单位权利金</small></span><strong>{{n(selected.risk.referencePrice)}}</strong></div>
        <p v-if="selected.risk.priceNote" class="note">{{selected.risk.priceNote}}</p>
        <dl class="greeks"><div><dt>参考 IV</dt><dd>{{pct(selected.risk.iv)}}</dd></div><div><dt>Delta</dt><dd>{{n(selected.risk.delta,4)}}</dd></div><div><dt>Gamma</dt><dd>{{n(selected.risk.gamma,6)}}</dd></div><div><dt>Theta / 自然日</dt><dd>{{n(selected.risk.theta,4)}}</dd></div><div><dt>Vega / 1 波动率百分点</dt><dd>{{n(selected.risk.vega,4)}}</dd></div><div><dt>合约乘数</dt><dd>{{n(selected.volumeMultiple,0)}}</dd></div><div><dt>内在 / 时间价值</dt><dd>{{n(selected.risk.intrinsicValue)}} / {{n(selected.risk.timeValue)}}</dd></div><div><dt>买卖价差</dt><dd>{{n(selected.risk.spread)}}</dd></div><div><dt>成交量 / 手</dt><dd>{{n(selected.volume,0)}}</dd></div><div><dt>持仓量 / 手</dt><dd>{{n(selected.openInterest,0)}}</dd></div></dl>
        <p v-if="selected.risk.riskReason" class="notice" :role="selected.risk.riskStatus==='UNAVAILABLE'?'status':undefined">{{selected.risk.riskReason}}</p>
        <details class="model-notes" open><summary>模型与计算假设</summary><p>{{selected.risk.model==='BLACK_76'?'Black-76 期货期权模型':'BSM 指数期权模型'}} · ACT/365。指标为每单位权利金的敏感度；整笔头寸需乘合约乘数、手数及买卖方向。</p><p>当前计算使用年化利率 {{pct(snapshot.assumptions.rate)}}、股息率 {{pct(snapshot.assumptions.dividend)}}。两项均为用户假设，非实时市场数据；期货模型不使用股息率。</p><form class="assumptions" @submit.prevent="applyAssumptions"><label>年化利率 %<input v-model.number="ratePct" aria-label="年化利率百分比" type="number" min="-10" max="50" step="0.1" required/></label><label>指数股息率 %<input v-model.number="dividendPct" aria-label="股息率百分比" type="number" min="0" max="50" step="0.1" required :disabled="snapshot.chain.underlyingType==='FUTURE'"/></label><button :disabled="!assumptionsValid||loading">应用假设</button></form><p>美式期权仅提供欧式模型近似。报价不同步超过 5 分钟、模型价格越界、缺少行权信息或合约到期时，IV 和 Greeks 留空。</p></details>
      </section>
      <section class="scenario-panel" aria-label="单腿到期损益"><div class="panel-heading"><div><p class="kicker">AT EXPIRY / 单腿情景</p><h3>到期时，盈亏如何变化？</h3></div></div><div class="scenario-inputs"><label>方向<select v-model="side" aria-label="情景买卖方向"><option value="BUY">买入期权</option><option value="SELL">卖出期权</option></select></label><label>手数<input v-model.number="lots" aria-label="情景手数" type="number" min="1" max="10000" step="1"/></label></div>
        <p v-if="!lotsValid" class="notice" role="alert">手数需为 1 至 10000 的整数。</p><p v-if="scenarioError" class="notice" role="alert">{{scenarioError}} <button @click="loadScenario">重试情景</button></p><p v-if="scenarioLoading" class="empty" role="status">正在计算到期情景…</p>
        <template v-if="scenario&&chart"><p class="note">按 {{basis(scenario.priceBasis)}} {{n(scenario.referencePrice)}} 测算 · {{status(scenario.dataStatus)}}<br/>权利金时点 {{time(scenario.dataTimestamp)}}；标的 {{status(scenario.underlyingStatus)}} {{time(scenario.underlyingTimestamp)}}</p><svg viewBox="0 0 640 250" role="img" :aria-label="`${side==='BUY'?'买入':'卖出'} ${selected.symbol} ${lots} 手的到期损益曲线`"><title>单腿期权到期损益，横轴为标的价格，纵轴为整笔盈亏（元）</title><line x1="58" y1="25" x2="58" y2="205" class="axis"/><line x1="58" y1="205" x2="608" y2="205" class="axis"/><line x1="58" :y1="chart.zero" x2="608" :y2="chart.zero" class="zero"/><line v-if="chart.breakeven!=null" :x1="chart.breakeven" y1="25" :x2="chart.breakeven" y2="205" class="zero"/><polyline :points="chart.line" class="payoff"/><text x="4" :y="chart.y(chart.hi)+4">{{n(chart.hi,0)}}</text><text x="4" :y="chart.y(chart.lo)+4">{{n(chart.lo,0)}}</text><text x="58" y="225">0</text><text x="608" y="225" text-anchor="end">{{n(chart.xmax,0)}}</text><text x="335" y="246" text-anchor="middle">到期标的价格</text></svg>
          <dl class="scenario-metrics"><div><dt>{{side==='BUY'?'支付':'收取'}}权利金 / 元</dt><dd>{{n(scenario.premiumAmount)}}</dd></div><div><dt>盈亏平衡标的价</dt><dd>{{n(scenario.breakeven)}}</dd></div><div><dt>最大到期亏损 / 元</dt><dd :class="{warning:scenario.unlimitedLoss}">{{scenario.unlimitedLoss?'理论上无上限':n(scenario.maxLoss)}}</dd></div><div><dt>最大到期收益 / 元</dt><dd>{{scenario.unlimitedProfit?'理论上无上限':n(scenario.maxProfit)}}</dd></div></dl><p class="note">{{scenario.note}}</p><p v-if="scenario.priceNote" class="note">{{scenario.priceNote}}</p>
        </template><p v-else-if="!scenarioLoading&&!scenarioError&&lotsValid" class="empty">取得真实权利金、标的价格与合约乘数后显示到期情景。</p>
      </section>
    </div>
    <p class="source-note">数据源为天勤 TqSdk；覆盖范围由账户权限和真实目录决定。模型指标与到期情景用于研究，不代表实际成交价、保证金或收益承诺。</p>
  </div>
</template>

<style scoped>
.options-workspace{display:grid;gap:1.4rem;min-width:0}.options-intro{display:flex;align-items:center;justify-content:space-between;gap:1rem}.kicker{font:500 .65rem var(--font-numeric);letter-spacing:.1em;color:var(--color-accent);margin:0 0 .7rem}.options-intro h2{font:500 clamp(1.4rem,2vw,2rem) var(--font-display);margin:0 0 .7rem}.options-intro>div>p:last-child{font-size:.8rem;color:var(--color-ink-secondary);margin:0}button,select,input{font:inherit}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}.refresh,.assumptions button{display:inline-flex;align-items:center;gap:.5rem;padding:.7rem .9rem;border:1px solid var(--color-line-strong);border-radius:.5rem;background:var(--color-surface);font-size:.75rem;white-space:nowrap;color:var(--color-ink)}.chain-panel,.risk-panel,.scenario-panel{background:var(--color-surface);border:1px solid var(--color-line);border-radius:.8rem;min-width:0;overflow:hidden}.filters{display:flex;gap:1rem;flex-wrap:wrap;padding:1.2rem;border-bottom:1px solid var(--color-line)}label{display:grid;gap:.4rem;font-size:.7rem;color:var(--color-ink-secondary)}input,select{background:var(--color-surface-raised);border:1px solid var(--color-line);border-radius:.4rem;padding:.65rem .7rem;color:var(--color-ink);max-width:100%;min-width:0}.chain-select{flex:1;min-width:18rem}.underlying-strip{display:flex;align-items:center;gap:1.8rem;padding:1.2rem;flex-wrap:wrap}.underlying-strip>div{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}.underlying-strip small,.underlying-strip p{font-size:.65rem;color:var(--color-ink-secondary);line-height:1.8}.underlying-strip strong{font:.8rem var(--font-numeric)}.underlying-strip b{font:600 1.2rem var(--font-numeric)}.underlying-strip p{margin:0 0 0 auto}.state{display:inline-block;font:.58rem var(--font-sans);border-radius:3px;padding:.2rem .3rem;color:var(--color-warning);background:var(--color-warning-soft);white-space:nowrap}.state.FRESH{color:var(--color-success);background:var(--color-success-soft)}.chain-scroll{overflow:auto;max-height:560px}.chain-table{width:100%;border-collapse:separate;border-spacing:0;white-space:nowrap;font:.7rem var(--font-numeric);text-align:right}.chain-table caption{text-align:left;padding:.8rem 1.2rem;font:.65rem var(--font-sans);color:var(--color-ink-secondary);white-space:normal;line-height:1.8}.chain-table thead th{font:.65rem var(--font-sans);background:var(--color-canvas);padding:.65rem .6rem;border-bottom:1px solid var(--color-line)}.chain-table .side-heading th{text-align:center;color:var(--color-accent);letter-spacing:.12em}.chain-table td,.chain-table tbody th{padding:.5rem .6rem;border-bottom:1px solid var(--color-line)}.chain-table .strike{text-align:center;background:var(--color-canvas);border-left:1px solid var(--color-line);border-right:1px solid var(--color-line);color:var(--color-ink);min-width:5.5rem}.chain-table small{display:block;font-size:.55rem;color:var(--color-ink-secondary);margin-top:.3rem}.chain-table .atm td{background:var(--color-accent-soft)}.contract{border:1px solid transparent;background:transparent;color:var(--color-ink);border-radius:.3rem;padding:.4rem;min-width:6.8rem;text-align:right}.contract[aria-pressed=true]{border-color:var(--color-accent);background:var(--color-surface-raised)}.contract:hover{border-color:var(--color-line-strong)}.risk-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:1.2rem;align-items:start}.risk-panel,.scenario-panel{padding:1.3rem}.panel-heading{display:flex;justify-content:space-between;align-items:start;gap:1rem}.panel-heading h3{margin:0 0 .6rem;font:500 1.2rem var(--font-display)}.panel-heading span,.quote-time,.note{font-size:.69rem;color:var(--color-ink-secondary);line-height:1.9}.quote-time{padding-bottom:.8rem;border-bottom:1px solid var(--color-line)}.reference{display:flex;justify-content:space-between;align-items:center;margin:1rem 0}.reference span{font-size:.75rem}.reference small{display:block;color:var(--color-ink-tertiary);font-size:.6rem;margin-top:.3rem}.reference strong{font:600 1.7rem var(--font-numeric)}.greeks,.scenario-metrics{display:grid;grid-template-columns:1fr 1fr;margin:1rem 0;gap:0 1rem}.greeks>div,.scenario-metrics>div{padding:.9rem 0;border-bottom:1px solid var(--color-line)}dt{font-size:.65rem;color:var(--color-ink-secondary);line-height:1.5}dd{margin:.5rem 0 0;font:500 .9rem var(--font-numeric)}.model-notes{font-size:.7rem;line-height:1.9;margin-top:1.1rem}.model-notes summary{cursor:pointer;color:var(--color-accent)}.model-notes p{color:var(--color-ink-secondary)}.assumptions{display:flex;align-items:end;gap:.6rem;flex-wrap:wrap}.assumptions label{flex:1;min-width:6rem}.assumptions input{width:100%}.assumptions button{background:var(--color-accent);color:white;border-color:var(--color-accent)}.scenario-inputs{display:flex;gap:1rem;margin:1rem 0}.scenario-inputs label{flex:1;min-width:0}.scenario-inputs input{width:100%}.scenario-panel svg{display:block;width:100%;overflow:visible;margin:1.5rem 0}.axis{stroke:var(--color-line-strong);stroke-width:1}.zero{stroke:var(--color-line-strong);stroke-dasharray:4 4}.payoff{stroke:var(--color-accent);stroke-width:2.5;fill:none;stroke-linejoin:round}.scenario-panel svg text{fill:var(--color-ink-secondary);font:10px var(--font-numeric)}.notice{background:var(--color-warning-soft);color:var(--color-warning);padding:.8rem 1rem;border-radius:.4rem;font-size:.73rem;line-height:1.8;margin:.8rem}.risk-panel .notice,.scenario-panel .notice{margin:.8rem 0}.notice button{border:0;background:none;text-decoration:underline;color:var(--color-accent)}.empty{padding:2.5rem 1rem;text-align:center;font-size:.8rem;color:var(--color-ink-secondary);line-height:1.9}.source-note{font-size:.65rem;line-height:1.9;color:var(--color-ink-tertiary);margin:0}.warning{color:var(--color-positive)}@media(max-width:1100px){.risk-layout{grid-template-columns:1fr}.underlying-strip p{margin-left:0}}@media(max-width:650px){.options-intro{align-items:start;flex-direction:column}.filters{padding:.8rem;gap:.7rem}.filters>label{min-width:0;flex:1}.filters>.chain-select{flex-basis:100%}.risk-panel,.scenario-panel{padding:1rem}.underlying-strip{gap:.8rem;padding:1rem}.chain-table{font-size:.65rem}.chain-table td{padding:.3rem}.greeks,.scenario-metrics{gap:0 .8rem}}
</style>

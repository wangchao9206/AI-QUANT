<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {ArrowDownToLine,ArrowUpRight,FlaskConical,RefreshCw} from 'lucide-vue-next'
import Pagination from '../components/Pagination.vue'
import ResearchReport from '../components/ResearchReport'
import ResearchEquity from '../components/ResearchEquity.vue'
import {researchLibrary as api,type ResearchCatalog,type Study,type Run,type RunDetail,type Observation} from '../services/researchLibrary'

const route=useRoute(),router=useRouter()
const catalog=ref<ResearchCatalog>(),study=ref<Study>(),error=ref(''),loading=ref(false)
const tab=ref('overview'),tabs=[['overview','研究概览'],['journal','失败与改进'],['runs','场景与逐笔'],['report','完整报告'],['observation','观察账本'],['downloads','证据下载']]
const rows=ref<Run[]>([]),total=ref(0),page=ref(1),runsBusy=ref(false),runsError=ref('')
const filters=ref<Record<string,string>>({}),selectedRun=ref<RunDetail>(),runBusy=ref(false),runError=ref(''),tradePage=ref(1)
const observer=ref<Observation>(),observerBusy=ref(false),observerError=ref('')
let selection=0,listRequest=0,detailRequest=0
const stageNames:Record<string,string>={DEVELOPMENT:'开发期',VALIDATION:'2024—2025 检验',FINAL:'2026 检验'}
const modeNames:Record<string,string>={BASE:'原规则',QUIET_FILTER:'低波动过滤',PAYOFF_HORIZON:'收益目标修正',RANGE_GATE:'横盘入场',REGIME_EXIT:'状态失效退出',SHOCK_PAUSE:'波动扩张暂停'}
const familyNames=computed<Record<string,string>>(()=>({BREAKOUT:'顺势区间突破',PULLBACK:'顺势回撤',REVERSION:'均值回归',RANGE_REVERSION:'区间位置反转',BAND_REVERSION:'均值回归',GAP_FADE:'跳空失败回归',...Object.fromEntries((study.value?.journal??[]).map(j=>[j.family,j.name]))}))
const stages=computed(()=>study.value?.id==='daily-screen'?{...stageNames,VALIDATION:'2025 诊断检验'}:stageNames)
const visibleTabs=computed(()=>tabs.filter(t=>t[0]!=='observation'||study.value?.observation))
const trades=computed(()=>selectedRun.value?.trades.slice((tradePage.value-1)*10,tradePage.value*10)??[])
const broadComparisons=computed(()=>{
  if(study.value?.id!=='daily-screen')return []
  const v=study.value.results.validation??{}
  return Object.entries(v).flatMap(([family,cap]:[string,any])=>Object.entries(cap['1000000']??{}).map(([cost,metrics])=>({family,cost,metrics:metrics as Record<string,number>})))
})
const money=(value:number)=>Number(value).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})
const pct=(value:number)=>`${value>0?'+':''}${Number(value).toFixed(3)}%`
const size=(value:number)=>value>1024*1024?`${(value/1024/1024).toFixed(2)} MB`:`${(value/1024).toFixed(1)} KB`
const asset=(name:string,download=false)=>study.value?api.asset(study.value.id,study.value.revision,name,download):''
const variant=(run:Run)=>[modeNames[run.mode??run.repair??'']??'',run.scale===undefined?`周期 ${run.period} / 止损 ${run.stop}`:`尺度 ${run.scale}`,run.direction&&run.direction!=='BOTH'?run.direction:'',run.delay?'延迟一日':''].filter(Boolean).join(' · ')

async function selectStudy(id:string){await router.replace({path:'/research',query:{study:id}})}
async function loadStudy(){
  if(!catalog.value)return
  const request=++selection
  const id=typeof route.query.study==='string'?route.query.study:catalog.value.studies[0]!.id
  if(!catalog.value.studies.some(s=>s.id===id)){error.value='找不到这个研究批次，请从下方选择。';study.value=undefined;loading.value=false;return}
  loading.value=true;error.value='';study.value=undefined;selectedRun.value=undefined;rows.value=[];observer.value=undefined;observerBusy.value=false;runBusy.value=false;runsBusy.value=false;runError.value='';observerError.value='';tab.value='overview';++listRequest;++detailRequest
  try{
    const next=await api.detail(id,catalog.value.revision)
    if(request!==selection)return
    study.value=next;page.value=1;filters.value={stage:'VALIDATION',family:next.defaultFamily,capital:'1000000',cost:'1'}
  }catch(e){if(request===selection)error.value=e instanceof Error?e.message:'研究资料读取失败'}finally{if(request===selection)loading.value=false}
}
async function load(){loading.value=true;error.value='';try{catalog.value=await api.catalog();await loadStudy()}catch(e){error.value=e instanceof Error?e.message:'目录读取失败';loading.value=false}}
async function loadRuns(){
  const current=study.value;if(!current)return
  const token=++listRequest;runsBusy.value=true;runsError.value=''
  try{const result=await api.runs(current.id,current.revision,{page:page.value,page_size:20,...Object.fromEntries(Object.entries(filters.value).filter(([,v])=>v!==''))});if(token===listRequest){rows.value=result.items;total.value=result.total}}
  catch(e){if(token===listRequest){rows.value=[];runsError.value=e instanceof Error?e.message:'场景读取失败'}}finally{if(token===listRequest)runsBusy.value=false}
}
async function openRun(id:number){
  const current=study.value;if(!current)return
  tab.value='runs';const token=++detailRequest;runBusy.value=true;runError.value='';selectedRun.value=undefined
  try{const result=await api.run(current.id,current.revision,id);if(token===detailRequest){selectedRun.value=result;tradePage.value=1}}
  catch(e){if(token===detailRequest)runError.value=e instanceof Error?e.message:'账本读取失败'}finally{if(token===detailRequest)runBusy.value=false}
}
async function loadObserver(){
  const token=selection;observerBusy.value=true;observerError.value=''
  try{const result=await api.observation();if(token===selection)observer.value=result}catch(e){if(token===selection)observerError.value=e instanceof Error?e.message:'观察账本读取失败'}finally{if(token===selection)observerBusy.value=false}
}
watch(()=>route.query.study,()=>void loadStudy())
watch(filters,()=>{page.value=1;if(tab.value==='runs')void loadRuns()},{deep:true})
watch(page,()=>{if(tab.value==='runs')void loadRuns()})
watch(tab,value=>{if(value==='runs')void loadRuns();if(value==='observation')void loadObserver()})
onMounted(()=>void load())
</script>

<template>
  <div class="library">
    <section class="research-hero">
      <div><span class="eyebrow">INDEPENDENT RESEARCH / 自主研究档案</span><h2>研究市场，也记录每一次失败。</h2><p>从真实日线出发，把假设、交易、亏损和改进过程留在同一份档案里。当前重点：上期所燃料油 FU。</p><RouterLink to="/books">阅读与思想：书籍感悟 <ArrowUpRight :size="14"/></RouterLink></div>
      <div class="hero-count"><strong>{{catalog?.totalRuns.toLocaleString()??'—'}}</strong><span>已保存模拟场景</span><small>{{catalog?.studies.length??'—'}} 个研究批次 · {{catalog?.qualifiedCount??'—'}} 个通过全部门槛</small></div>
    </section>
    <p v-if="error" role="alert" class="notice">{{error}} <button @click="load">重新读取</button></p>
    <nav v-if="catalog" class="study-rail" aria-label="研究批次">
      <button v-for="(item,index) in catalog.studies" :key="item.id" :aria-pressed="study?.id===item.id" @click="selectStudy(item.id)"><span class="study-number">0{{catalog.studies.length-index}} / {{item.badge}}</span><strong>{{item.title}}</strong><span>{{item.subtitle}}</span><small>{{item.count}} 个场景 <ArrowUpRight :size="14"/></small></button>
    </nav>
    <p v-if="loading" role="status" class="empty">正在读取已保存的研究证据…</p>
    <template v-if="study">
      <section class="study-heading"><div><span class="eyebrow">{{study.badge}} / 截至 {{catalog?.date}}</span><h2>{{study.title}}</h2><p>{{study.scope}}</p></div><span class="status"><FlaskConical :size="15"/> 尚未通过有效性门槛</span></section>
      <p class="conclusion">{{study.conclusion}}</p>
      <nav class="tabs" aria-label="研究内容"><button v-for="item in visibleTabs" :key="item[0]" :aria-current="tab===item[0]?'page':undefined" @click="tab=item[0]!">{{item[1]}}</button></nav>

      <section v-if="tab==='overview'" class="panel">
        <header><div><h3>让结果接受核查</h3><p>收益率为整个窗口累计净收益，已经计入模型中的手续费与滑点。点击记录可查看单场景账本。</p></div><button @click="tab='report'">阅读完整研究 <ArrowUpRight :size="14"/></button></header>
        <div class="principles"><div><b>时间顺序</b><p>{{study.id==='daily-screen'?'先开发，再看 2025 诊断；2026 未打开。':'开发 2019—2023；后续 2024—2025；最后 2026。'}}<span v-if="study.id==='fu-regime'">本轮在前轮结果之后设计，所有历史窗口都已使用。</span></p></div><div><b>真实执行边界</b><p>完成日线生成信号，下一根开盘模拟成交；真实交割合约执行、换月平仓。跳空可超出计划风险预算。</p></div><div><b>资金与风险</b><p>1 万 / 10 万 / 100 万资金分别试验。每笔风险预算 0.5%，整数手取整；资金不足一手时保留零成交结果。</p></div></div>
        <p class="scope-note" v-if="study.id==='fu-regime'">表中保留三种修正的对照；开发期固定的是“状态失效退出”。不能看过 2026 后再把其他修正改称胜出策略。</p>
        <p class="scope-note" v-else-if="study.id==='fu-mechanisms'">表中是开发期预先固定的三个候选。16 类机制及其 144 个配置可在失败日志与全部场景中查看。</p>
        <p class="scope-note" v-else>下面是每个品种独立配置 100 万元的账户均值，39 个账户共需 3900 万元；不是 100 万元组合。没有打开 2026 留出期。</p>
        <div class="table-scroll" v-if="study.id!=='daily-screen'"><table><thead><tr><th>机制 / 修正</th><th>窗口</th><th>成本</th><th>累计净收益</th><th>最大收盘回撤</th><th>平仓笔数</th><th>账本</th></tr></thead><tbody><tr v-for="row in study.comparisons" :key="row.id"><td><strong>{{familyNames[row.family]??row.family}}</strong><small>{{modeNames[row.mode??row.repair??'']}}</small></td><td>{{stages[row.stage]??row.stage}}</td><td>{{row.cost}} 倍</td><td :class="row.metrics.returnPct>0?'gain':'loss'">{{pct(row.metrics.returnPct)}}</td><td>{{row.metrics.maxDrawdownPct.toFixed(3)}}%</td><td>{{row.metrics.closedTrades}}</td><td><button @click="openRun(row.id)" :aria-label="`查看场景 ${row.id} 账本`">查看 ↗</button></td></tr></tbody></table></div>
        <div class="table-scroll" v-else><table><thead><tr><th>机制</th><th>成本</th><th>独立账户平均收益</th><th>有交易账户</th><th>盈利账户</th><th>总平仓笔数</th></tr></thead><tbody><tr v-for="row in broadComparisons" :key="row.family+row.cost"><td>{{familyNames[row.family]}}</td><td>{{row.cost}} 倍</td><td :class="row.metrics.meanReturnPct!>0?'gain':'loss'">{{pct(row.metrics.meanReturnPct!)}}</td><td>{{row.metrics.activeAccounts}} / {{row.metrics.accounts}}</td><td>{{row.metrics.positiveAccounts}}</td><td>{{row.metrics.closedTrades}}</td></tr></tbody></table></div>
        <p class="scope-note">历史每日费率、平今差异、保证金变动、涨跌停及排队信息不完整。这里是有条件的历史执行模拟；统计场景数量包含参数、资金和成本对照，不代表独立发现数量。</p>
      </section>

      <section v-if="tab==='journal'" class="panel">
        <header><div><h3>失败不是删掉一条曲线</h3><p>保留最初假设、诊断原因和后续改动。完整计算证据可以下载核对。</p></div></header>
        <div v-if="study.journal.length" class="journal-grid"><details v-for="item in study.journal" :key="item.family"><summary><span>{{item.name}}</span><b :class="item.base.returnPct>0?'gain':'loss'">{{pct(item.base.returnPct)}}</b></summary><p>{{item.hypothesis}}</p><p class="scope-note">原规则 · 100 万元 · 2019—2023 开发期 · {{item.base.closedTrades}} 笔</p><ul><li v-for="reason in item.failureReasons" :key="reason">{{reason}}</li></ul><p><strong>经验：</strong>{{item.lesson}}</p><details><summary>两种修正的原始记录</summary><pre>{{JSON.stringify(item.repairs,null,2)}}</pre></details><button @click="filters.family=item.family;tab='runs'">核对全部场景 ↗</button></details></div>
        <template v-else-if="study.id==='fu-regime'"><div class="lesson-list"><article><span>01 / 从亏损归因出发</span><h4>横盘门控不是通用解药</h4><p>两类反转机制加入横盘门控后，开发期的低趋势交易表现并不一致。区间反转与均值回归保留为正负对照，不能只留有效片段。</p></article><article><span>02 / 修正也会失败</span><h4>允许状态退出，仍会跨窗口失效</h4><p>固定区间反转 / 状态失效退出后，100 万元基准账户开发期 +1.397%，2024—2025 为 −0.422%，2026 为 −0.831%。4 笔末期交易也不足以支持强结论。</p></article><article><span>03 / 下一步的边界</span><h4>冻结规则，等新数据检验</h4><p>不能再把已反复看过的年份称为新样本外证据。观察账本从冻结日之后按新增完成日线推进；期限结构与原油驱动目前只是后续研究方向。</p></article></div><details><summary>开发期选择和各窗口原始结果</summary><pre>{{JSON.stringify(study.results,null,2)}}</pre></details></template>
        <template v-else><div class="lesson-list"><article><span>01 / 数据先过关</span><h4>隔离三个品种的数据冲突</h4><p>M0、CJ0、LC0 存在 27 个换月新腿与对应日线开盘不一致的日期，已从本轮合格池隔离。原始数据保留，没有人为补出盈利。</p></article><article><span>02 / 样本不足也是结论</span><h4>开发期 19 笔，不能跳过门槛</h4><p>开发期选择顺势回撤，但只有 19 笔平仓，未通过成交数门槛。2025 的微小账户均值和单品种贡献不能证明普遍有效。</p></article><article><span>03 / 资金决定可执行性</span><h4>零成交不能被算作稳定策略</h4><p>在本轮保守风险约束下，1 万元账户不足以按预算开一手。结论只对应这些规则和规格，不等于所有小资金都无法交易。</p></article></div><details><summary>原始筛选门槛和结果</summary><pre>{{JSON.stringify(study.results,null,2)}}</pre></details></template>
      </section>

      <section v-if="tab==='runs'" class="panel">
        <header><div><h3>每个场景都能回到交易</h3><p>包含亏损、成本压力、邻近参数和零成交。这里展示独立账户，窗口末有假设清算。</p></div><button @click="filters={}">清除筛选</button></header>
        <div class="filters"><label v-for="(label,key) in {stage:'窗口',family:'机制',capital:'初始资金',cost:'成本倍数',symbol:'品种'}" :key="key">{{label}}<select v-model="filters[key]"><option value="">全部</option><option v-for="value in study.filters[key]" :key="value" :value="String(value)">{{key==='stage'?stages[value]??value:key==='family'?familyNames[value]??value:key==='capital'?`${Number(value)/10000} 万元`:value}}</option></select></label></div>
        <p v-if="runsError" role="alert" class="notice">{{runsError}} <button @click="loadRuns">重试</button></p><p v-if="runsBusy" role="status" class="scope-note">正在读取场景…</p>
        <div class="table-scroll"><table><thead><tr><th>机制 / 参数</th><th>窗口 / 品种</th><th>资金 / 成本</th><th>累计净收益</th><th>平仓笔数</th><th>明细</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id" :class="{'selected-row':selectedRun?.id===row.id}"><td><strong>{{familyNames[row.family]??row.family}}</strong><small>{{variant(row)}}</small></td><td>{{stages[row.stage]??row.stage}}<small>{{row.symbol??'FU0'}}</small></td><td>{{row.capital/10000}} 万元<small>{{row.cost}} 倍成本</small></td><td :class="row.metrics.returnPct>0?'gain':row.metrics.returnPct<0?'loss':''">{{pct(row.metrics.returnPct)}}</td><td>{{row.metrics.closedTrades}}</td><td><button @click="openRun(row.id)">账本 #{{row.id}} ↗</button></td></tr></tbody></table></div><p v-if="!runsBusy&&!rows.length&&!runsError" class="empty">没有满足筛选条件的场景。</p>
        <Pagination v-model:page="page" :total="total" :page-size="20" label="研究场景分页"/>
        <p v-if="runBusy" role="status">正在读取逐笔账本…</p><p v-if="runError" role="alert" class="notice">{{runError}}</p>
        <article v-if="selectedRun" class="run-detail"><header><div><span class="eyebrow">场景 #{{selectedRun.id}} / 单账户</span><h3>{{familyNames[selectedRun.family]??selectedRun.family}} · {{stages[selectedRun.stage]??selectedRun.stage}}</h3><p>{{variant(selectedRun)}} · {{selectedRun.symbol??'FU0'}} · {{selectedRun.capital/10000}} 万元 · {{selectedRun.cost}} 倍成本</p></div><button @click="selectedRun=undefined">收起账本</button></header>
          <div class="metric-strip"><div><span>累计净收益</span><strong>{{pct(selectedRun.metrics.returnPct)}}</strong></div><div><span>期末权益</span><strong>¥ {{money(selectedRun.metrics.finalEquity)}}</strong></div><div><span>最大收盘回撤</span><strong>{{selectedRun.metrics.maxDrawdownPct.toFixed(3)}}%</strong></div><div><span>平仓笔数</span><strong>{{selectedRun.metrics.closedTrades}}</strong></div></div>
          <ResearchEquity :curve="selectedRun.curve" :initial="selectedRun.metrics.initialCash"/>
          <p class="scope-note">可用日期滑块逐日查看。曲线为账户权益；表中是平仓交易。WINDOW_END_LIQUIDATION 表示窗口末假设清算，并非真实委托成交。</p>
          <div class="table-scroll" v-if="selectedRun.trades.length"><table><thead><tr><th>合约 / 方向</th><th>入场日 / 价</th><th>出场日 / 价</th><th>手数</th><th>扣费净盈亏</th><th>出场原因</th></tr></thead><tbody><tr v-for="(trade,index) in trades" :key="index"><td>{{trade.contract}}<small>{{trade.direction===1?'做多':'做空'}}</small></td><td>{{trade.entryDate}}<small>{{trade.entryPrice}}</small></td><td>{{trade.exitDate}}<small>{{trade.exitPrice}}</small></td><td>{{trade.lots}}</td><td :class="trade.netPnl>0?'gain':'loss'">{{money(trade.netPnl)}}</td><td>{{trade.exitReason}}</td></tr></tbody></table></div><p v-else class="empty">本场景没有成交，风险预算不足等拒单原因保留在计算明细中。</p>
          <Pagination v-model:page="tradePage" :total="selectedRun.trades.length" :page-size="10" label="逐笔交易分页"/>
          <details><summary>执行指标和拒单计数</summary><pre>{{JSON.stringify(selectedRun.metrics,null,2)}}</pre></details>
          <details><summary>逐日决策记录（{{selectedRun.decisions.length}} 条）</summary><pre>{{JSON.stringify(selectedRun.decisions,null,2)}}</pre></details>
        </article>
      </section>

      <section v-if="tab==='report'" class="panel report-panel"><header><div><h3>完整研究报告</h3><p v-if="study.id!=='daily-screen'">燃油报告合并记录两轮研究；各批次场景在上方分别查询。</p><p>报告与原始证据保留，不用摘要替代失败与局限。</p></div><a :href="asset('report.md',true)">下载原文 <ArrowDownToLine :size="14"/></a></header><ResearchReport :text="study.report" :links="study.reportLinks" :asset="name=>asset(name)"/></section>

      <section v-if="tab==='observation'" class="panel">
        <header><div><h3>FU-R2 · 新数据诊断观察</h3><p>区间位置反转 / 状态失效退出。规则已冻结；历史模拟与这里的冻结后记录分别呈现。</p></div><button @click="loadObserver" :disabled="observerBusy"><RefreshCw :size="14"/>{{observerBusy?'读取中':'刷新已保存记录'}}</button></header>
        <p v-if="observerError" role="alert" class="notice">{{observerError}}</p>
        <template v-if="observer"><p class="observer-note">{{observer.message}} 当前未开启后台自动更新；数据截止日为 {{observer.state.asOf}}。</p><div class="metric-strip"><div><span>数据截止 / 修订</span><strong>{{observer.state.asOf}}</strong><small>修订 {{observer.state.revision}}</small></div><div><span>诊断账户权益</span><strong>¥ {{money(observer.state.equity)}}</strong></div><div><span>冻结后平仓记录</span><strong>{{observer.state.trades.length}} 笔</strong></div><div><span>已提交实盘委托</span><strong>{{observer.state.ordersSubmittedToBroker}} 笔</strong></div></div>
          <div class="observer-grid"><article><span>当前持仓</span><h4>{{observer.state.position?'有诊断持仓':'空仓'}}</h4><pre v-if="observer.state.position">{{JSON.stringify(observer.state.position,null,2)}}</pre><p>现金 ¥ {{money(observer.state.cash)}}</p></article><article><span>最新完成日线信号</span><h4>{{observer.state.nextSignal.signal==='HOLD'?'观望 / HOLD':observer.state.nextSignal.signal}}</h4><p>{{observer.state.nextSignal.reason}}</p><p>计划最多 {{observer.state.nextSignal.maxPlannedEntryLots}} 手；信号不代表已成交。</p></article></div>
          <ResearchEquity :curve="observer.state.curve" :initial="Number(observer.state.config.initialCash)"/>
          <p class="scope-note">本账本根据完成日线模拟执行，不接券商。历史终点的假设清算已撤销，持仓可跨更新延续。任何盈利有效性仍需新数据检验。</p>
          <details><summary>冻结规则与风险参数</summary><pre>{{JSON.stringify(observer.state.config,null,2)}}</pre></details><details><summary>最新节点计算记录</summary><pre>{{JSON.stringify(observer.state.nextSignal.nodeTrace,null,2)}}</pre></details><details><summary>冻结后完整交易与事件</summary><pre>{{JSON.stringify({trades:observer.state.trades,events:observer.state.events},null,2)}}</pre></details>
          <p class="scope-note hash">规则指纹 {{observer.state.configHash}}</p><a href="/api/v1/research/studies/fu-regime/observation?download=true">下载当前观察账本 <ArrowDownToLine :size="14"/></a>
        </template>
      </section>

      <section v-if="tab==='downloads'" class="panel"><header><div><h3>把结论还原为证据</h3><p>包含研究协议、全部场景汇总、压缩逐笔账本、配置、审计和图表。规则 JSON 是研究配置，资金与信号语义不等同于模拟交易工作流。</p></div></header><div class="download-list"><a v-for="file in study.assets" :key="file.name" :href="asset(file.name,true)"><ArrowDownToLine :size="17"/><div><strong>{{file.name}}</strong><small class="hash">SHA256 {{file.sha256}}</small></div><span>{{size(file.size)}}</span></a></div><p class="scope-note">发布版本 {{study.revision}}。原始冻结研究不会被页面刷新修改；观察账本单独读取最新保存状态。</p></section>
    </template>
  </div>
</template>

<style scoped>
.library{display:grid;gap:1.4rem;min-width:0}.research-hero{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2rem;padding:1.4rem 0 1.8rem;border-bottom:1px solid var(--color-line)}.eyebrow{font:500 .63rem var(--font-numeric);letter-spacing:.11em;color:var(--color-accent)}.research-hero h2{font:500 clamp(1.8rem,3.3vw,3rem)/1.3 var(--font-display);letter-spacing:-.04em;margin:.8rem 0}.research-hero p{max-width:43rem;color:var(--color-ink-secondary);font-size:.81rem;line-height:1.9}.library a{color:var(--color-accent);text-decoration:none}.research-hero a{display:inline-flex;gap:.3rem;align-items:center;font-size:.72rem;margin-top:.6rem}.hero-count{display:flex;flex-direction:column;justify-content:center;padding-left:2rem;border-left:1px solid var(--color-line);gap:.5rem}.hero-count strong{font:400 3.4rem var(--font-numeric);letter-spacing:-.08em}.hero-count span{font-size:.76rem}.hero-count small{font-size:.62rem;color:var(--color-ink-tertiary)}.study-rail{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem}.study-rail button{text-align:left;display:flex;flex-direction:column;align-items:stretch;gap:.6rem;padding:1.1rem;background:var(--color-surface);border:1px solid var(--color-line);border-radius:.6rem;color:var(--color-ink);cursor:pointer;min-width:0}.study-rail button[aria-pressed=true]{border-color:var(--color-accent);background:var(--color-accent-soft);box-shadow:inset 3px 0 var(--color-accent)}.study-number{font:.64rem var(--font-numeric);color:var(--color-accent)}.study-rail strong{font-size:.9rem}.study-rail button>span:not(.study-number){font-size:.72rem;color:var(--color-ink-secondary)}.study-rail small{display:flex;justify-content:space-between;align-items:center;font-size:.64rem;color:var(--color-ink-tertiary);padding-top:.5rem}.study-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-top:.5rem}.study-heading h2{font:500 1.6rem var(--font-display);margin:.7rem 0 .4rem}.study-heading p{font-size:.73rem;color:var(--color-ink-secondary);margin:0}.status{display:flex;align-items:center;gap:.4rem;font-size:.7rem;color:var(--color-warning);background:var(--color-warning-soft);padding:.65rem .85rem;border-radius:2rem}.conclusion{border-left:2px solid var(--color-accent);padding:.25rem 1rem;font-size:.85rem;line-height:1.9;margin:0}.tabs{display:flex;gap:1.5rem;overflow:auto;border-bottom:1px solid var(--color-line)}.tabs button{white-space:nowrap;border:0;border-bottom:2px solid transparent;background:none;padding:.75rem 0;color:var(--color-ink-secondary);font-size:.76rem;cursor:pointer}.tabs button[aria-current]{color:var(--color-accent);border-color:var(--color-accent)}.panel{padding:1.4rem;background:var(--color-surface-raised);border:1px solid var(--color-line);border-radius:.7rem;min-width:0}header{display:flex;justify-content:space-between;align-items:start;gap:1rem}header h3{font-size:1rem;margin:0}header p{font-size:.73rem;color:var(--color-ink-secondary);line-height:1.9;max-width:50rem;margin:.5rem 0 0}.library button:not(.study-rail button,.tabs button){cursor:pointer}.panel button,.notice button{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;border:1px solid var(--color-line);border-radius:.4rem;background:transparent;color:var(--color-accent);padding:.4rem .55rem;font-size:.7rem}.panel header>button,.panel header>a{flex-shrink:0;font-size:.7rem;display:flex;gap:.4rem;align-items:center}.principles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1.4rem;padding:1.2rem 0;margin:1rem 0;border-top:1px solid var(--color-line);border-bottom:1px solid var(--color-line)}.principles b{font-size:.75rem}.principles p{font-size:.72rem;line-height:1.9;color:var(--color-ink-secondary);margin-bottom:0}.scope-note{font-size:.69rem;color:var(--color-ink-tertiary);line-height:1.9}.table-scroll{max-width:100%;overflow:auto;margin-top:1rem}table{border-collapse:collapse;width:100%;font-size:.71rem;text-align:left}th{color:var(--color-ink-tertiary);font-weight:500;font-size:.64rem;background:var(--color-surface)}td,th{padding:.8rem .7rem;border-bottom:1px solid var(--color-line);white-space:nowrap}td strong{font-weight:500}td small{display:block;color:var(--color-ink-tertiary);font-size:.62rem;line-height:1.8;margin-top:.25rem}.gain{color:#a24635}.loss{color:#24736b}.selected-row{background:var(--color-accent-soft)}.journal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem;margin-top:1.2rem}.journal-grid>details{padding:1rem;border:1px solid var(--color-line);border-radius:.5rem;min-width:0}.journal-grid>details>summary{display:flex;align-items:center;justify-content:space-between;gap:.7rem}.journal-grid p,.journal-grid li{font-size:.74rem;line-height:1.9;color:var(--color-ink-secondary)}summary{cursor:pointer;font-size:.77rem;line-height:1.9}details{margin:.8rem 0}pre{background:var(--color-surface);padding:.8rem;font:.68rem/1.8 var(--font-numeric);max-height:27rem;overflow:auto;border:1px solid var(--color-line);border-radius:.4rem;white-space:pre-wrap;overflow-wrap:anywhere}.lesson-list{display:grid;gap:1rem;margin:1.4rem 0}.lesson-list article{padding:1.2rem;border-left:2px solid var(--color-line);background:var(--color-surface)}.lesson-list span{font-size:.66rem;color:var(--color-accent)}h4{font-size:.9rem;margin:.6rem 0}.lesson-list p{font-size:.77rem;line-height:1.9;color:var(--color-ink-secondary);margin-bottom:0}.filters{display:flex;flex-wrap:wrap;gap:.8rem;margin:1.2rem 0}.filters label{display:grid;gap:.4rem;flex:1;min-width:8rem;font-size:.66rem;color:var(--color-ink-secondary)}select{min-width:0;max-width:100%;padding:.6rem;border:1px solid var(--color-line);border-radius:.4rem;background:var(--color-surface);color:var(--color-ink);font-size:.73rem}.run-detail{margin-top:1.4rem;border-top:2px solid var(--color-accent);padding-top:1.4rem;min-width:0}.metric-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem;border-block:1px solid var(--color-line);padding:1.2rem 0;margin:1.2rem 0}.metric-strip>div{display:grid;gap:.5rem}.metric-strip span{font-size:.65rem;color:var(--color-ink-tertiary)}.metric-strip strong{font:500 clamp(.85rem,1.5vw,1.15rem) var(--font-numeric);overflow-wrap:anywhere}.metric-strip small{font-size:.63rem;color:var(--color-ink-tertiary)}.notice,.observer-note{background:var(--color-warning-soft);color:var(--color-warning);border-radius:.4rem;padding:.9rem;font-size:.75rem;line-height:1.9}.empty{padding:1rem 0;font-size:.8rem;color:var(--color-ink-tertiary)}.observer-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.observer-grid article{background:var(--color-surface);padding:1rem;border:1px solid var(--color-line);border-radius:.5rem;min-width:0}.observer-grid span{font-size:.65rem;color:var(--color-ink-tertiary)}.observer-grid p{font-size:.73rem;line-height:1.9;color:var(--color-ink-secondary)}.panel>a{font-size:.75rem;display:inline-flex;gap:.4rem;align-items:center}.hash{overflow-wrap:anywhere;font-family:var(--font-numeric)}.download-list{margin-top:1.1rem}.download-list a{display:flex;align-items:center;gap:.8rem;padding:1rem 0;border-bottom:1px solid var(--color-line);min-width:0}.download-list a>div{flex:1;min-width:0}.download-list strong{font-size:.76rem;font-weight:500;overflow-wrap:anywhere}.download-list small{display:block;font-size:.58rem;color:var(--color-ink-tertiary);margin-top:.4rem}.download-list span{font:.65rem var(--font-numeric);white-space:nowrap;color:var(--color-ink-tertiary)}
:deep(.research-report){max-width:70rem;font-size:.81rem;line-height:2;color:var(--color-ink-secondary);overflow-wrap:anywhere}:deep(.research-report h2){font:500 1.7rem/1.5 var(--font-display);color:var(--color-ink);margin:1.5rem 0}:deep(.research-report h3){color:var(--color-ink);font-size:1.1rem;margin:2rem 0 .8rem}:deep(.research-report h4){color:var(--color-ink)}:deep(.research-report li){margin:.4rem 0}:deep(.research-report img){max-width:100%;height:auto;border:1px solid var(--color-line);border-radius:.5rem}:deep(.report-table){overflow:auto;max-width:100%}:deep(.research-report table){font-size:.72rem}:deep(.research-report th),:deep(.research-report td){padding:.7rem;border-bottom:1px solid var(--color-line);white-space:nowrap}:deep(.research-report code){font-family:var(--font-numeric);background:var(--color-surface);font-size:.73rem}:deep(.research-report pre){overflow:auto;max-width:100%;white-space:pre-wrap}
@media(max-width:1000px){.research-hero{grid-template-columns:1fr}.hero-count{border-left:0;border-top:1px solid var(--color-line);padding:1rem 0 0;display:grid;grid-template-columns:auto 1fr;align-items:end;column-gap:1rem}.hero-count strong{grid-row:span 2;font-size:2.7rem}.hero-count small{align-self:start}.principles{grid-template-columns:1fr;gap:.6rem}.principles p{margin-top:.4rem}.study-rail strong{font-size:.78rem}.study-heading{flex-wrap:wrap}.journal-grid{grid-template-columns:1fr}}
@media(max-width:650px){.library{gap:1rem}.study-rail{grid-template-columns:1fr}.study-rail button{padding:.85rem;gap:.4rem}.study-rail small{padding-top:0}.research-hero{padding-top:.5rem;gap:1rem}.panel{padding:1rem}.study-heading h2{font-size:1.4rem}.status{font-size:.65rem;padding:.5rem .7rem}.tabs{gap:1.2rem}.metric-strip{grid-template-columns:1fr 1fr}.observer-grid{grid-template-columns:1fr}header{flex-wrap:wrap}.download-list small{display:none}.download-list strong{font-size:.68rem}.hero-count small{font-size:.59rem}.journal-grid{gap:0}.filters label{min-width:calc(50% - 1rem)}.research-hero h2{font-size:1.9rem}}
</style>

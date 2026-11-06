<script setup lang="ts">
import {instrumentLabel} from '../../utils/instrumentNames'
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import ChanlunNavigation from './ChanlunNavigation.vue'
import ChanlunReader from '../../components/ChanlunReader.vue'
import {requestUuid} from '../../utils/requestId'
import {labApi,type LabDraft,type LabExperiment,type LabGroup,type LabSummary} from './lab'
const route=useRoute(),router=useRouter()
const group=ref<LabGroup>('THIRD'),cash=ref(1_000_000),busy=ref(false),loading=ref(false),error=ref('')
const current=ref<LabExperiment|null>(null),recent=ref<LabSummary[]>([]),selected=ref('NATIVE_BASE'),reader=ref(false),lesson=ref(20)
const report=computed(()=>current.value?.report),variant=computed(()=>report.value?.variants.find(v=>v.id===selected.value))
const labels:Record<string,string>={NATIVE_BASE:'自研 · 基础成本',NATIVE_DOUBLE_COST:'自研 · 双倍费用与滑点',NATIVE_DELAY_ONE:'自研 · 延后一根',RANGE_RETEST:'普通突破回踩',CHANNEL_BREAKOUT:'普通直接突破'}
const outcomes:Record<string,string>={FILLED:'已成交',POSITION_ALREADY_OPEN:'已有持仓',ROLL_DAY_NEW_ORDER_CANCELLED:'换月取消新单',EXIT_DAY_NO_REENTRY:'退出当日不再入场',CANDIDATE_INVALID_WHILE_WAITING:'等待期间候选失效',STRUCTURE_INVALID_WHILE_WAITING:'等待期间结构失效',STRUCTURE_INVALID_AT_OPEN:'开盘已失效',LIQUIDITY:'成交量不足',RISK_OR_MARGIN_BELOW_ONE_LOT:'风险或保证金不足一手',SIMULTANEOUS_CANDIDATES_SKIPPED:'同根多个候选全部跳过',OUTSIDE_EXECUTION_WINDOW:'窗口外无法成交',STOP:'止损',TARGET:'止盈',STRUCTURE_EXIT:'结构失效退出',OPPOSITE_EVENT:'反向事件',TIME_EXIT:'最长持有期限',ROLL_EXIT:'换月平仓',MARGIN_LIQUIDATION:'保证金不足清仓',WINDOW_END_LIQUIDATION:'窗口末平仓'}
const money=(n:number)=>n.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})
const name=(id:string)=>labels[id]??id,reason=(id:string)=>outcomes[id]??id
let alive=true,generation=0,timer:number|undefined,polls=0,command:LabDraft|null=null
function stop(){if(timer!==undefined)window.clearTimeout(timer);timer=undefined}
function accept(value:LabExperiment){
  current.value=value
  if(value.status==='RUNNING'&&alive&&polls<90){stop();timer=window.setTimeout(()=>{polls++;void restore(value.id,false)},2000)}
  else stop()
}
async function restore(id:string,showLoading=true){
  const version=++generation
  if(showLoading){loading.value=true;busy.value=false;current.value=null;error.value='';stop();polls=0}
  try{const value=await labApi.get(id);if(alive&&version===generation)accept(value)}
  catch(e){if(alive&&version===generation){stop();error.value=e instanceof Error?e.message:'实验读取失败'}}
  finally{if(alive&&version===generation)loading.value=false}
}
async function refreshRecent(){try{recent.value=await labApi.recent()}catch(e){error.value=e instanceof Error?e.message:'实验列表读取失败'}}
async function create(){
  if(busy.value||loading.value)return
  const version=++generation;stop();busy.value=true;error.value='';polls=0
  if(!command||command.group!==group.value||command.initialCash!==cash.value)command={clientRequestId:requestUuid(),group:group.value,initialCash:cash.value}
  try{
    const value=await labApi.create(command)
    if(!alive||version!==generation)return
    accept(value);command=null;await router.replace({path:'/chanlun/lab',query:{experiment:value.id}});await refreshRecent()
  }catch(e){if(alive&&version===generation)error.value=(e instanceof Error?e.message:'实验未完成')+'；重试沿用同一请求编号。'}
  finally{if(alive&&version===generation)busy.value=false}
}
function open(id:string){void router.push({path:'/chanlun/lab',query:{experiment:id}})}
function book(evidence:Record<string,unknown>){const refs=evidence.referenceLessons;lesson.value=Array.isArray(refs)&&typeof refs[0]==='number'?refs[0]:20;reader.value=true}
watch(()=>route.query.experiment,id=>{if(typeof id==='string'&&id!==current.value?.id)void restore(id)})
onMounted(async()=>{await refreshRecent();if(typeof route.query.experiment==='string')await restore(route.query.experiment)})
onUnmounted(()=>{alive=false;generation++;stop()})
</script>
<template>
  <main class="chan-lab">
    <ChanlunNavigation active="lab"/>
    <header><p class="eyebrow">策略实验 · 真实合约成本账本</p><h1>让候选点接受成交检验</h1><p>首次出现即入档，后续失效也保留。所有成本和对照情景同时展示，结果可恢复、可核对。</p></header>
    <form class="config" @submit.prevent="create">
      <label>候选范围<select v-model="group" :disabled="busy"><option value="THIRD">三类候选 B3 / S3</option><option value="ALL">一、二、三类全部候选</option></select></label>
      <label>初始资金<select v-model.number="cash" :disabled="busy"><option :value="100000">10 万元</option><option :value="500000">50 万元</option><option :value="1000000">100 万元</option></select></label>
      <button type="submit" :disabled="busy||loading">{{busy?'核算中…':'运行固定规则实验'}}</button>
    </form>
    <p class="scope">燃油冻结日线 · 2019—2026 · 下一根实际交割合约开盘撮合 · 历史开发样本，不能当作未见样本业绩</p>
    <p v-if="error" role="alert" class="error">{{error}}</p>
    <p v-if="loading" role="status">正在恢复实验…</p>
    <p v-else-if="current?.status==='RUNNING'" role="status">服务器正在核算；离开后可从历史记录恢复。</p>
    <p v-else-if="current?.status==='FAILED'" role="alert" class="error">{{current.error}}</p>
    <button v-if="current" :disabled="busy||loading" @click="restore(current.id)">刷新服务器记录</button>
    <section v-if="report" class="results">
      <h2>五个情景并列，保留亏损与成本敏感性</h2>
      <p>本次配置：{{report.config.group==='ALL'?'全部候选':'三类候选'}} · 初始 {{money(report.config.initialCash)}} 元 · {{report.config.window.join(' 至 ')}}。下表滑点已计入成交价，不能再从净损益重复扣除。</p>
      <div class="scroll"><table><caption>净损益含双边费用及滑点，研究模拟</caption><thead><tr><th>情景</th><th>净损益 / 元</th><th>最大回撤</th><th>平仓笔数</th><th>胜率</th><th>手续费 / 元</th><th>滑点成本 / 元</th></tr></thead><tbody>
        <tr v-for="v in report.variants" :key="v.id" :aria-selected="selected===v.id"><th><button @click="selected=v.id" :aria-pressed="selected===v.id">{{name(v.id)}}</button></th><td :class="v.metrics.netPnl<0?'loss':'gain'">{{money(v.metrics.netPnl)}}</td><td>{{v.metrics.maxDrawdownPct.toFixed(2)}}%</td><td>{{v.metrics.closedTrades}}</td><td>{{v.metrics.winRatePct.toFixed(1)}}%</td><td>{{money(v.metrics.fees)}}</td><td>{{money(v.metrics.slippageCost)}}</td></tr>
      </tbody></table></div>
      <section v-if="variant" class="detail"><h2>{{name(variant.id)}} · 逐笔账本</h2><p>初始资金 + 净损益 = {{money(variant.metrics.finalEquity)}} 元。超过计划风险预算的平仓 {{variant.metrics.overBudgetExits}} 笔；跳空与清仓成本可能使实际损失超出计划。</p>
        <div class="scroll"><table><thead><tr><th>入场 → 离场</th><th>交割合约</th><th>方向 / 手数</th><th>成交价</th><th>净损益 / 元</th><th>离场原因</th></tr></thead><tbody><tr v-for="(t,i) in variant.trades" :key="i"><td>{{t.entryDate}} → {{t.exitDate}}</td><td>{{instrumentLabel(t.contract)}}</td><td>{{t.direction>0?'多':'空'}} / {{t.lots}}</td><td>{{money(t.entryPrice)}} → {{money(t.exitPrice)}}</td><td :class="t.netPnl<0?'loss':'gain'">{{money(t.netPnl)}}</td><td>{{reason(t.exitReason)}}</td></tr><tr v-if="!variant.trades.length"><td colspan="6">该情景没有成交，继续保留候选与拒单记录。</td></tr></tbody></table></div>
        <details><summary>成交与未成交决策（{{variant.decisions.length+variant.excluded.length}} 条）</summary><ul><li v-for="(d,i) in [...variant.decisions,...variant.excluded]" :key="i">{{d.executionDate??`观察索引 ${d.confirmedIndex}`}} · {{d.source}} · {{reason(d.outcome)}}<span v-if="d.structureId"> · {{d.structureId}}</span></li></ul></details>
      </section>
      <details><summary>首次候选档案（{{report.candidateTape.length}} 条，包含后来失效者）</summary><ol><li v-for="c in report.candidateTape" :key="c.structureId">{{c.source}} · 端点 {{c.pivotDate??c.pivotIndex}} · 首次观察 {{c.firstObservationDate??c.confirmedIndex}} · 连续价失效边界 {{money(c.invalidation)}} · {{report.invalidationObservations[c.structureId]!==undefined?`后来失效，观察索引 ${report.invalidationObservations[c.structureId]}`:'窗口内未观察到失效'}} <button @click="book(c.evidence)">阅读对应原文</button><code>{{c.structureId}}</code></li></ol></details>
      <details open><summary>执行规则与研究限制</summary><ul><li v-for="a in report.assumptions" :key="a">{{a}}</li></ul></details>
      <details><summary>冻结版本与审计摘要</summary><dl><dt>配置摘要</dt><dd>{{report.configHash}}</dd><dt>自研结构规则摘要</dt><dd>{{report.config.profileHash}}</dd><dt>执行实现摘要</dt><dd>{{report.config.implementationHash}}</dd><dt>数据摘要</dt><dd>{{report.config.datasetHash}}</dd><dt>记录时间</dt><dd>{{current?.createdAt}}</dd></dl></details>
    </section>
    <section class="history"><h2>已保存的实验</h2><p v-if="!recent.length">尚无实验；点击运行后由服务器保存配置、账本与对照结果。</p><ul><li v-for="item in recent" :key="item.id"><button @click="open(item.id)" :disabled="busy">{{item.group==='ALL'?'全部候选':'三类候选'}} · {{money(item.initialCash)}} 元 · {{item.status==='SUCCEEDED'?'已完成':item.status==='RUNNING'?'核算中':'未完成'}} · {{item.createdAt}}</button></li></ul></section>
    <section v-if="reader" class="reader"><button @click="reader=false">收起原文</button><ChanlunReader :initial-chapter="lesson"/></section>
  </main>
</template>
<style scoped>
.chan-lab{max-width:1400px;margin:auto;color:#293b31}.eyebrow{font-size:.75rem;color:#7a725e;letter-spacing:.12em}h1{font-size:1.8rem;margin:.5rem 0}h2{font-size:1.05rem;margin:1.5rem 0 .8rem}header>p:last-child,.scope,.results>p,.detail>p{font-size:.85rem;line-height:1.8;color:#657066}.config{display:flex;gap:1rem;align-items:end;flex-wrap:wrap;margin-top:1.5rem;padding:1rem;background:#f0f1e8;border:1px solid #dedfd5;border-radius:.5rem}label{display:grid;gap:.45rem;font-size:.8rem}select,button{font:inherit;border:1px solid #c6cdbf;border-radius:.3rem;padding:.55rem .7rem;background:#fff;color:#293b31;cursor:pointer}button:disabled{opacity:.5;cursor:wait}button:focus-visible,select:focus-visible{outline:2px solid #9e784b;outline-offset:3px}.scroll{overflow:auto;border:1px solid #dedfd5;border-radius:.3rem}table{border-collapse:collapse;width:100%;white-space:nowrap;font-size:.78rem}th,td{text-align:left;padding:.7rem;border-bottom:1px solid #e6e8de}thead{background:#f0f1e8}caption{text-align:left;padding:.7rem;color:#657066}tbody tr[aria-selected=true]{background:#e8eee3}td.loss,.error{color:#aa4539}td.gain{color:#267052}details{margin:1rem 0;border-top:1px solid #dedfd5;padding-top:1rem;font-size:.8rem;line-height:1.8}summary{cursor:pointer;font-weight:600}li{margin:.4rem 0;overflow-wrap:anywhere}code{display:block;font-size:.68rem;color:#657066}dd{overflow-wrap:anywhere;margin:0 0 .7rem;font-family:monospace}.history ul{list-style:none;padding:0}.history button{text-align:left;font-size:.78rem}.reader{margin-top:1.5rem;border-top:1px solid #dedfd5;padding-top:1rem}@media(max-width:600px){h1{font-size:1.4rem}.config{align-items:stretch;flex-direction:column}.config>button{min-height:44px}}@media(pointer:coarse){button,select{min-height:44px}}
</style>

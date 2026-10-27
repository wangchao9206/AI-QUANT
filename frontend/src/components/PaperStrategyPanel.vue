<script setup lang="ts">
import {traceValue} from '../utils/workflowGraph'
import {computed} from 'vue'
import type {BacktestPresets,PaperSession,PaperSessionSummary} from '../services/api'
import {formatNumber,formatPct,formatTradingDate} from '../utils/format'
const props=defineProps<{current:PaperSession;presets:BacktestPresets|null;sessions:PaperSessionSummary[]}>()
defineEmits<{compare:[]}>()
const name=(id?:string)=>!id||id==='MANUAL'?'手动交易':props.presets?.strategies?.find(s=>s.id===id)?.name??id
const automatic=computed(()=>props.current.strategyId&&props.current.strategyId!=='MANUAL')
const states:Record<string,string>={LIVE:'交易中 · 可执行',CLOSED_CACHE:'休市 · 仅更新估值',STALE:'报价过期 · 暂不执行',WARMING:'行情准备中',DISCONNECTED:'行情断开',UNKNOWN:'交易状态待核验',CONTRACT_CHANGED:'执行合约已变更 · 暂停新增'}
const signals:Record<string,string>={BUY:'开多',SELL:'开空',FLATTEN:'平仓',HOLD:'等待',WARMING:'日线准备中'}
const compared=computed(()=>props.sessions.filter(s=>s.strategyId&&s.strategyId!=='MANUAL'))
</script>
<template>
  <section class="strategy-panel" aria-label="当前模拟策略">
    <header><div><span class="eyebrow">{{automatic?'STRATEGY EXPERIMENT':'MANUAL EXPERIMENT'}}</span><h3>{{current.strategyId==='WORKFLOW'?current.workflowName+' · v'+current.workflowVersion:name(current.strategyId)}}</h3></div><button type="button" @click="$emit('compare')">新建策略对照</button></header>
    <div class="strategy-facts"><span>{{current.mode==='HISTORICAL'?'历史回放':'实时仿真'}}</span><template v-if="automatic"><span>每次开仓 {{current.strategyLots}} 手</span><span v-if="current.strategyId!=='BUY_AND_HOLD'">保护 {{current.stopLossAtr}} ATR / 止盈 {{current.takeProfitAtr}} ATR</span></template><span>净收益 {{formatPct((current.equity/current.initialCash-1)*100)}}</span><span>最大回撤 {{formatNumber(current.maxDrawdownPct??0)}}%</span></div>
    <p v-if="current.mode==='LIVE'" class="market-state">{{states[current.marketState??'UNKNOWN']??current.marketState}}。{{current.executionMessage}}</p>
    <p v-if="automatic">策略与参数在创建时固定。{{current.mode==='HISTORICAL'?'单步或播放时按已知日线决策，下一根日线撮合。':'刷新或监测时按已完成日线决策；同根信号只执行一次，休市、过期行情不成交。监测仅在本页打开并启动时运行。'}} 保护单以真实交割合约 ATR 为尺度；日线同根双触及时优先止损。</p>
    <p v-if="current.strategyId==='HOLISTIC_14D'">融合策略只使用该时点可取得的日线维度，不回填当前新闻、气象等外部信息。</p>
    <details v-if="automatic" open><summary>策略决策记录 · 最近30条</summary><div class="table-wrap"><table><thead><tr><th>信号交易日</th><th>动作</th><th>依据 / 状态</th><th>日线数</th></tr></thead><tbody><tr v-for="row in current.strategyDecisions??[]" :key="row.signalTime"><td>{{formatTradingDate(row.signalTime)}}</td><td>{{signals[row.signal]??row.signal}}</td><td>{{row.reason}}<details v-if="row.nodeTrace?.length"><summary>节点计算与拦截原因</summary><div v-for="node in row.nodeTrace" :key="node.nodeId">{{node.label}} · {{node.status}} · {{traceValue(node.value)}}<br/>{{node.reason}}</div></details></td><td>{{row.historyCount}}</td></tr><tr v-if="!current.strategyDecisions?.length"><td colspan="4">尚未评估。历史试验点击单步/播放，实时试验刷新行情或启动策略监测。</td></tr></tbody></table></div></details>
    <details v-if="compared.length"><summary>策略试验对照 · {{compared.length}} 个</summary><p>净收益包含账户已计提成本；不同品种、时段、资金与参数的结果不宜直接排名。最大回撤从本功能启用后开始记录，未平仓头寸按当前观测估值。</p><div class="table-wrap"><table><thead><tr><th>试验 / 品种</th><th>策略 / 模式</th><th>开仓手数</th><th>净收益</th><th>最大回撤</th></tr></thead><tbody><tr v-for="row in compared" :key="row.id"><td>{{row.name}} · {{row.symbol}}</td><td>{{row.strategyId==='WORKFLOW'?row.workflowName+' · v'+row.workflowVersion:name(row.strategyId)}} · {{row.mode==='LIVE'?'实时':'历史'}}</td><td>{{row.strategyLots}}</td><td>{{formatPct((row.equity/row.initialCash-1)*100)}}</td><td>{{formatNumber(row.maxDrawdownPct??0)}}%</td></tr></tbody></table></div></details>
  </section>
</template>
<style scoped>
.strategy-panel{padding:1.2rem;border:1px solid var(--color-line);border-radius:.8rem;background:var(--color-surface);min-width:0}.strategy-panel header{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}.strategy-panel h3{margin:.3rem 0 .8rem;font-size:1rem}.strategy-panel button{border:1px solid var(--color-line);border-radius:.5rem;background:transparent;color:var(--color-accent);padding:.55rem .8rem;cursor:pointer}.strategy-panel p{font-size:.72rem;line-height:1.9;color:var(--color-ink-secondary)}.strategy-facts{display:flex;gap:.6rem;flex-wrap:wrap;font-size:.72rem}.strategy-facts span{padding:.3rem .6rem;background:var(--color-accent-soft);border-radius:.3rem}.market-state{font-weight:600}.strategy-panel summary{cursor:pointer;font-size:.76rem;margin-top:1rem}.table-wrap{overflow:auto;max-width:100%;max-height:16rem;margin-top:.8rem}table{width:100%;border-collapse:collapse;font-size:.69rem;text-align:left}th,td{padding:.65rem .6rem;border-bottom:1px solid var(--color-line);vertical-align:top}th{white-space:nowrap;color:var(--color-ink-tertiary)}td:first-child{white-space:nowrap}
</style>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { workflowTrialsApi, workflowsApi, type MaTrendReplay, type WorkflowTrialDetail, type WorkflowVersion } from '../services/workflows'
import { TRINITY_SYMBOLS } from '../utils/personalTrinity'
import { formatTradingDateTime } from '../utils/format'
import { requestUuid } from '../utils/requestId'
import MaTrendReplayTimeline from './MaTrendReplayTimeline.vue'

const props = defineProps<{
  version: WorkflowVersion; versions?: WorkflowVersion[]; disabled?: boolean
  createTrial?: boolean; savedTrial?: WorkflowTrialDetail
}>()
const emit = defineEmits<{ 'created-trial':[detail:WorkflowTrialDetail]; 'saving-trial':[saving:boolean] }>()
const name = ref(`${props.version.name.slice(0,72)} · 历史试验`)
const symbol = ref<string>(TRINITY_SYMBOLS[0].value)
const initialCash = ref(100000)
const costMultiplier = ref<1|2>(1)
const busy = ref(false)
const error = ref('')
const replay = ref<MaTrendReplay|null>(props.savedTrial?.replay ?? null)
const finished = ref(false)
const compareWith = ref('')
const comparison = ref<{ version: WorkflowVersion; replay: MaTrendReplay } | null>(null)
const comparing = ref(false)
const compareError = ref('')
const runConditions = ref<{ symbol: string; initialCash: number; costMultiplier: 1|2 }|null>(props.savedTrial?.trial ?? null)
const alternatives = computed(() => (props.versions ?? []).filter(version => version.id !== props.version.id
    && version.workflowId === props.version.workflowId && version.engineVersion === props.version.engineVersion))
const actions: Record<string,string> = {OPEN:'开仓', ADD:'加仓', TAKE_PROFIT:'减半止盈', REVERSAL_CLOSE:'反手平仓', TERMINAL_CLOSE:'期末平仓'}
const number = new Intl.NumberFormat('zh-CN', {maximumFractionDigits:2})
let generation = 0
let trialAttempt: { signature:string; id:string } | undefined

function clear() {
  replay.value = null
  runConditions.value = null
  finished.value = false
  comparison.value = null
  compareError.value = ''
  comparing.value = false
  error.value = ''
}

watch([() => props.version.id, symbol, initialCash, costMultiplier], () => { generation += 1; busy.value = false; clear() })
watch(compareWith, () => { comparison.value = null; compareError.value = '' })

async function run() {
  if (busy.value || props.disabled || props.savedTrial || (props.createTrial&&!name.value)) return
  const currentGeneration = ++generation
  const params = { symbol: symbol.value, initialCash: initialCash.value, costMultiplier: costMultiplier.value }
  clear()
  busy.value = true
  try {
    if (props.createTrial) {
      emit('saving-trial',true)
      const trial = {...params, name:name.value, workflowVersionId:props.version.id}
      const signature = JSON.stringify(trial)
      if (trialAttempt?.signature !== signature) trialAttempt = { signature, id:requestUuid() }
      const detail = await workflowTrialsApi.create({...trial, clientRequestId:trialAttempt.id})
      if (!detail.replay.reviewTimeline?.length) throw new Error('这次模拟没有返回可播放的行情，请重试。')
      trialAttempt = undefined
      emit('created-trial',detail)
      return
    }
    const result = await workflowsApi.maTrendReplay(props.version.id, { ...params, includeTimeline:true })
    if (generation !== currentGeneration) return
    if (!result.reviewTimeline?.length) throw new Error('这次模拟没有返回可播放的行情，请重试。')
    runConditions.value = params
    replay.value = result
  } catch (failure) {
    if (generation === currentGeneration) error.value = failure instanceof Error ? failure.message : '历史模拟暂不可用'
  } finally {
    if (generation === currentGeneration) busy.value = false
    if (props.createTrial) emit('saving-trial',false)
  }
}

async function compare() {
  const baseline = replay.value
  const peer = alternatives.value.find(version => version.id === compareWith.value)
  const params = runConditions.value
  if (!finished.value || !peer || !baseline || !params || comparing.value || props.disabled) return
  const currentGeneration = generation
  comparison.value = null
  compareError.value = ''
  comparing.value = true
  try {
    const result = await workflowsApi.maTrendReplay(peer.id, { ...params, includeTimeline:false })
    if (generation !== currentGeneration || compareWith.value !== peer.id) return
    const candidate = result.scope, anchor = baseline.scope
    if (candidate.first !== anchor.first || candidate.last !== anchor.last || candidate.scoreDays !== anchor.scoreDays) {
      throw new Error('两个版本的历史行情区间不同，不能直接比较。')
    }
    if (!baseline.reviewDatasetId || result.reviewDatasetId !== baseline.reviewDatasetId) {
      throw new Error('两个版本使用的历史行情档案不同，不能直接比较。')
    }
    comparison.value = { version:peer, replay:result }
  } catch (failure) {
    if (generation === currentGeneration) compareError.value = failure instanceof Error ? failure.message : '版本对照暂不可用'
  } finally {
    if (generation === currentGeneration) comparing.value = false
  }
}
</script>

<template>
  <section class="ma-trend-replay" aria-label="历史模拟">
    <h4>{{ savedTrial ? version.name : '历史模拟' }} · v{{ version.version }}</h4>
    <p>该版本的止盈目标为 {{ version.definition.maTrendExecution?.takeProfitPct }}%。</p>
    <p v-if="savedTrial">{{ savedTrial.trial.symbol }} · 初始资金 {{ number.format(savedTrial.trial.initialCash) }} 元 · {{ savedTrial.trial.costMultiplier === 2 ? '双倍成本' : '基准成本' }}</p>
    <form v-else class="replay-fields" @submit.prevent="run">
      <label v-if="createTrial">试验名称<input v-model.trim="name" maxlength="80" required :disabled="busy||disabled" /></label>
      <label>交割合约<select v-model="symbol" :disabled="busy||disabled"><option v-for="option in TRINITY_SYMBOLS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
      <label>初始资金（元）<input v-model.number="initialCash" min="1000" max="100000000" step="0.01" type="number" required :disabled="busy||disabled" /></label>
      <label>交易成本<select v-model="costMultiplier" :disabled="busy||disabled"><option :value="1">基准成本</option><option :value="2">双倍成本</option></select></label>
      <button class="primary" type="submit" :disabled="busy||disabled||(createTrial&&!name)">{{ busy ? (createTrial ? '正在创建试验…' : '准备历史回放…') : createTrial ? '创建试验并开始回放' : replay ? '重新回放' : '开始历史回放' }}</button>
    </form>
    <p v-if="error" role="alert" class="replay-error">{{ error }}</p>
    <MaTrendReplayTimeline v-if="replay&&runConditions" :replay="replay" :version="version" :symbol="runConditions.symbol"
      :disabled="busy||disabled" @end-state="finished=$event" />
    <div v-if="replay&&finished" aria-label="历史模拟结果">
      <p>{{ replay.scope.first }} 至 {{ replay.scope.last }} · {{ replay.scope.scoreDays }} 个交易日</p>
      <dl class="replay-metrics">
        <div><dt>净盈亏</dt><dd>{{ number.format(replay.metrics.netPnl) }} 元</dd></div>
        <div><dt>最大回撤</dt><dd>{{ number.format(replay.metrics.maxDrawdownPct) }}%</dd></div>
        <div><dt>开仓 / 加仓</dt><dd>{{ replay.metrics.entryCount }} / {{ replay.metrics.addCount }}</dd></div>
        <div><dt>减半止盈</dt><dd>{{ replay.metrics.takeProfitCount }} 次</dd></div>
      </dl>
      <details v-if="replay.executions.length">
        <summary>查看 {{ replay.executions.length }} 条模拟成交</summary>
        <div class="replay-table"><table>
          <thead><tr><th scope="col">成交时间</th><th scope="col">动作</th><th scope="col">持仓方向</th><th scope="col">手数</th><th scope="col">成交价</th></tr></thead>
          <tbody><tr v-for="row in replay.executions" :key="row.at+row.action"><td>{{ formatTradingDateTime(row.at) }}</td><td>{{ actions[row.action]??row.action }}</td><td>{{ row.direction>0 ? '多头' : '空头' }}</td><td>{{ row.lots }}</td><td>{{ number.format(row.price) }}</td></tr></tbody>
        </table></div>
      </details>
      <details><summary>成交与资金假设</summary><ul><li v-for="note in replay.assumptions" :key="note">{{ note }}</li></ul></details>
      <section v-if="alternatives.length" class="replay-comparison" aria-label="版本对照">
        <h5>相同条件下对照版本</h5>
        <form class="replay-fields" @submit.prevent="compare">
          <label>已发布版本<select v-model="compareWith" :disabled="comparing||disabled">
            <option value="">选择对照版本</option>
            <option v-for="peer in alternatives" :key="peer.id" :value="peer.id">v{{ peer.version }} · 止盈 {{ peer.definition.maTrendExecution?.takeProfitPct }}%</option>
          </select></label>
          <button type="submit" :disabled="!compareWith||comparing||disabled">{{ comparing ? '计算中…' : '运行版本对照' }}</button>
        </form>
        <p class="comparison-details">沿用本次合约、初始资金和交易成本。</p>
        <p v-if="compareError" role="alert" class="replay-error">{{ compareError }}</p>
        <div v-if="comparison" class="replay-table"><table>
          <thead><tr><th scope="col">版本</th><th scope="col">净盈亏（元）</th><th scope="col">最大回撤</th><th scope="col">成交笔数</th><th scope="col">减半止盈</th></tr></thead>
          <tbody>
            <tr><th scope="row">v{{ version.version }} · 本次</th><td>{{ number.format(replay.metrics.netPnl) }}</td><td>{{ number.format(replay.metrics.maxDrawdownPct) }}%</td><td>{{ replay.executions.length }}</td><td>{{ replay.metrics.takeProfitCount }} 次</td></tr>
            <tr><th scope="row">v{{ comparison.version.version }} · 对照</th><td>{{ number.format(comparison.replay.metrics.netPnl) }}</td><td>{{ number.format(comparison.replay.metrics.maxDrawdownPct) }}%</td><td>{{ comparison.replay.executions.length }}</td><td>{{ comparison.replay.metrics.takeProfitCount }} 次</td></tr>
          </tbody>
        </table></div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.ma-trend-replay { border-top: 1px solid var(--color-line); margin-top: 1rem; padding-top: 1rem; }
.ma-trend-replay h4 { margin: 0; }
.ma-trend-replay p { font-size: .78rem; line-height: 1.65; }
.replay-fields { display: flex; flex-wrap: wrap; align-items: end; gap: .65rem; }
.replay-fields label { display: grid; gap: .35rem; font-size: .78rem; }
.replay-error { color: var(--color-warning); }
.replay-metrics { display: flex; flex-wrap: wrap; column-gap: 1.5rem; row-gap: .6rem; padding: .75rem 0; border-block: 1px solid var(--color-line); }
.replay-metrics dt { font-size: .72rem; color: var(--color-ink-secondary); }
.replay-metrics dd { margin: .25rem 0 0; font-weight: 650; }
.ma-trend-replay details { margin: .6rem 0; font-size: .78rem; }
.replay-table { overflow: auto; }
.replay-table table { width: 100%; border-collapse: collapse; text-align: left; }
.replay-table th, .replay-table td { padding: .55rem; white-space: nowrap; border-bottom: 1px solid var(--color-line); }
.replay-comparison { margin-top: 1.2rem; padding-top: .8rem; border-top: 1px solid var(--color-line); }
.replay-comparison h5 { margin: 0 0 .65rem; font-size: .9rem; }
.comparison-details { color: var(--color-ink-secondary); }
</style>

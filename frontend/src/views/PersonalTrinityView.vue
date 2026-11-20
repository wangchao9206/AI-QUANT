<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowUpRight, Download, Play, RotateCcw, Save, Upload } from 'lucide-vue-next'
import { authState, hasPermission } from '../services/auth'
import { formatNumber, formatPct, formatTradingDate, formatTradingDateTime } from '../utils/format'
import {
  TRINITY_DEFAULT, TRINITY_NAME, TRINITY_STRATEGY_ID, TRINITY_SYMBOLS, backtestTrinity, exportTrinity, importTrinity,
  loadTrinityDrafts, persistTrinityDrafts, stageTrinityPaperLaunch, validateTrinity,
  type TrinityConfig, type TrinityDraft, type TrinityResult,
} from '../utils/personalTrinity'
import { requestId } from '../utils/requestId'
import { currentScope } from '../utils/storageScope'

const confirmations: Record<TrinityConfig['confirmation'], string> = {
  either: '缠论或威科夫，先确认即可',
  chan: '仅缠论',
  wyckoff: '仅威科夫',
}
const addModes: Record<TrinityConfig['addMode'], string> = {
  MINUTE_ADD: '同向的新分钟信号',
  MA10_ADD: '日线收敛后等待分钟确认',
  NONE: '只做一手',
}
const exitReasons: Record<string, string> = { MA_REVERSAL: '日线反手', WINDOW_END: '窗口末清算' }
const copyName = `${TRINITY_NAME} · 副本`
const router = useRouter()
const config = ref<TrinityConfig>({ ...TRINITY_DEFAULT })
const name = ref(copyName)
const activeId = ref('')
const drafts = ref<TrinityDraft[]>([])
const importControl = ref<HTMLInputElement>()
const busy = ref(false)
const formError = ref('')
const draftError = ref('')
const notice = ref('')
const run = ref<{ name: string; config: TrinityConfig; result: TrinityResult } | null>(null)
const activeDraft = computed(() => drafts.value.find(draft => draft.id === activeId.value))
const canBacktest = computed(() => hasPermission('research.write'))
const canSimulate = computed(() => !!authState.user && ['paper.read','paper.write','market.read'].every(hasPermission))
const identity = computed(() => authState.user ? `${authState.user.id}:${authState.user.tenantId}` : null)
const validation = computed(() => validateTrinity(config.value))
const dirty = computed(() => !!activeDraft.value && (
  activeDraft.value.name !== name.value.trim()
  || JSON.stringify(activeDraft.value.config) !== JSON.stringify(config.value)
))

watch(config, () => {
  run.value = null
  formError.value = ''
}, { deep: true })

function refreshDrafts() {
  try {
    drafts.value = loadTrinityDrafts()
  } catch (error) {
    draftError.value = message(error, '读取本地草稿失败')
  }
}

onMounted(refreshDrafts)
watch(identity, () => {
  drafts.value = []
  resetTemplate()
  notice.value = ''
  refreshDrafts()
}, { flush: 'post' })

function message(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function labelFor(value: TrinityConfig['symbol']) {
  return TRINITY_SYMBOLS.find(option => option.value === value)?.label ?? value
}

function money(value: number) {
  return `${value > 0 ? '+' : ''}${formatNumber(value)} 元`
}

function loadDraft(draft: TrinityDraft, saved: boolean) {
  activeId.value = saved ? draft.id : ''
  name.value = draft.name
  config.value = { ...draft.config }
  draftError.value = ''
  notice.value = saved ? '已打开本地草稿。' : '已导入为新草稿，保存后可在此继续编辑。'
}

function selectDraft(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  const draft = drafts.value.find(item => item.id === id)
  if (draft) loadDraft(draft, true)
}

function resetTemplate() {
  activeId.value = ''
  name.value = copyName
  config.value = { ...TRINITY_DEFAULT }
  draftError.value = ''
  notice.value = '已打开内置模板。'
}

function snapshot(asCopy = false): TrinityDraft {
  const label = name.value.trim()
  if (!label) throw new Error('请输入策略名称。')
  if (label.length > 120) throw new Error('策略名称最多 120 个字符。')
  if (validation.value) throw new Error(validation.value)
  return { id: (!asCopy && activeId.value) || requestId(), name: asCopy ? `${label.slice(0, 115)} · 副本` : label,
    config: { ...config.value } }
}

function saveDraft(asCopy = false) {
  draftError.value = ''
  notice.value = ''
  try {
    const draft = snapshot(asCopy)
    const updated = [draft, ...loadTrinityDrafts().filter(item => item.id !== draft.id)]
    persistTrinityDrafts(updated)
    drafts.value = updated
    activeId.value = draft.id
    name.value = draft.name
    notice.value = '草稿已保存到当前浏览器。'
  } catch (error) {
    draftError.value = message(error, '保存本地草稿失败')
  }
}

function downloadDraft() {
  draftError.value = ''
  try {
    const draft = snapshot()
    const url = URL.createObjectURL(new Blob([exportTrinity(draft)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${draft.name.replace(/[<>:"/\\|?*]/g, '_')}.json`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) {
    draftError.value = message(error, '导出草稿失败')
  }
}

async function importDraft(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  draftError.value = ''
  notice.value = ''
  const scope = currentScope()
  try {
    if (file.size > 64 * 1024) throw new Error('策略 JSON 文件不能超过 64 KB。')
    const value = await file.text()
    if (currentScope() === scope) loadDraft(importTrinity(value), false)
  } catch (error) {
    if (currentScope() === scope) draftError.value = message(error, '导入草稿失败')
  }
}

async function runBacktest() {
  if (busy.value || !canBacktest.value) return
  run.value = null
  formError.value = validation.value ?? ''
  if (formError.value) return
  const frozen = { ...config.value }
  const frozenName = activeId.value || name.value !== copyName ? name.value.trim() || TRINITY_NAME : TRINITY_NAME
  const scope = currentScope()
  busy.value = true
  try {
    const result = await backtestTrinity(frozen)
    if (currentScope() === scope) run.value = { name: frozenName, config: frozen, result }
  } catch (error) {
    if (currentScope() === scope) formError.value = message(error, '历史回测暂不可用')
  } finally {
    busy.value = false
  }
}

async function openSimulation() {
  if(busy.value||!canSimulate.value)return
  formError.value=''
  try {
    const draft=snapshot()
    const trinity=stageTrinityPaperLaunch({...draft,id:requestId(),name:draft.name===copyName?TRINITY_NAME:draft.name})
    await router.push({path:'/paper',query:{automation:TRINITY_STRATEGY_ID,trinity},hash:'#paper-automation'})
  } catch(error) {
    formError.value=message(error,'无法把当前参数带到模拟盘')
  }
}
</script>

<template>
  <div class="page-stack trinity-page">
    <header class="trinity-header">
      <RouterLink to="/strategy" class="back-link"><ArrowLeft :size="15" aria-hidden="true" /> 返回策略中心</RouterLink>
      <h2>改造策略</h2>
      <p>已完成的日线决定方向与反手平仓。分钟信号负责择时，首笔一手，多头最多加一手。</p>
    </header>

    <div class="trinity-workspace">
      <form class="trinity-editor" novalidate @submit.prevent="runBacktest">
        <fieldset :disabled="busy">
          <legend>日线趋势</legend>
          <p>快线穿越慢线时确定多空方向，反手平仓以日线为准。</p>
          <div class="trinity-fields trinity-fields--ma">
            <label>快线周期（日）<input v-model.number="config.fastPeriod" type="number" min="2" max="120" step="1" /></label>
            <label>中线周期（日）<input v-model.number="config.mediumPeriod" type="number" min="2" max="120" step="1" /></label>
            <label>慢线周期（日）<input v-model.number="config.slowPeriod" type="number" min="2" max="120" step="1" /></label>
            <label>收敛观察（交易日）<input v-model.number="config.convergenceDays" type="number" min="2" max="20" step="1" /></label>
          </div>
        </fieldset>

        <fieldset :disabled="busy">
          <legend>分钟择时与加仓</legend>
          <div class="trinity-fields">
            <label>分钟周期<select v-model.number="config.entryMinutes"><option :value="15">15 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option></select></label>
            <label>入场确认<select v-model="config.confirmation"><option v-for="(label, key) in confirmations" :key="key" :value="key">{{ label }}</option></select></label>
            <label>多头加仓方式<select v-model="config.addMode"><option v-for="(label, key) in addModes" :key="key" :value="key">{{ label }}</option></select></label>
            <label>最长等待（交易日）<input v-model.number="config.waitTradingDays" type="number" min="1" max="40" step="1" /></label>
          </div>
          <p>日线信号确认后，等待新的同向分钟信号。方向失效时取消等待。</p>
        </fieldset>

        <fieldset class="trinity-backtest" :disabled="busy">
          <legend>历史回测</legend>
          <div class="trinity-fields">
            <label>回测合约<select v-model="config.symbol"><option v-for="option in TRINITY_SYMBOLS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <label>交易成本<select v-model.number="config.costMultiplier"><option :value="1">基准成本</option><option :value="2">双倍成本</option></select></label>
          </div>
          <div class="trinity-run-footer">
            <p>{{ canBacktest ? '使用已核验的同合约历史行情。' : '当前账号没有运行历史回测的权限。' }}</p>
            <button type="submit" class="primary" :disabled="busy || !canBacktest"><Play :size="15" aria-hidden="true" /> {{ busy ? '回测中…' : '运行历史回测' }}</button>
          </div>
        </fieldset>
        <fieldset :disabled="busy">
          <legend>模拟盘自动执行</legend>
          <div class="trinity-run-footer">
            <p>{{ canSimulate ? '把当前规则带到模拟账户，选定实际交割合约后启动。' : '当前账号没有启动模拟执行的权限。' }}</p>
            <button type="button" :disabled="!canSimulate" @click="openSimulation">带参数去模拟盘 <ArrowUpRight :size="15" aria-hidden="true" /></button>
          </div>
        </fieldset>
        <p v-if="formError" class="trinity-error" role="alert">{{ formError }}</p>
        <p v-else-if="busy" class="trinity-status" role="status">正在按当前参数回测…</p>
      </form>

      <aside class="trinity-drafts" aria-labelledby="trinity-drafts-title">
        <fieldset :disabled="busy">
          <legend id="trinity-drafts-title">我的改造草稿</legend>
          <p>草稿保存在当前浏览器，也可以导出 JSON 后在另一台设备上导入。</p>
          <label>打开已保存草稿<select :value="activeId" @change="selectDraft"><option value="" disabled>{{ drafts.length ? '选择已保存草稿' : '暂无已保存草稿' }}</option><option v-for="draft in drafts" :key="draft.id" :value="draft.id">{{ draft.name }}</option></select></label>
          <label>策略名称<input v-model="name" type="text" maxlength="120" /></label>
          <p v-if="dirty" class="draft-state">当前草稿有未保存的修改。</p>
          <div class="draft-actions">
            <button type="button" class="primary" @click="saveDraft()"><Save :size="15" aria-hidden="true" /> {{ activeId ? '保存修改' : '保存为草稿' }}</button>
            <button v-if="activeId" type="button" @click="saveDraft(true)">另存副本</button>
            <button type="button" @click="resetTemplate"><RotateCcw :size="15" aria-hidden="true" /> 恢复内置模板</button>
          </div>
          <div class="draft-actions draft-actions--files">
            <button type="button" @click="downloadDraft"><Download :size="15" aria-hidden="true" /> 导出 JSON</button>
            <button type="button" @click="importControl?.click()"><Upload :size="15" aria-hidden="true" /> 导入 JSON</button>
            <input ref="importControl" type="file" accept=".json,application/json" aria-label="导入策略 JSON 文件" hidden @change="importDraft" />
          </div>
        </fieldset>
        <p v-if="draftError" class="trinity-error" role="alert">{{ draftError }}</p>
        <p v-else-if="notice" class="trinity-status" role="status">{{ notice }}</p>
      </aside>
    </div>

    <section v-if="run" class="trinity-result" aria-labelledby="trinity-result-title">
      <header>
        <h2 id="trinity-result-title">回测结果</h2>
        <p>{{ run.name }} · {{ labelFor(run.config.symbol) }} · {{ formatTradingDate(run.result.scope.first) }} 至 {{ formatTradingDate(run.result.scope.last) }} · {{ run.result.scope.scoreDays }} 个交易日</p>
        <p>MA{{ run.config.fastPeriod }}／{{ run.config.mediumPeriod }}／{{ run.config.slowPeriod }} · 收敛 {{ run.config.convergenceDays }} 日 · {{ run.config.entryMinutes }} 分钟 · {{ confirmations[run.config.confirmation] }} · 最长等待 {{ run.config.waitTradingDays }} 日 · {{ addModes[run.config.addMode] }} · {{ run.config.costMultiplier === 2 ? '双倍成本' : '基准成本' }}</p>
      </header>
      <dl class="result-metrics">
        <div><dt>净损益</dt><dd :class="run.result.metrics.netPnl > 0 ? 'gain' : undefined">{{ money(run.result.metrics.netPnl) }}</dd></div>
        <div><dt>累计收益率</dt><dd>{{ formatPct(run.result.metrics.returnPct, 3) }}</dd></div>
        <div><dt>最大回撤</dt><dd>{{ formatNumber(run.result.metrics.maxDrawdownPct, 3) }}%</dd></div>
        <div><dt>主仓 / 加仓 / 平仓笔数</dt><dd>{{ run.result.metrics.primaryOpens }} / {{ run.result.metrics.addOpens }} / {{ run.result.metrics.closedTrades }}</dd></div>
      </dl>
      <div v-if="run.result.trades.length" class="trinity-trades">
        <table>
          <caption>逐笔成交</caption>
          <thead><tr><th scope="col">仓位</th><th scope="col">方向</th><th scope="col">开仓时间</th><th scope="col">开仓价</th><th scope="col">平仓时间</th><th scope="col">平仓价</th><th scope="col">平仓原因</th><th scope="col">净损益</th></tr></thead>
          <tbody><tr v-for="(trade, index) in run.result.trades" :key="index"><td>{{ trade.slot ? '加仓' : '主仓' }}</td><td>{{ trade.direction > 0 ? '多头' : '空头' }}</td><td>{{ formatTradingDateTime(trade.entryAt) }}</td><td>{{ formatNumber(trade.entryPrice) }}</td><td>{{ formatTradingDateTime(trade.exitAt) }}</td><td>{{ formatNumber(trade.exitPrice) }}</td><td>{{ exitReasons[trade.exitReason ?? ''] ?? '—' }}</td><td>{{ money(trade.netPnl) }}</td></tr></tbody>
        </table>
      </div>
      <p v-else class="trinity-status">本次回测没有成交。</p>
    </section>
  </div>
</template>

<style scoped>
.trinity-page { min-width: 0; }
.trinity-header { padding: .6rem 0 .3rem; }
.trinity-header h2 { margin: 1rem 0 .45rem; font: 500 clamp(1.55rem, 3vw, 2.25rem) / 1.35 var(--font-display); }
.trinity-header p, fieldset p, .trinity-result p { margin: .4rem 0 0; color: var(--color-ink-secondary); font-size: .76rem; line-height: 1.8; }
.back-link { display: inline-flex; gap: .4rem; align-items: center; font-size: .75rem; color: var(--color-accent); text-decoration: none; }
.trinity-workspace { display: grid; grid-template-columns: minmax(0, 2fr) minmax(17rem, 1fr); gap: 1rem; align-items: start; }
.trinity-editor, .trinity-drafts, .trinity-result { min-width: 0; border: 1px solid var(--color-line); border-radius: .85rem; background: var(--color-surface-raised); padding: 1.25rem; }
.trinity-editor { border-top: 3px solid var(--color-accent); }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
.trinity-editor fieldset + fieldset { border-top: 1px solid var(--color-line); margin-top: 1.2rem; padding-top: .7rem; }
legend, .trinity-result h2 { margin: 0; padding: 0; color: var(--color-ink); font-size: .97rem; font-weight: 650; }
.trinity-editor fieldset + fieldset legend { padding-right: .7rem; }
.trinity-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem 1rem; margin-top: .65rem; }
.trinity-fields--ma { grid-template-columns: repeat(4, minmax(0, 1fr)); }
label { display: grid; gap: .4rem; font-size: .72rem; font-weight: 550; color: var(--color-ink-secondary); }
.trinity-drafts label { margin-top: .95rem; }
input, select, button { font: inherit; }
input:not([type=file]), select { box-sizing: border-box; min-width: 0; width: 100%; padding: .62rem .7rem; color: var(--color-ink); background: var(--color-surface); border: 1px solid var(--color-line); border-radius: .45rem; font-size: .8rem; }
button { display: inline-flex; align-items: center; justify-content: center; gap: .38rem; padding: .59rem .72rem; border: 1px solid var(--color-line); border-radius: .45rem; background: var(--color-surface); color: var(--color-ink); white-space: nowrap; font-size: .74rem; cursor: pointer; }
button.primary { background: var(--color-accent); border-color: var(--color-accent); color: white; }
button:disabled { opacity: .55; cursor: default; }
a:focus-visible, input:focus-visible, select:focus-visible, button:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
.trinity-run-footer, .draft-actions { display: flex; align-items: center; gap: .55rem; flex-wrap: wrap; margin-top: .8rem; }
.trinity-run-footer { justify-content: space-between; }
.trinity-run-footer p { margin: 0; }
.draft-actions--files { border-top: 1px solid var(--color-line); padding-top: .8rem; }
.draft-state, .trinity-status { color: var(--color-accent); }
.trinity-status, .trinity-error { margin: .75rem 0 0; font-size: .75rem; line-height: 1.8; }
.trinity-error { background: var(--color-warning-soft); color: var(--color-warning); padding: .55rem .7rem; border-radius: .4rem; }
.result-metrics { margin: 1rem 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem; }
.result-metrics > div { padding: .75rem 0; border-top: 1px solid var(--color-line); }
.result-metrics dt { color: var(--color-ink-secondary); font-size: .7rem; }
.result-metrics dd { margin: .42rem 0 0; color: var(--color-ink); font: 600 clamp(.88rem, 1.35vw, 1.3rem) var(--font-numeric); }
.result-metrics dd.gain { color: var(--color-accent); }
.trinity-trades { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; text-align: left; white-space: nowrap; font-size: .72rem; }
caption { text-align: left; font-weight: 650; padding-bottom: .5rem; }
th, td { padding: .56rem .6rem; border-bottom: 1px solid var(--color-line); }
th { color: var(--color-ink-secondary); font-weight: 550; }
@media (max-width: 950px) { .trinity-fields--ma { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) { .trinity-workspace { grid-template-columns: minmax(0, 1fr); } .result-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 360px) { .trinity-editor, .trinity-drafts, .trinity-result { padding: .85rem; } .trinity-fields { grid-template-columns: minmax(0, 1fr); } }
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatTradingDateTime } from '../utils/format'
import { TRINITY_SYMBOLS } from '../utils/personalTrinity'
import { request } from '../services/api'

type Minute = { at: string; close: number; ma20: number|null; trend: number; confirmed: boolean;
  dif: number|null; dea: number|null; macdCross: 'GOLD'|'DEATH'|null; dkx: number|null; madkx: number|null }
type Preview = {
  symbol: string; signalDate: string; executionDate: string; confirmedAt: string|null;
  scope: { first: string; last: string };
  daily: { close: number; ma5: number|null; ma10: number|null; ma20: number|null; trend: number; strong: number;
    trigger: 'LONG_CROSS'|'SHORT_CROSS'|'LONG_REENTRY'|null; dkx: number|null; madkx: number|null };
  minutes: Minute[];
}

const symbol = ref<string>(TRINITY_SYMBOLS[0].value)
const date = ref('')
const busy = ref(false)
const error = ref('')
const result = ref<Preview|null>(null)
const confirmation = computed(() => result.value?.minutes.find(row => row.at === result.value?.confirmedAt))
const triggerLabels = { LONG_CROSS: 'MA5 上穿 MA20 · 买多／平空候选',
  SHORT_CROSS: 'MA5 下穿 MA20 · 买空／平多候选', LONG_REENTRY: '收敛后 MA5 上穿 MA10 · 买多／加多候选' }
const side = (value: number) => value > 0 ? '偏多' : value < 0 ? '偏空' : '中性'
const amount = (value: number|null, digits = 2) => typeof value === 'number' ? value.toFixed(digits) : '—'
const cross = (value: Minute['macdCross']) => value === 'GOLD' ? '金叉' : value === 'DEATH' ? '死叉' : '无交叉'

function clear() { result.value = null; error.value = '' }

async function preview() {
  if (busy.value) return
  busy.value = true
  clear()
  try {
    result.value = await request<Preview>('/api/v1/research/ma-trend-workflow/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: symbol.value, ...(date.value ? { signalDate: date.value } : {}) }),
    }, 45000)
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : '历史试算暂不可用'
  } finally { busy.value = false }
}
</script>

<template>
  <section class="ma-preview" aria-label="均线与分钟信号试算">
    <form class="preview-controls" @submit.prevent="preview">
      <label>交割合约<select v-model="symbol" :disabled="busy" @change="clear"><option v-for="item in TRINITY_SYMBOLS" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
      <label>日线信号日期（可选）<input v-model="date" type="date" :disabled="busy" @change="clear" /></label>
      <button type="submit" class="primary" :disabled="busy">{{ busy ? '试算中…' : '试算日线和 15 分钟' }}</button>
    </form>
    <p v-if="!date">日期留空时，选取档案中最近一次有次日行情可核验的日线候选。</p>
    <p v-if="error" role="alert" class="preview-error">{{ error }}</p>
    <div v-if="result" class="preview-result" aria-label="均线试算结果">
      <div class="preview-timeline">
        <div><h4>{{ result.signalDate }} 日线</h4>
          <strong>{{ result.daily.trigger ? triggerLabels[result.daily.trigger] : '未触发买卖候选' }}</strong>
          <p>{{ side(result.daily.trend) }}<template v-if="result.daily.strong"> · 强势{{ result.daily.strong > 0 ? '多头' : '空头' }}</template> · 收盘 {{ amount(result.daily.close) }}</p>
          <p>MA5 {{ amount(result.daily.ma5) }} · MA10 {{ amount(result.daily.ma10) }} · MA20 {{ amount(result.daily.ma20) }}</p>
          <p>DKX {{ amount(result.daily.dkx) }} · MADKX {{ amount(result.daily.madkx) }}</p></div>
        <div><h4>{{ result.executionDate }} 下一个交易日</h4>
          <template v-if="confirmation"><strong>首次 15 分钟确认 {{ formatTradingDateTime(confirmation.at) }}</strong>
            <p>{{ side(confirmation.trend) }} · 收盘 {{ amount(confirmation.close) }} · MA20 {{ amount(confirmation.ma20) }}</p>
            <p>MACD {{ cross(confirmation.macdCross) }} · DKX {{ amount(confirmation.dkx) }} · MADKX {{ amount(confirmation.madkx) }}</p>
          </template>
          <strong v-else>{{ result.daily.trigger ? '当天没有出现同方向的 15 分钟确认' : '日线未触发，无待确认候选' }}</strong>
          <p>夜盘按交易所交易日归属。表内时间为 K 线收盘时间。</p>
        </div>
      </div>
      <details>
        <summary>展开当日 15 分钟记录（{{ result.minutes.length }} 根）</summary>
        <div class="preview-table">
          <table>
            <thead><tr><th scope="col">收盘时间</th><th scope="col">收盘价</th><th scope="col">MA20</th><th scope="col">15 分钟方向</th><th scope="col">MACD</th><th scope="col">DIF / DEA</th><th scope="col">DKX / MADKX</th></tr></thead>
            <tbody><tr v-for="row in result.minutes" :key="row.at"><td>{{ formatTradingDateTime(row.at) }}</td><td>{{ amount(row.close) }}</td><td>{{ amount(row.ma20) }}</td><td>{{ side(row.trend) }}{{ row.confirmed ? ' · 符合' : '' }}</td><td>{{ cross(row.macdCross) }}</td><td>{{ amount(row.dif,3) }} / {{ amount(row.dea,3) }}</td><td>{{ amount(row.dkx) }} / {{ amount(row.madkx) }}</td></tr></tbody>
          </table>
        </div>
      </details>
      <p>可选信号日期 {{ result.scope.first }} 至 {{ result.scope.last }}。这是信号试算，尚未计算半仓、成交和盈亏。</p>
    </div>
  </section>
</template>

<style scoped>
.preview-controls { display: flex; flex-wrap: wrap; align-items: end; gap: .65rem; }
.preview-controls label { display: grid; gap: .35rem; font-size: .78rem; }
.preview-timeline { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); border-block: 1px solid var(--color-line); }
.preview-timeline > div { padding: .8rem .5rem; min-width: 0; }
.preview-timeline h4 { margin: 0 0 .5rem; font-size: .86rem; }
.preview-result { margin-top: 1rem; }
.ma-preview p { margin: .4rem 0; font-size: .76rem; line-height: 1.6; color: var(--color-ink-secondary); }
.ma-preview .preview-error { color: var(--color-warning); }
.preview-result summary { padding: .68rem 0; cursor: pointer; font-size: .79rem; }
.preview-table { overflow: auto; }
.preview-table table { width: 100%; border-collapse: collapse; text-align: left; font-size: .73rem; }
.preview-table th, .preview-table td { padding: .5rem; white-space: nowrap; border-bottom: 1px solid var(--color-line); }
@media (max-width: 640px) { .preview-timeline { grid-template-columns: minmax(0,1fr); } }
</style>

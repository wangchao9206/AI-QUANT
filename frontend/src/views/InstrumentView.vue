<script setup lang="ts">
import { computed, ref } from 'vue'
import { Eye, Maximize2, Minimize2 } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

import AsyncState from '../components/AsyncState.vue'
import DataPanel from '../components/DataPanel.vue'
import FreshnessBadge from '../components/FreshnessBadge.vue'
import LineChart from '../components/LineChart.vue'
import TongdaxinChart from '../components/TongdaxinChart.vue'
import {useExperience} from '../composables/useExperience'
import {instrumentPath,researchPath} from '../utils/marketNavigation'
import { useDashboard } from '../composables/useDashboard'
import { formatNumber, formatPct, formatTime } from '../utils/format'

const router = useRouter()
const { store, state, quote, history, termStructure, catalog, error } = useDashboard(false)
const {isSimple}=useExperience()
const priceRange=computed(()=>{
  const points=history.value?.points??[]
  return points.length?{low:Math.min(...points.map(p=>p.price)),high:Math.max(...points.map(p=>p.price)),first:points[0]!.timestamp.slice(0,10),last:points[points.length-1]!.timestamp.slice(0,10)}:null
})
const asyncState = computed(() => (state.value === 'idle' ? 'loading' : state.value))
const termValues = computed(() => termStructure.value?.contracts.map((item) => item.price) ?? [])
const instrumentCount = computed(
  () => catalog.value?.exchanges.reduce((sum, group) => sum + group.instruments.length, 0) ?? 0,
)
const contractCount = computed(
  () =>
    catalog.value?.exchanges.reduce(
      (sum, group) => sum + group.instruments.reduce((count, item) => count + item.contracts.length, 0),
      0,
    ) ?? 0,
)

// 通达信图表宽屏切换
const isWideChart = ref(false)

// 合约梯度点击切换看盘
async function selectContract(contractCode: string) {
  if (isCurrentContract(contractCode)) return
  await router.push(instrumentPath(contractCode))
}

function isCurrentContract(contractCode: string): boolean {
  const cur = (store.symbol || '').toUpperCase().trim()
  const target = contractCode.toUpperCase().trim()
  if (cur === target) return true
  // 兼容郑商所3位与4位写法 (例如 CJ701 与 CJ2701)
  const normCur = cur.replace(/^([A-Z]+)2(\d{3})$/, '$1$2')
  const normTarget = target.replace(/^([A-Z]+)2(\d{3})$/, '$1$2')
  return normCur === normTarget
}
</script>

<template>
  <div class="page-stack">
    <nav class="detail-links" aria-label="品种详情导航"><RouterLink to="/market">← 返回行情市场</RouterLink><RouterLink :to="researchPath(store.symbol)">了解这个品种的研究结果 ↗</RouterLink></nav>
    <div class="section-intro">
      <p>
        当前页面只查看选中的品种。返回行情市场可以比较多个品种；每条数据均保留观测时间与来源。
      </p>
    </div>
    <div v-if="catalog&&!isSimple" class="coverage-strip" aria-label="国内期货覆盖范围">
      <div>
        <strong>{{ catalog.exchanges.length }}</strong>
        <span>交易所</span>
      </div>
      <div>
        <strong>{{ instrumentCount }}</strong>
        <span>期货品种</span>
      </div>
      <div>
        <strong>{{ contractCount }}</strong>
        <span>当前挂牌合约</span>
      </div>
      <div class="coverage-exchanges">
        <span v-for="group in catalog.exchanges" :key="group.code">{{ group.code }}</span>
      </div>
      <FreshnessBadge :status="catalog.dataStatus" :timestamp="catalog.dataTimestamp" />
    </div>

    <AsyncState :state="asyncState" :error-message="error" @retry="store.loadMarket()">
      <div v-if="quote && history" class="page-grid">
        <!-- 当前报价卡片 -->
        <DataPanel
          :class="isWideChart ? 'span-12' : 'span-4'"
          title="当前报价"
          eyebrow="Market snapshot"
        >
          <template #actions>
            <FreshnessBadge :status="quote.dataStatus" :timestamp="quote.dataTimestamp" />
          </template>
          <div class="quote-main">
            <strong>{{ formatNumber(quote.price) }}</strong>
            <span :class="quote.change >= 0 ? 'positive' : 'negative'">
              {{ formatPct(quote.changePct) }}
            </span>
          </div>
          <p class="instrument">{{ quote.displayName }} · {{ quote.symbol }}</p>
          <div class="metric-grid quote-metrics">
            <div class="metric">
              <span>涨跌</span>
              <strong :class="quote.change >= 0 ? 'positive' : 'negative'">
                {{ quote.change > 0 ? `+${formatNumber(quote.change)}` : formatNumber(quote.change) }}
              </strong>
            </div>
            <div class="metric">
              <span>数据来源</span>
              <strong class="source-value">{{ quote.source }}</strong>
            </div>
          </div>
          <p class="source-note">更新于 {{ formatTime(quote.dataTimestamp) }}</p>
        </DataPanel>

        <!-- 通达信风格行情图表 (包含主图K线 + MACD/VOL/涨跌柱状图) -->
        <DataPanel
          :class="isWideChart ? 'span-12' : 'span-8'"
          :title="isSimple?'价格走势':'专业K线与指标'"
          :eyebrow="isSimple?'先观察价格随时间的变化':'K线 · 均线 · MACD · 成交量'"
        >
          <template #actions>
            <div class="chart-panel-actions">
              <button
                type="button"
                class="wide-toggle-btn"
                :title="isWideChart ? '还原宽度' : '全宽展示'"
                @click="isWideChart = !isWideChart"
              >
                <Minimize2 v-if="isWideChart" :size="14" />
                <Maximize2 v-else :size="14" />
                <span>{{ isWideChart ? '标准宽' : '宽屏看盘' }}</span>
              </button>
              <FreshnessBadge :status="history.dataStatus" :timestamp="history.dataTimestamp" />
            </div>
          </template>

          <div v-if="isSimple" class="simple-price-chart"><div v-if="priceRange" class="price-range"><span>区间最低 {{formatNumber(priceRange.low)}}</span><span>区间最高 {{formatNumber(priceRange.high)}}</span></div><LineChart :values="history.points.map(p=>p.price)" :label="`${quote.displayName}价格走势`" :height="280"/><div v-if="priceRange" class="price-range"><time>{{priceRange.first}}</time><time>{{priceRange.last}}</time></div><p>图中是观测价格随时间的变化；切换专业模式可查看K线与指标。报价单位因品种而异，价格不等于一手合约金额。</p></div>
          <TongdaxinChart v-else
            :points="history.points"
            :symbol="quote.symbol"
            :display-name="quote.displayName"
            :height="380"
          />
        </DataPanel>

        <details class="span-12 advanced-market" :open="!isSimple"><summary>查看合约月份、价格差异与切换合约</summary><p>同一种期货可能有多个交割月份。主连用于串联走势；实际合约有明确月份和到期安排。</p><div class="page-grid">
        <!-- 期限结构 -->
        <DataPanel v-if="termStructure" class="span-7" title="期限结构" eyebrow="Forward curve">
          <template #actions>
            <FreshnessBadge
              :status="termStructure.dataStatus"
              :timestamp="termStructure.dataTimestamp"
            />
          </template>
          <LineChart
            :values="termValues"
            :height="180"
            :label="`${termStructure.rootSymbol}期限结构`"
          />
        </DataPanel>

        <!-- 合约梯度 -->
        <DataPanel v-if="termStructure" class="span-5" title="合约梯度" eyebrow="Contract ladder · 点击任意合约切换看盘">
          <template #actions>
            <span class="ladder-hint">点击合约即时切换</span>
          </template>
          <div class="table-wrap">
            <table class="data-table ladder-table">
              <thead>
                <tr>
                  <th>合约</th>
                  <th>交割月</th>
                  <th class="numeric">最新价</th>
                  <th class="action-col">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in termStructure.contracts"
                  :key="item.contract"
                  class="ladder-row"
                  :class="{ 'is-active': isCurrentContract(item.contract) }"
                  title="点击切换到该合约查看分时与K线"
                  @click="selectContract(item.contract)"
                >
                  <td>
                    <div class="contract-cell">
                      <strong class="contract-name">{{ item.contract }}</strong>
                      <span v-if="isCurrentContract(item.contract)" class="badge-active">展示中</span>
                    </div>
                  </td>
                  <td>{{ item.maturityDate }}</td>
                  <td class="numeric font-mono">{{ formatNumber(item.price) }}</td>
                  <td class="action-col">
                    <button
                      type="button"
                      class="btn-select-contract"
                      :class="{ active: isCurrentContract(item.contract) }"
                      @click.stop="selectContract(item.contract)"
                    >
                      <Eye :size="12" />
                      <span>{{ isCurrentContract(item.contract) ? '当前看盘' : '看此合约' }}</span>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </DataPanel>
        <DataPanel v-else class="span-12" title="期限结构" eyebrow="Forward curve unavailable">
          <p class="empty-curve">
            当前品种没有足够的有效合约报价形成价格差异曲线。未取得的数据保持为空，其他价格信息可独立查看。
          </p>
        </DataPanel>
        </div></details>
      </div>
    </AsyncState>
  </div>
</template>

<style scoped>
.price-range{display:flex;justify-content:space-between;gap:.7rem;color:var(--color-ink-tertiary);font:.65rem var(--font-numeric);padding:.5rem 0;flex-wrap:wrap}
.detail-links{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;font-size:.73rem}.detail-links a{color:var(--color-accent);text-decoration:none}.simple-price-chart p,.advanced-market>p{font-size:.7rem;line-height:1.8;color:var(--color-ink-secondary)}.advanced-market{min-width:0}.advanced-market>summary{cursor:pointer;padding:1rem;border:1px solid var(--color-line);border-radius:.7rem;background:var(--color-surface);font-size:.8rem;color:var(--color-accent);margin-bottom:1rem}

.coverage-strip {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.8rem 1rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  background: rgb(255 255 255 / 55%);
}
.coverage-strip > div:not(.coverage-exchanges) {
  display: grid;
  gap: 0.08rem;
}
.coverage-strip strong {
  font: 600 0.9rem var(--font-numeric);
}
.coverage-strip div > span {
  color: var(--color-ink-tertiary);
  font-size: 0.6rem;
}
.coverage-exchanges {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.coverage-exchanges span {
  padding: 0.25rem 0.42rem;
  border-radius: var(--radius-pill);
  background: #ece9e2;
  font: 650 0.58rem var(--font-numeric);
}
.empty-curve {
  margin: 0;
  color: var(--color-ink-secondary);
  font-size: 0.74rem;
  line-height: 1.7;
}
.quote-main {
  display: flex;
  align-items: baseline;
  gap: 1rem;
  margin-top: 0.6rem;
}
.quote-main > strong {
  font: 500 clamp(2.6rem, 6vw, 4.2rem) var(--font-display);
  letter-spacing: -0.07em;
}
.quote-main > span {
  font: 650 0.8rem var(--font-numeric);
}
.instrument {
  margin: 0.1rem 0 1.4rem;
  color: var(--color-ink-secondary);
  font-size: 0.74rem;
}
.quote-metrics {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 1rem;
}
.source-value {
  display: block;
  overflow: hidden;
  font-family: var(--font-sans) !important;
  font-size: 0.72rem !important;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chart-panel-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
}

.wide-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.55rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  background: white;
  color: var(--color-ink-secondary);
  font-size: 0.67rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}

.wide-toggle-btn:hover {
  color: var(--color-ink);
  border-color: var(--color-line-strong);
}

@media (max-width: 700px) {
  .coverage-strip {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .coverage-exchanges {
    order: 5;
    flex-basis: 100%;
  }
}

.ladder-hint {
  font-size: 0.65rem;
  color: var(--color-ink-tertiary);
  font-weight: 500;
}

.ladder-table tbody tr.ladder-row {
  cursor: pointer;
  transition: all var(--duration-fast, 160ms) ease;
}

.ladder-table tbody tr.ladder-row:hover {
  background: rgba(6, 182, 212, 0.08);
}

.ladder-table tbody tr.ladder-row.is-active {
  background: rgba(6, 182, 212, 0.14);
}

.contract-cell {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.contract-name {
  font-family: var(--font-numeric, monospace);
  font-weight: 600;
  color: var(--color-ink, #0f172a);
}

.badge-active {
  display: inline-block;
  padding: 0.1rem 0.35rem;
  font-size: 0.58rem;
  font-weight: 600;
  border-radius: var(--radius-pill, 9999px);
  background: rgba(6, 182, 212, 0.2);
  color: #0891b2;
  border: 1px solid rgba(6, 182, 212, 0.4);
}

.action-col {
  text-align: right;
  white-space: nowrap;
}

.btn-select-contract {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm, 4px);
  border: 1px solid var(--color-line);
  background: white;
  color: var(--color-ink-secondary);
  font-size: 0.64rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast, 160ms) ease;
}

.ladder-row:hover .btn-select-contract:not(.active) {
  border-color: #06b6d4;
  color: #0891b2;
  background: rgba(6, 182, 212, 0.1);
}

.btn-select-contract.active {
  background: #06b6d4;
  border-color: #06b6d4;
  color: #ffffff;
}

.font-mono {
  font-family: var(--font-numeric, monospace);
  font-weight: 600;
}
</style>

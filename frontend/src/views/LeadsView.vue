<script setup lang="ts">
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart2,
  BrainCircuit,
  Check,
  ChevronRight,
  Copy,
  ExternalLink,
  Filter,
  Flame,
  Layers,
  LineChart,
  Newspaper,
  Radar,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import Pagination from '../components/Pagination.vue'
import {usePagination} from '../composables/usePagination'
import AsyncState from '../components/AsyncState.vue'
import FreshnessBadge from '../components/FreshnessBadge.vue'
import { api, type OpportunityLead, type LeadsResponse } from '../services/api'
import {instrumentPath,researchPath} from '../utils/marketNavigation'
import { useMarketStore } from '../stores/market'
import { formatNumber, formatPct, formatTime } from '../utils/format'

const router = useRouter()
const marketStore = useMarketStore()

const state = ref<'idle' | 'loading' | 'ready' | 'error'>('loading')
const errorMessage = ref<string | undefined>(undefined)
const responseData = ref<LeadsResponse | null>(null)
const copiedId = ref<string | null>(null)

const asyncState = computed<'loading' | 'error' | 'ready'>(() => {
  if (state.value === 'idle' || state.value === 'loading') return 'loading'
  if (state.value === 'error') return 'error'
  return 'ready'
})

// 过滤器状态
const selectedAlgorithm = ref<string>('ALL')
const selectedDirection = ref<string>('ALL')
const selectedUrgency = ref<string>('ALL')
const sortBy = ref<'urgency' | 'score' | 'change' | 'confidence'>('urgency')
const searchKeyword = ref<string>('')

const algorithmOptions = [
  { value: 'ALL', label: '全部算法' },
  { value: 'DIMENSION_RESONANCE', label: '十四维全息共振' },
  { value: 'MOMENTUM_BREAKOUT', label: '量价动能突破' },
  { value: 'SUPPLY_DEMAND', label: '供需基本面错配' },
  { value: 'SENTIMENT_NEWS', label: '突发消息舆情' },
  { value: 'TERM_STRUCTURE', label: '期限结构套利' },
  { value: 'CYCLE_PIVOT', label: '时空周期变盘' },
]

async function loadLeads() {
  state.value = 'loading'
  errorMessage.value = undefined
  try {
    const data = await api.leads()
    responseData.value = data
    state.value = 'ready'
  } catch (err: any) {
    errorMessage.value = err?.message || '获取线索池数据失败，请重试'
    state.value = 'error'
  }
}


onMounted(() => {
  void loadLeads()
})

const leads = computed(() => responseData.value?.leads || [])

const filteredLeads = computed(() => {
  let list = [...leads.value]

  if (selectedAlgorithm.value !== 'ALL') {
    list = list.filter((l) => l.algorithmType === selectedAlgorithm.value)
  }

  if (selectedDirection.value !== 'ALL') {
    list = list.filter((l) => l.direction === selectedDirection.value)
  }

  if (selectedUrgency.value !== 'ALL') {
    list = list.filter((l) => l.urgency === selectedUrgency.value)
  }

  if (searchKeyword.value.trim()) {
    const kw = searchKeyword.value.trim().toLowerCase()
    list = list.filter(
      (l) =>
        l.symbol.toLowerCase().includes(kw) ||
        l.displayName.toLowerCase().includes(kw) ||
        l.signal.toLowerCase().includes(kw) ||
        l.algorithmName.toLowerCase().includes(kw),
    )
  }

  list.sort((a, b) => {
    if (sortBy.value === 'urgency') {
      const weight: Record<string, number> = { S: 3, A: 2, B: 1 }
      const diff = (weight[b.urgency] || 0) - (weight[a.urgency] || 0)
      if (diff !== 0) return diff
      return Math.abs(b.compositeScore) - Math.abs(a.compositeScore)
    }
    if (sortBy.value === 'score') {
      return Math.abs(b.compositeScore) - Math.abs(a.compositeScore)
    }
    if (sortBy.value === 'change') {
      return Math.abs(b.changePct) - Math.abs(a.changePct)
    }
    if (sortBy.value === 'confidence') {
      return b.confidence - a.confidence
    }
    return 0
  })

  return list
})

// 统计量
const stats = computed(() => {
  const total = leads.value.length
  const sCount = leads.value.filter((l) => l.urgency === 'S').length
  const bullCount = leads.value.filter((l) => l.direction === 'BULLISH').length
  const bearCount = leads.value.filter((l) => l.direction === 'BEARISH').length
  return { total, sCount, bullCount, bearCount }
})

function copyDirective(lead: OpportunityLead) {
  const text = `【AI-QUANT 研究线索】${lead.displayName}(${lead.symbol})\n数据状态：${lead.dataStatus}\n观测时间：${lead.dataTimestamp || lead.discoveredAt}\n方向：${lead.direction === 'BULLISH' ? '偏多' : '偏空'}\n模型：${lead.algorithmName}\n模型说明：${lead.execution.actionDirective}\n参考价格：${lead.execution.entryZone}\n目标参考：${formatNumber(lead.execution.targetPrice)}\n失效参考：${formatNumber(lead.execution.stopLossPrice)}\n仓位上限：${lead.execution.recommendedPositionPct}%\n风险收益比：${lead.execution.riskRewardRatio}\n\n仅供研究，不构成投资建议或实盘交易指令。`
  navigator.clipboard.writeText(text).then(() => {
    copiedId.value = lead.id
    setTimeout(() => {
      if (copiedId.value === lead.id) copiedId.value = null
    }, 2000)
  })
}

function navigateToMarket(symbol: string) {
  router.push(instrumentPath(symbol))
}

function navigateToStrategy(symbol: string) {
  router.push(researchPath(symbol))
}
const {items:pagedLeads,page:leadPage,total:leadTotal}=usePagination(filteredLeads,12,[selectedAlgorithm,selectedDirection,selectedUrgency,sortBy,searchKeyword])
</script>

<template>
  <div class="page-stack leads-view">
    <!-- 顶部概览横幅 -->
    <section class="leads-header">
      <div class="leads-header__main">
        <div class="leads-header__title">
          <div class="radar-tag">
            <Radar :size="18" class="radar-icon pulse" />
            <span>实时机会扫描雷达</span>
          </div>
          <h2>智能线索池 · 品种机会推荐</h2>
          <p class="leads-header__desc">
            扫描已配置品种，并仅展示当前数据源实际返回的维度证据。文化维度为非实证参考；线索不是实盘交易指令。
          </p>
        </div>

        <div class="leads-header__action">
          <button
            class="refresh-btn"
            :disabled="state === 'loading'"
            @click="loadLeads"
          >
            <RefreshCw :size="16" :class="{ spinning: state === 'loading' }" />
            <span>{{ state === 'loading' ? '正在扫描配置品种...' : '重新扫描线索' }}</span>
          </button>
          <span v-if="responseData?.dataTimestamp" class="update-time">
            更新于 {{ formatTime(responseData.dataTimestamp) }}
          </span>
        </div>
      </div>

      <!-- 核心指标统计条 -->
      <div class="stats-strip">
        <div class="stat-card">
          <span class="stat-label">扫描候选标的</span>
          <strong class="stat-val">{{ responseData?.scannedCount ?? '—' }} <small>个品种</small></strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">发现机会线索</span>
          <strong class="stat-val accent">{{ stats.total }} <small>条有效</small></strong>
        </div>
        <div class="stat-card s-level">
          <span class="stat-label">
            <Flame :size="14" class="flame-icon" /> S级阈值信号
          </span>
          <strong class="stat-val danger">{{ stats.sCount }} <small>个高阈值</small></strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">多空线索分布</span>
          <div class="multidirection-bar">
            <span class="bull-text"><TrendingUp :size="13" /> 多头 {{ stats.bullCount }}</span>
            <span class="separator">/</span>
            <span class="bear-text"><TrendingDown :size="13" /> 空头 {{ stats.bearCount }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 过滤器与控制栏 -->
    <section class="filter-panel">
      <div class="filter-group">
        <label><Filter :size="14" /> 算法类型</label>
        <div class="pill-tabs">
          <button
            v-for="opt in algorithmOptions"
            :key="opt.value"
            class="pill-tab"
            :class="{ active: selectedAlgorithm === opt.value }"
            @click="selectedAlgorithm = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <div class="filter-row-secondary">
        <div class="filter-subgroup">
          <span class="filter-label">方向：</span>
          <div class="mini-tabs">
            <button
              class="mini-tab"
              :class="{ active: selectedDirection === 'ALL' }"
              @click="selectedDirection = 'ALL'"
            >
              全部
            </button>
            <button
              class="mini-tab bull"
              :class="{ active: selectedDirection === 'BULLISH' }"
              @click="selectedDirection = 'BULLISH'"
            >
              多头看涨
            </button>
            <button
              class="mini-tab bear"
              :class="{ active: selectedDirection === 'BEARISH' }"
              @click="selectedDirection = 'BEARISH'"
            >
              空头看跌
            </button>
          </div>
        </div>

        <div class="filter-subgroup">
          <span class="filter-label">等级：</span>
          <div class="mini-tabs">
            <button
              class="mini-tab"
              :class="{ active: selectedUrgency === 'ALL' }"
              @click="selectedUrgency = 'ALL'"
            >
              全部
            </button>
            <button
              class="mini-tab s-tag"
              :class="{ active: selectedUrgency === 'S' }"
              @click="selectedUrgency = 'S'"
            >
              S 级
            </button>
            <button
              class="mini-tab a-tag"
              :class="{ active: selectedUrgency === 'A' }"
              @click="selectedUrgency = 'A'"
            >
              A 级
            </button>
            <button
              class="mini-tab b-tag"
              :class="{ active: selectedUrgency === 'B' }"
              @click="selectedUrgency = 'B'"
            >
              B 级
            </button>
          </div>
        </div>

        <div class="filter-subgroup">
          <span class="filter-label">排序：</span>
          <select v-model="sortBy" class="select-sort">
            <option value="urgency">机会等级优先 (S &gt; A &gt; B)</option>
            <option value="score">综合评分高低</option>
            <option value="change">盘面涨跌幅</option>
            <option value="confidence">指标内部评分（非胜率）</option>
          </select>
        </div>

        <div class="search-box">
          <Search :size="14" class="search-icon" />
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索品种代码/名称/关键词..."
          />
        </div>
      </div>
    </section>

    <!-- 状态反馈 -->
    <AsyncState :state="asyncState" :error-message="errorMessage" @retry="loadLeads">
      <!-- 搜索空状态 -->
      <div v-if="filteredLeads.length === 0" class="empty-leads">
        <Radar :size="48" class="empty-icon" />
        <h3>未发现匹配的交易机会线索</h3>
        <p>当前筛选条件下无满足阈值的线索，建议放宽筛选条件或点击右上角重新扫描全网。</p>
        <button class="reset-filter-btn" @click="selectedAlgorithm = 'ALL'; selectedDirection = 'ALL'; selectedUrgency = 'ALL'; searchKeyword = ''">
          重置所有筛选
        </button>
      </div>

      <!-- 线索列表卡片网格 -->
      <div v-else class="leads-grid">
        <article
          v-for="lead in pagedLeads"
          :key="lead.id"
          class="lead-card"
          :class="[
            lead.direction === 'BULLISH' ? 'lead-card--bullish' : 'lead-card--bearish',
            `urgency--${lead.urgency.toLowerCase()}`
          ]"
        >
          <!-- 卡片头部：标的信息、最新行情、等级徽章 -->
          <header class="card-head">
            <div class="instrument-title-wrap">
              <div class="badges-row">
                <span class="urgency-badge" :class="`badge-${lead.urgency.toLowerCase()}`">
                  {{ lead.urgency }} 级机会
                </span>
                <span class="algorithm-badge">
                  <Sparkles :size="12" />
                  {{ lead.algorithmBadge }}
                </span>
                <span class="exchange-badge">{{ lead.exchange }}</span>
              </div>
              <h3 class="instrument-name">
                <span class="sym-text">{{ lead.symbol }}</span>
                <span class="display-text">{{ lead.displayName }}</span>
              </h3>
            </div>

            <!-- 行情报价区：中国习惯红涨绿跌 -->
            <div class="quote-stat">
              <div class="price-val">{{ formatNumber(lead.price) }}</div>
              <div class="change-tag" :class="lead.change >= 0 ? 'positive' : 'negative'">
                <component :is="lead.change >= 0 ? ArrowUpRight : ArrowDownRight" :size="16" />
                <span>{{ lead.change >= 0 ? '+' : '' }}{{ formatNumber(lead.change) }}</span>
                <span>({{ formatPct(lead.changePct) }})</span>
              </div>
            </div>
          </header>

          <!-- 核心信号指示栏 -->
          <div class="signal-banner" :class="lead.direction === 'BULLISH' ? 'signal-bull' : 'signal-bear'">
            <div class="signal-tag">
              <component :is="lead.direction === 'BULLISH' ? TrendingUp : TrendingDown" :size="16" />
              <strong>{{ lead.direction === 'BULLISH' ? '看多做多' : '看空做空' }}</strong>
            </div>
            <span class="signal-desc">{{ lead.signal }}</span>
            <div class="score-pill">
              <span>评分</span>
              <b>{{ Math.round(lead.compositeScore) }}</b>
            </div>
          </div>

          <!-- 分析说明区 (Analysis) -->
          <div class="card-section analysis-section">
            <div class="section-title">
              <Newspaper :size="15" />
              <span>模型证据与数据边界</span>
            </div>

            <!-- 核心起因 -->
            <div class="analysis-box anomaly-box">
              <div class="box-label">
                <Zap :size="13" class="zap-icon" /> 核心异动起因
              </div>
              <p class="box-content">{{ lead.analysis.coreAnomaly }}</p>
            </div>

            <!-- 盘面与量价 -->
            <div class="analysis-box">
              <div class="box-label">
                <BarChart2 :size="13" /> 盘面走势与量价动能
              </div>
              <p class="box-content">{{ lead.analysis.marketContext }}</p>
            </div>

            <!-- 实时消息驱动 -->
            <div class="analysis-box">
              <div class="box-label">
                <Newspaper :size="13" /> 实时消息与产业链动态
              </div>
              <p class="box-content">{{ lead.analysis.newsDriver }}</p>
            </div>

            <!-- 关键维度证据条 -->
            <div v-if="lead.analysis.keyEvidence?.length" class="evidence-block">
              <div class="evidence-title">关键量化维度佐证：</div>
              <div class="evidence-list">
                <div
                  v-for="(ev, idx) in lead.analysis.keyEvidence"
                  :key="idx"
                  class="evidence-chip"
                >
                  <span class="chip-name">{{ ev.name }}</span>
                  <span
                    v-if="ev.score !== null"
                    class="chip-score"
                    :class="ev.score >= 0 ? 'positive' : 'negative'"
                  >
                    {{ ev.score > 0 ? '+' : '' }}{{ Math.round(ev.score) }}分
                  </span>
                  <span class="chip-summary">{{ ev.summary }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 具体操作指引区 (Execution) -->
          <div class="card-section execution-section">
            <div class="section-title">
              <ShieldAlert :size="15" />
              <span>量化研究参考</span>
            </div>

            <div class="directive-highlight">
              <div class="directive-label">操作方针</div>
              <div class="directive-text">{{ lead.execution.actionDirective }}</div>
            </div>

            <!-- 关键执行价格与仓位参数网格 -->
            <div class="execution-params-grid">
              <div class="param-box">
                <span class="param-name">入场参考区间</span>
                <strong class="param-val accent-val">{{ lead.execution.entryZone }}</strong>
              </div>
              <div class="param-box">
                <span class="param-name">止盈目标价格</span>
                <strong class="param-val target-val">{{ formatNumber(lead.execution.targetPrice) }}</strong>
              </div>
              <div class="param-box">
                <span class="param-name">硬止损防守价</span>
                <strong class="param-val stop-val">{{ formatNumber(lead.execution.stopLossPrice) }}</strong>
              </div>
              <div class="param-box">
                <span class="param-name">模型仓位上限</span>
                <strong class="param-val">{{ lead.execution.recommendedPositionPct }}%</strong>
              </div>
              <div class="param-box">
                <span class="param-name">预期盈亏比</span>
                <strong class="param-val rr-val">{{ lead.execution.riskRewardRatio }}</strong>
              </div>
              <div class="param-box">
                <span class="param-name">内部评分 · 非胜率</span>
                <strong class="param-val">{{ Math.round(lead.confidence * 100) }}%</strong>
              </div>
            </div>

            <!-- 失效条件 -->
            <div class="invalidation-box">
              <span class="inval-label">⚠️ 失效观察条件：</span>
              <span class="inval-text">{{ lead.execution.invalidationCondition }}</span>
            </div>
          </div>

          <!-- 卡片底部联动操作按钮 -->
          <footer class="card-foot">
            <div class="foot-actions">
              <button
                class="foot-btn btn-secondary"
                type="button"
                @click="copyDirective(lead)"
              >
                <component :is="copiedId === lead.id ? Check : Copy" :size="14" />
                <span>{{ copiedId === lead.id ? '已复制研究摘要' : '复制研究摘要' }}</span>
              </button>

              <button
                class="foot-btn btn-primary"
                type="button"
                @click="navigateToMarket(lead.symbol)"
              >
                <LineChart :size="14" />
                <span>通达信交互行情</span>
              </button>

              <button
                class="foot-btn btn-primary"
                type="button"
                @click="navigateToStrategy(lead.symbol)"
              >
                <BrainCircuit :size="14" />
                <span>十四维量化研判</span>
              </button>
            </div>
          </footer>
        </article>
      </div>
      <Pagination v-model:page="leadPage" :page-size="12" :total="leadTotal" label="线索分页" />
    </AsyncState>
  </div>
</template>

<style scoped>
.leads-view {
  display: grid;
  gap: var(--space-6);
  padding-bottom: var(--space-12);
}

/* 顶部概览 */
.leads-header {
  display: grid;
  gap: var(--space-5);
  padding: var(--space-6);
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--color-surface-raised) 0%, var(--color-surface) 100%);
  border: 1px solid var(--color-line);
  box-shadow: var(--shadow-raised);
}

.leads-header__main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.radar-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-pill);
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-size: 0.78rem;
  font-weight: 600;
  margin-bottom: var(--space-2);
}

.pulse {
  animation: pulse-ring 2s infinite ease-in-out;
}

@keyframes pulse-ring {
  0% { transform: scale(0.95); opacity: 0.8; }
  50% { transform: scale(1.15); opacity: 1; }
  100% { transform: scale(0.95); opacity: 0.8; }
}

.leads-header__title h2 {
  font-size: 1.45rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0 0 var(--space-2);
  color: var(--color-ink);
}

.leads-header__desc {
  font-size: 0.88rem;
  color: var(--color-ink-secondary);
  max-width: 58rem;
  line-height: 1.55;
  margin: 0;
}

.leads-header__action {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-2);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-pill);
  background: var(--color-ink);
  color: #fff;
  border: none;
  font-size: 0.86rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--color-accent);
  transform: translateY(-1px);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}

.update-time {
  font-size: 0.75rem;
  color: var(--color-ink-tertiary);
}

/* 统计条 */
.stats-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-line);
}

.stat-card {
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.stat-card.s-level {
  background: #fff8f6;
  border-color: #f7c5be;
}

.stat-label {
  font-size: 0.78rem;
  color: var(--color-ink-secondary);
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.flame-icon {
  color: #d93025;
}

.stat-val {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-ink);
  font-family: var(--font-numeric);
}

.stat-val.accent {
  color: var(--color-accent);
}

.stat-val.danger {
  color: #d93025;
}

.stat-val small {
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--color-ink-secondary);
  margin-left: 0.2rem;
}

.multidirection-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: 0.25rem;
  font-size: 0.88rem;
  font-weight: 700;
  font-family: var(--font-numeric);
}

.bull-text {
  color: var(--color-positive);
  display: flex;
  align-items: center;
  gap: 0.15rem;
}

.bear-text {
  color: var(--color-negative);
  display: flex;
  align-items: center;
  gap: 0.15rem;
}

.separator {
  color: var(--color-line-strong);
}

/* 筛选面板 */
.filter-panel {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
}

.filter-group {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.filter-group label {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--color-ink-secondary);
  display: flex;
  align-items: center;
  gap: 0.25rem;
  white-space: nowrap;
}

.pill-tabs {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.pill-tab {
  padding: 0.3rem 0.75rem;
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  color: var(--color-ink-secondary);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.pill-tab:hover {
  background: var(--color-line);
  color: var(--color-ink);
}

.pill-tab.active {
  background: var(--color-ink);
  color: #fff;
  border-color: var(--color-ink);
}

.filter-row-secondary {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
  padding-top: var(--space-2);
  border-top: 1px solid #f0ede6;
}

.filter-subgroup {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.filter-label {
  font-size: 0.8rem;
  color: var(--color-ink-secondary);
  white-space: nowrap;
}

.mini-tabs {
  display: flex;
  gap: 0.25rem;
  background: var(--color-surface);
  padding: 0.15rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-line);
}

.mini-tab {
  padding: 0.2rem 0.55rem;
  border-radius: calc(var(--radius-sm) - 2px);
  background: transparent;
  border: none;
  font-size: 0.78rem;
  color: var(--color-ink-secondary);
  cursor: pointer;
}

.mini-tab.active {
  background: #fff;
  color: var(--color-ink);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}

.mini-tab.bull.active {
  color: var(--color-positive);
  background: var(--color-positive-soft);
}

.mini-tab.bear.active {
  color: var(--color-negative);
  background: var(--color-negative-soft);
}

.mini-tab.s-tag.active {
  color: #c5221f;
  background: #fce8e6;
}

.select-sort {
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-line);
  background: #fff;
  font-size: 0.8rem;
  color: var(--color-ink);
}

.search-box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0.25rem 0.6rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-line);
  background: #fff;
  margin-left: auto;
}

.search-box input {
  border: none;
  outline: none;
  font-size: 0.8rem;
  background: transparent;
  width: 11rem;
}

.search-icon {
  color: var(--color-ink-tertiary);
}

/* 空状态 */
.empty-leads {
  text-align: center;
  padding: var(--space-12) var(--space-4);
  background: var(--color-surface-raised);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.empty-icon {
  color: var(--color-ink-tertiary);
  margin-bottom: var(--space-2);
}

.empty-leads h3 {
  font-size: 1.15rem;
  margin: 0;
  color: var(--color-ink);
}

.empty-leads p {
  color: var(--color-ink-secondary);
  font-size: 0.88rem;
  max-width: 28rem;
  margin: 0 0 var(--space-3);
}

.reset-filter-btn {
  padding: 0.35rem 0.9rem;
  border-radius: var(--radius-pill);
  background: var(--color-accent-soft);
  color: var(--color-accent);
  border: none;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
}

/* 线索卡片网格 */
.leads-grid {
  display: grid;
  gap: var(--space-6);
}

.lead-card {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  overflow: hidden;
  transition: transform var(--duration-fast) var(--ease-out), box-shadow var(--duration-fast) var(--ease-out);
}

.lead-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}

.lead-card--bullish {
  border-top: 4px solid var(--color-positive);
}

.lead-card--bearish {
  border-top: 4px solid var(--color-negative);
}

/* 卡片头部 */
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--color-line);
  flex-wrap: wrap;
  gap: var(--space-3);
}

.badges-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: 0.35rem;
}

.urgency-badge {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-pill);
  text-transform: uppercase;
}

.badge-s {
  background: #fce8e6;
  color: #c5221f;
  border: 1px solid #f7c5be;
}

.badge-a {
  background: #fef7e0;
  color: #b06000;
  border: 1px solid #fce293;
}

.badge-b {
  background: #e8f0fe;
  color: #1967d2;
  border: 1px solid #aecbfa;
}

.algorithm-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.15rem 0.55rem;
  border-radius: var(--radius-pill);
  background: #f1f3f4;
  color: var(--color-ink-secondary);
}

.exchange-badge {
  font-size: 0.72rem;
  color: var(--color-ink-tertiary);
  padding: 0.1rem 0.4rem;
  background: #faf9f6;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
}

.instrument-name {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin: 0;
}

.sym-text {
  font-size: 1.35rem;
  font-weight: 700;
  font-family: var(--font-numeric);
  color: var(--color-ink);
}

.display-text {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--color-ink-secondary);
}

.quote-stat {
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
}

.price-val {
  font-size: 1.6rem;
  font-weight: 700;
  font-family: var(--font-numeric);
  color: var(--color-ink);
}

.change-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  padding: 0.25rem 0.55rem;
  border-radius: var(--radius-sm);
  font-size: 0.88rem;
  font-weight: 700;
  font-family: var(--font-numeric);
}

.change-tag.positive {
  color: var(--color-positive);
  background: var(--color-positive-soft);
}

.change-tag.negative {
  color: var(--color-negative);
  background: var(--color-negative-soft);
}

/* 核心信号指示栏 */
.signal-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-6);
  gap: var(--space-3);
  flex-wrap: wrap;
}

.signal-bull {
  background: #fdf2f0;
  border-bottom: 1px solid #f9d8d5;
}

.signal-bear {
  background: #edf7f0;
  border-bottom: 1px solid #c9ebd4;
}

.signal-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.92rem;
  font-weight: 700;
}

.signal-bull .signal-tag {
  color: var(--color-positive);
}

.signal-bear .signal-tag {
  color: var(--color-negative);
}

.signal-desc {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--color-ink);
  flex: 1;
}

.score-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-pill);
  background: rgba(255,255,255,0.8);
  font-size: 0.82rem;
}

.score-pill span {
  color: var(--color-ink-secondary);
}

.score-pill b {
  font-family: var(--font-numeric);
  font-size: 1.05rem;
  color: var(--color-ink);
}

/* 卡片内容区块 */
.card-section {
  padding: var(--space-5) var(--space-6);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--color-ink-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: var(--space-3);
}

/* 分析说明区样式 */
.analysis-section {
  display: grid;
  gap: var(--space-3);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-line);
}

.analysis-box {
  padding: var(--space-3) var(--space-4);
  background: #fff;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
}

.anomaly-box {
  background: #fbfbfc;
  border-left: 3px solid var(--color-accent);
}

.box-label {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--color-ink-secondary);
  margin-bottom: 0.25rem;
}

.zap-icon {
  color: #e37400;
}

.box-content {
  font-size: 0.88rem;
  color: var(--color-ink);
  line-height: 1.6;
  margin: 0;
  white-space: pre-line;
}

.evidence-block {
  padding-top: var(--space-1);
}

.evidence-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--color-ink-secondary);
  margin-bottom: var(--space-2);
}

.evidence-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: var(--space-2);
}

.evidence-chip {
  padding: 0.35rem 0.6rem;
  border-radius: var(--radius-sm);
  background: #fff;
  border: 1px solid var(--color-line);
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.chip-name {
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--color-ink);
}

.chip-score {
  font-size: 0.75rem;
  font-weight: 700;
  font-family: var(--font-numeric);
}

.chip-score.positive {
  color: var(--color-positive);
}

.chip-score.negative {
  color: var(--color-negative);
}

.chip-summary {
  font-size: 0.75rem;
  color: var(--color-ink-secondary);
  line-height: 1.4;
  white-space: pre-line;
}

/* 具体操作区样式 */
.execution-section {
  display: grid;
  gap: var(--space-4);
  background: #fff;
}

.directive-highlight {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #1b2838 0%, #2a3a4f 100%);
  color: #fff;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.directive-label {
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #a0aec0;
}

.directive-text {
  font-size: 1.05rem;
  font-weight: 600;
  line-height: 1.4;
  color: #f7fafc;
}

.execution-params-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
  gap: var(--space-2);
}

.param-box {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.param-name {
  font-size: 0.72rem;
  color: var(--color-ink-secondary);
}

.param-val {
  font-size: 1.05rem;
  font-weight: 700;
  font-family: var(--font-numeric);
  color: var(--color-ink);
}

.accent-val {
  color: var(--color-accent);
}

.target-val {
  color: var(--color-positive);
}

.stop-val {
  color: #5f6368;
}

.rr-val {
  color: #137333;
}

.invalidation-box {
  padding: 0.45rem 0.75rem;
  border-radius: var(--radius-sm);
  background: #fff8f0;
  border: 1px dashed #fbd38d;
  font-size: 0.8rem;
  line-height: 1.4;
}

.inval-label {
  font-weight: 600;
  color: #c05621;
}

.inval-text {
  color: #7b341e;
}

/* 卡片底栏 */
.card-foot {
  padding: var(--space-3) var(--space-6);
  border-top: 1px solid var(--color-line);
  background: var(--color-surface);
  display: flex;
  justify-content: flex-end;
}

.foot-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.foot-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.75rem;
  border-radius: var(--radius-pill);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.btn-secondary {
  background: #fff;
  border: 1px solid var(--color-line-strong);
  color: var(--color-ink);
}

.btn-secondary:hover {
  background: #f1f3f4;
}

.btn-primary {
  background: var(--color-accent);
  color: #fff;
  border: 1px solid var(--color-accent);
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}
</style>

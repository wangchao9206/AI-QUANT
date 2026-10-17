<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Sparkles,
  Info,
  CheckCircle2,
  SlidersHorizontal,
} from 'lucide-vue-next'
import type { Dimension } from '../services/api'

const props = withDefaults(
  defineProps<{
    dimensions: Dimension[]
    culturalDimensions?: Dimension[]
    title?: string
  }>(),
  {
    culturalDimensions: () => [],
    title: '量化指标多空全景柱状图',
  },
)

// 合并实证与文化维度
const allItems = computed(() => [
  ...props.dimensions,
  ...props.culturalDimensions,
])

// 过滤状态
type FilterTab = 'all' | 'empirical' | 'cultural' | 'bullish' | 'bearish'
const activeTab = ref<FilterTab>('all')

// 排序状态
type SortMode = 'default' | 'score-desc' | 'score-asc' | 'weight-desc'
const sortMode = ref<SortMode>('default')

// 选中的指标（供下方详细查看）
const selectedKey = ref<string | null>(null)

// 简写映射表（柱状图紧凑排版）
const shortNameMap: Record<string, string> = {
  momentum: '量价动能',
  weather: '气象物候',
  indicators: '技术指标',
  supply_demand: '供需压力',
  execution: '执行风险',
  positioning: '持仓拥挤',
  sentiment: '新闻舆情',
  policy: '交割规则',
  spread: '跨期价差',
  term_structure: '期限结构',
  liquidity: '流动状态',
  liuyao: '六爻时历',
  iching: '易经时序',
  qimen: '奇门九星',
}

// 多空统计（中国人最关注的多头与空头阵营实力对比）
const sentimentStats = computed(() => {
  let bullishCount = 0
  let bearishCount = 0
  let neutralCount = 0
  let bullishWeight = 0
  let bearishWeight = 0

  for (const item of allItems.value) {
    if (item.direction === 'BULLISH' || (item.score !== null && item.score > 15)) {
      bullishCount++
      bullishWeight += item.weight
    } else if (item.direction === 'BEARISH' || (item.score !== null && item.score < -15)) {
      bearishCount++
      bearishWeight += item.weight
    } else {
      neutralCount++
    }
  }

  return {
    bullishCount,
    bearishCount,
    neutralCount,
    bullishWeight: Math.round(bullishWeight * 100),
    bearishWeight: Math.round(bearishWeight * 100),
  }
})

// 根据过滤和排序筛选列表
const displayedItems = computed(() => {
  let list = allItems.value.slice()

  // 1. 过滤
  if (activeTab.value === 'empirical') {
    list = list.filter((i) => i.category === 'EMPIRICAL')
  } else if (activeTab.value === 'cultural') {
    list = list.filter((i) => i.category === 'CULTURAL_REFERENCE')
  } else if (activeTab.value === 'bullish') {
    list = list.filter((i) => i.direction === 'BULLISH' || (i.score !== null && i.score > 0))
  } else if (activeTab.value === 'bearish') {
    list = list.filter((i) => i.direction === 'BEARISH' || (i.score !== null && i.score < 0))
  }

  // 2. 排序
  if (sortMode.value === 'score-desc') {
    list.sort((a, b) => (b.score ?? -999) - (a.score ?? -999))
  } else if (sortMode.value === 'score-asc') {
    list.sort((a, b) => (a.score ?? 999) - (b.score ?? 999))
  } else if (sortMode.value === 'weight-desc') {
    list.sort((a, b) => b.weight - a.weight)
  }

  return list
})

// 默认选中第一个
const activeItem = computed(() => {
  if (selectedKey.value) {
    const found = allItems.value.find((i) => i.key === selectedKey.value)
    if (found) return found
  }
  return displayedItems.value[0] || null
})

function selectItem(key: string) {
  selectedKey.value = key
}

// 柱状图高度计算 (-100 ~ +100，0 为中线)
const chartHeight = 220
const baselineY = chartHeight / 2 // 110px 为 0 轴
const maxScoreHeight = 85 // 单向最大高度 85px

function getBarY(score: number | null): number {
  if (score === null || score === 0) return baselineY - 1
  if (score > 0) {
    const barH = (Math.min(100, score) / 100) * maxScoreHeight
    return baselineY - barH
  }
  return baselineY
}

function getBarHeight(score: number | null): number {
  if (score === null || score === 0) return 2
  return Math.max(3, (Math.min(100, Math.abs(score)) / 100) * maxScoreHeight)
}

function getBarColor(item: Dimension): string {
  if (item.score === null) return '#94a3b8'
  if (item.score > 15 || item.direction === 'BULLISH') return 'var(--color-bullish)' // 中国红
  if (item.score < -15 || item.direction === 'BEARISH') return 'var(--color-bearish)' // 中国绿
  return '#ca8a04' // 中性金黄
}
</script>

<template>
  <div class="indicator-histogram-container" role="region" aria-label="量化指标柱状图">
    <!-- 顶部多空力量战报（中国股民/期民核心看盘习惯） -->
    <header class="chart-header">
      <div class="sentiment-summary">
        <span class="camp camp--bullish" title="看多维度统计">
          <TrendingUp :size="15" />
          <b>看多 {{ sentimentStats.bullishCount }}</b>
          <small>权重 {{ sentimentStats.bullishWeight }}%</small>
        </span>
        <span class="camp camp--bearish" title="看空维度统计">
          <TrendingDown :size="15" />
          <b>看空 {{ sentimentStats.bearishCount }}</b>
          <small>权重 {{ sentimentStats.bearishWeight }}%</small>
        </span>
        <span class="camp camp--neutral" title="中性/观望维度统计">
          <Minus :size="15" />
          <b>中性 {{ sentimentStats.neutralCount }}</b>
        </span>
      </div>

      <!-- 控制工具栏（快速筛选与排序） -->
      <div class="chart-controls">
        <div class="filter-tabs" role="tablist">
          <button
            type="button"
            class="tab-btn"
            :class="{ active: activeTab === 'all' }"
            role="tab"
            :aria-selected="activeTab === 'all'"
            @click="activeTab = 'all'"
          >
            全部 ({{ allItems.length }})
          </button>
          <button
            type="button"
            class="tab-btn"
            :class="{ active: activeTab === 'empirical' }"
            role="tab"
            :aria-selected="activeTab === 'empirical'"
            @click="activeTab = 'empirical'"
          >
            实证 ({{ props.dimensions.length }})
          </button>
          <button
            v-if="props.culturalDimensions.length"
            type="button"
            class="tab-btn"
            :class="{ active: activeTab === 'cultural' }"
            role="tab"
            :aria-selected="activeTab === 'cultural'"
            @click="activeTab = 'cultural'"
          >
            文化 ({{ props.culturalDimensions.length }})
          </button>
          <button
            type="button"
            class="tab-btn tab-btn--bullish"
            :class="{ active: activeTab === 'bullish' }"
            role="tab"
            :aria-selected="activeTab === 'bullish'"
            @click="activeTab = 'bullish'"
          >
            看多 🔴
          </button>
          <button
            type="button"
            class="tab-btn tab-btn--bearish"
            :class="{ active: activeTab === 'bearish' }"
            role="tab"
            :aria-selected="activeTab === 'bearish'"
            @click="activeTab = 'bearish'"
          >
            看空 🟢
          </button>
        </div>

        <div class="sort-selector">
          <SlidersHorizontal :size="14" class="sort-icon" />
          <select v-model="sortMode" aria-label="指标排序">
            <option value="default">默认顺序</option>
            <option value="score-desc">多头强度 (由强到弱)</option>
            <option value="score-asc">空头强度 (由强到弱)</option>
            <option value="weight-desc">权重大小 (由大到小)</option>
          </select>
        </div>
      </div>
    </header>

    <!-- 柱状图主视图（红涨绿跌，0 轴水平基准） -->
    <div class="svg-stage-wrapper">
      <div class="axis-legend-left">
        <span class="legend-tick tick--bullish">+100 多</span>
        <span class="legend-tick">+50</span>
        <span class="legend-tick tick--zero">0 轴</span>
        <span class="legend-tick">-50</span>
        <span class="legend-tick tick--bearish">-100 空</span>
      </div>

      <div class="chart-scroll">
        <div class="bars-flex">
          <div
            v-for="item in displayedItems"
            :key="item.key"
            class="bar-column"
            :class="{
              'is-active': activeItem?.key === item.key,
              'is-cultural': item.category === 'CULTURAL_REFERENCE',
            }"
            role="button"
            tabindex="0"
            :aria-label="`${item.name}，评分 ${item.score ?? '不可用'}，查看详情`"
            @click="selectItem(item.key)"
            @keydown.enter="selectItem(item.key)"
            @keydown.space.prevent="selectItem(item.key)"
          >
            <!-- 柱形绘制区 -->
            <div class="bar-drawing-area" :style="{ height: `${chartHeight}px` }">
              <!-- 背景网格参考线 -->
              <span class="ref-line ref-line--top" />
              <span class="ref-line ref-line--zero" />
              <span class="ref-line ref-line--bottom" />

              <!-- 正分柱 (看多向上红柱) -->
              <div
                v-if="item.score !== null && item.score > 0"
                class="bar-rect bar-rect--bullish"
                :style="{
                  bottom: `${baselineY}px`,
                  height: `${getBarHeight(item.score)}px`,
                  backgroundColor: getBarColor(item),
                }"
              >
                <span class="bar-value-label bar-value-label--top">
                  +{{ Math.round(item.score) }}
                </span>
              </div>

              <!-- 负分柱 (看空向下绿柱) -->
              <div
                v-else-if="item.score !== null && item.score < 0"
                class="bar-rect bar-rect--bearish"
                :style="{
                  top: `${baselineY}px`,
                  height: `${getBarHeight(item.score)}px`,
                  backgroundColor: getBarColor(item),
                }"
              >
                <span class="bar-value-label bar-value-label--bottom">
                  {{ Math.round(item.score) }}
                </span>
              </div>

              <!-- 零分或不可用中性柱 -->
              <div
                v-else
                class="bar-rect bar-rect--zero"
                :style="{
                  top: `${baselineY - 2}px`,
                  height: '4px',
                }"
              >
                <span class="bar-value-label bar-value-label--mid">
                  {{ item.dataStatus === 'UNAVAILABLE' ? 'N/A' : '0' }}
                </span>
              </div>
            </div>

            <!-- X 轴指标名称与权重 -->
            <div class="bar-footer">
              <strong class="indicator-name" :title="item.name">
                {{ shortNameMap[item.key] || item.name.slice(0, 4) }}
              </strong>
              <span
                class="weight-badge"
                :class="{ 'weight-badge--cultural': item.category === 'CULTURAL_REFERENCE' }"
              >
                {{ Math.round(item.weight * 100) }}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部选定指标的量化研判卡片 -->
    <footer v-if="activeItem" class="indicator-detail-panel">
      <div class="detail-header">
        <div class="detail-title-line">
          <h4>{{ activeItem.name }}</h4>
          <span
            class="direction-pill"
            :class="{
              'pill--bullish': activeItem.direction === 'BULLISH' || (activeItem.score ?? 0) > 15,
              'pill--bearish': activeItem.direction === 'BEARISH' || (activeItem.score ?? 0) < -15,
              'pill--neutral': activeItem.direction === 'NEUTRAL' || activeItem.dataStatus === 'REFERENCE',
            }"
          >
            {{
              activeItem.direction === 'BULLISH'
                ? '看多 (Bullish)'
                : activeItem.direction === 'BEARISH'
                ? '看空 (Bearish)'
                : activeItem.dataStatus === 'UNAVAILABLE'
                ? '数据源不可用'
                : '中性 / 辅助参考'
            }}
          </span>
          <span class="category-tag">
            {{ activeItem.category === 'EMPIRICAL' ? '实证量化模型' : '中华时历参考' }}
          </span>
        </div>

        <div class="detail-metrics-chips">
          <span class="chip">
            得分:
            <strong :style="{ color: getBarColor(activeItem) }">
              {{ activeItem.score !== null ? `${activeItem.score > 0 ? '+' : ''}${Math.round(activeItem.score)}` : '无' }}
            </strong>
          </span>
          <span class="chip">权重: <strong>{{ Math.round(activeItem.weight * 100) }}%</strong></span>
          <span v-if="activeItem.confidence !== null" class="chip">
            指标内部评分（非胜率）: <strong>{{ Math.round(activeItem.confidence * 100) }}%</strong>
          </span>
          <span class="chip">样本: <strong>{{ activeItem.sampleSize }}</strong></span>
        </div>
      </div>

      <p class="detail-summary">{{ activeItem.summary }}</p>

      <!-- 核心指标量化明细 -->
      <dl v-if="Object.keys(activeItem.keyMetrics).length" class="detail-key-metrics">
        <div v-for="(v, k) in activeItem.keyMetrics" :key="k" class="metric-item">
          <dt>{{ k }}</dt>
          <dd>{{ v }}</dd>
        </div>
      </dl>

      <div class="detail-recommendation">
        <CheckCircle2 :size="16" class="rec-icon" />
        <p><strong>研判建议：</strong>{{ activeItem.recommendation }}</p>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.indicator-histogram-container {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

/* 顶部中国式多空阵营看板 */
.chart-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-line);
}

.sentiment-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
}

.camp {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.28rem 0.65rem;
  border-radius: var(--radius-sm);
  font-size: 0.72rem;
  font-weight: 600;
}

.camp--bullish {
  color: var(--color-bullish);
  background: var(--color-bullish-soft);
  border: 1px solid rgba(217, 48, 37, 0.2);
}

.camp--bearish {
  color: var(--color-bearish);
  background: var(--color-bearish-soft);
  border: 1px solid rgba(30, 142, 62, 0.2);
}

.camp--neutral {
  color: var(--color-ink-secondary);
  background: #f1f0eb;
  border: 1px solid var(--color-line);
}

.camp small {
  margin-left: 0.2rem;
  font-size: 0.65rem;
  opacity: 0.85;
}

/* 控制按钮与排序 */
.chart-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
}

.filter-tabs {
  flex-wrap: wrap;
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  background: #f3f1ec;
}

.tab-btn {
  padding: 0.22rem 0.55rem;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--color-ink-secondary);
  font-size: 0.68rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.tab-btn.active {
  background: white;
  color: var(--color-ink);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.tab-btn--bullish.active {
  color: var(--color-bullish);
}

.tab-btn--bearish.active {
  color: var(--color-bearish);
}

.sort-selector {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.45rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  background: white;
  font-size: 0.68rem;
}

.sort-selector select {
  border: none;
  outline: none;
  background: transparent;
  font-size: 0.68rem;
  color: var(--color-ink-secondary);
  cursor: pointer;
}

.sort-icon {
  color: var(--color-ink-tertiary);
}

/* 柱状图主舞台 */
.svg-stage-wrapper {
  display: flex;
  gap: 0.5rem;
  min-height: 260px;
  padding: 0.5rem 0;
}

.axis-legend-left {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 48px;
  height: 220px;
  padding-right: 6px;
  border-right: 1px dashed var(--color-line);
  text-align: right;
}

.legend-tick {
  font-family: var(--font-numeric);
  font-size: 0.58rem;
  color: var(--color-ink-tertiary);
}

.tick--bullish {
  color: var(--color-bullish);
  font-weight: 700;
}

.tick--bearish {
  color: var(--color-bearish);
  font-weight: 700;
}

.tick--zero {
  color: var(--color-ink-secondary);
  font-weight: 700;
}

.chart-scroll {
  min-width: 0;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 0.5rem;
}

.bars-flex {
  display: flex;
  gap: 0.85rem;
  min-width: max-content;
  padding: 0 0.5rem;
}

.bar-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 46px;
  cursor: pointer;
  border-radius: 6px;
  padding: 2px;
  transition: transform 0.15s ease, background-color 0.15s ease;
}

.bar-column:hover {
  background-color: rgba(0, 0, 0, 0.03);
}

.bar-column.is-active {
  background-color: rgba(44, 99, 133, 0.08);
  outline: 1.5px solid var(--color-accent);
}

.bar-column.is-cultural {
  border-bottom: 2px solid #8b5cf6;
}

.bar-drawing-area {
  position: relative;
  width: 100%;
}

/* 参考虚线 */
.ref-line {
  position: absolute;
  left: 0;
  right: 0;
  border-top: 1px dashed #e2e8f0;
  pointer-events: none;
}

.ref-line--top {
  top: 25px;
}

.ref-line--zero {
  top: 110px;
  border-top: 1.5px solid #cbd5e1;
}

.ref-line--bottom {
  top: 195px;
}

/* 柱体 */
.bar-rect {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: 20px;
  border-radius: 3px;
  transition: height 0.25s ease, top 0.25s ease, bottom 0.25s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.bar-rect--bullish {
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
}

.bar-rect--bearish {
  border-bottom-left-radius: 4px;
  border-bottom-right-radius: 4px;
}

.bar-rect--zero {
  background: #cbd5e1;
  width: 14px;
}

/* 柱顶/柱底数值标签 */
.bar-value-label {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  font-family: var(--font-numeric);
  font-size: 0.62rem;
  font-weight: 700;
  white-space: nowrap;
}

.bar-value-label--top {
  top: -18px;
  color: var(--color-bullish);
}

.bar-value-label--bottom {
  bottom: -18px;
  color: var(--color-bearish);
}

.bar-value-label--mid {
  top: -16px;
  color: var(--color-ink-tertiary);
}

/* X 轴名称与权重 */
.bar-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  margin-top: 0.4rem;
}

.indicator-name {
  font-size: 0.68rem;
  font-weight: 650;
  color: var(--color-ink);
  white-space: nowrap;
}

.weight-badge {
  padding: 0.1rem 0.35rem;
  border-radius: var(--radius-pill);
  background: #f1f5f9;
  color: var(--color-ink-secondary);
  font-family: var(--font-numeric);
  font-size: 0.58rem;
  font-weight: 600;
}

.weight-badge--cultural {
  background: #f3e8ff;
  color: #7c3aed;
}

/* 底部指标研判卡片 */
.indicator-detail-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
  background: white;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
}

.detail-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.8rem;
  padding-bottom: 0.6rem;
  border-bottom: 1px solid #f1f0eb;
}

.detail-title-line {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.detail-title-line h4 {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-ink);
}

.direction-pill {
  padding: 0.2rem 0.55rem;
  border-radius: var(--radius-pill);
  font-size: 0.68rem;
  font-weight: 700;
}

.pill--bullish {
  background: var(--color-bullish-soft);
  color: var(--color-bullish);
  border: 1px solid rgba(217, 48, 37, 0.25);
}

.pill--bearish {
  background: var(--color-bearish-soft);
  color: var(--color-bearish);
  border: 1px solid rgba(30, 142, 62, 0.25);
}

.pill--neutral {
  background: #f1f5f9;
  color: var(--color-ink-secondary);
  border: 1px solid var(--color-line);
}

.category-tag {
  font-size: 0.64rem;
  color: var(--color-ink-tertiary);
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  background: #f8fafc;
}

.detail-metrics-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.chip {
  font-size: 0.68rem;
  color: var(--color-ink-secondary);
}

.chip strong {
  font-family: var(--font-numeric);
  color: var(--color-ink);
}

.detail-summary {
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--color-ink-secondary);
  white-space: pre-line;
}

.detail-key-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.2rem;
  margin: 0;
  padding: 0.65rem 0.85rem;
  border-radius: 6px;
  background: #f8fafc;
}

.metric-item {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  font-size: 0.68rem;
}

.metric-item dt {
  color: var(--color-ink-tertiary);
}

.metric-item dd {
  margin: 0;
  font-family: var(--font-numeric);
  font-weight: 600;
  color: var(--color-ink);
}

.detail-recommendation {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.65rem 0.85rem;
  border-radius: 6px;
  background: #fffdf5;
  border: 1px solid #fef3c7;
  color: #92400e;
  font-size: 0.72rem;
  line-height: 1.5;
}

.detail-recommendation p {
  margin: 0;
  white-space: pre-line;
}

.rec-icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: #d97706;
}

@media (max-width: 768px) {
  .chart-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .chart-controls {
    width: 100%;
    justify-content: space-between;
  }
}
</style>

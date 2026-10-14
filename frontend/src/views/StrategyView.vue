<script setup lang="ts">
import { CalendarClock, Crosshair, ShieldAlert } from 'lucide-vue-next'
import { computed } from 'vue'

import AsyncState from '../components/AsyncState.vue'
import DataPanel from '../components/DataPanel.vue'
import DimensionBars from '../components/DimensionBars.vue'
import FreshnessBadge from '../components/FreshnessBadge.vue'
import { useDashboard } from '../composables/useDashboard'
import { formatNumber, formatTime } from '../utils/format'

const { store, state, prediction, error } = useDashboard()
const asyncState = computed(() => state.value === 'idle' ? 'loading' : state.value)
</script>

<template>
  <div class="page-stack">
    <AsyncState :state="asyncState" :error-message="error" @retry="store.load()">
      <template v-if="prediction">
        <section class="strategy-header">
          <div>
            <div class="instrument-line"><span>{{ prediction.symbol }}</span><FreshnessBadge :status="prediction.dataStatus" :timestamp="prediction.dataTimestamp" /></div>
            <h2>{{ prediction.signal }}</h2>
            <p>{{ prediction.actionDirective }}</p>
          </div>
          <div class="score"><strong>{{ Math.round(prediction.compositeScore) }}</strong><span>综合分</span></div>
        </section>

        <div class="metric-grid strategy-metrics">
          <div class="metric"><span>建议仓位</span><strong>{{ formatNumber(prediction.recommendedPositionPct, 0) }}%</strong></div>
          <div class="metric"><span>目标价格</span><strong>{{ formatNumber(prediction.targetPrice) }}</strong></div>
          <div class="metric"><span>止损价格</span><strong>{{ formatNumber(prediction.stopLossPrice) }}</strong></div>
          <div class="metric"><span>置信度</span><strong>{{ Math.round(prediction.confidence * 100) }}%</strong></div>
        </div>

        <div class="page-grid">
          <DataPanel class="span-8" title="十一维真实量化证据" eyebrow="11 empirical dimensions · scored">
            <DimensionBars :dimensions="prediction.dimensions" />
          </DataPanel>
          <div class="span-4 side-stack">
            <DataPanel title="风险边界" eyebrow="Execution guardrail">
              <div class="boundary"><Crosshair :size="18" /><span>达到 {{ formatNumber(prediction.targetPrice) }} 分批止盈</span></div>
              <div class="boundary boundary--danger"><ShieldAlert :size="18" /><span>跌破 {{ formatNumber(prediction.stopLossPrice) }} 停止策略</span></div>
              <p class="disclaimer">策略输出是研究辅助信息，不构成收益承诺或自动下单授权。</p>
            </DataPanel>
            <DataPanel title="观察条件" eyebrow="Recalculation triggers">
              <ul class="events"><li v-for="event in prediction.eventWindows" :key="event"><CalendarClock :size="16" /><span>{{ event }}</span></li></ul>
            </DataPanel>
            <DataPanel title="可追溯性" eyebrow="Audit trail">
              <dl class="audit"><div><dt>模型版本</dt><dd>{{ prediction.modelVersion }}</dd></div><div><dt>数据时间</dt><dd>{{ formatTime(prediction.dataTimestamp) }}</dd></div><div><dt>Trace ID</dt><dd>{{ prediction.traceId }}</dd></div></dl>
            </DataPanel>
          </div>
        </div>

        <DataPanel class="culture-panel" title="中华传统文化时历参考" eyebrow="Cultural reference · 9% weight">
          <p class="culture-notice">六爻、易经与奇门基于当前真实时间与中国传统历法透明计算，融入中华数千年时历与卦象智慧，以辅助参考形式（各占 3% 权重，合计 9%）纳入综合决策评分，为量价信号提供时序背景参考。</p>
          <DimensionBars :dimensions="prediction.culturalReferences" reference />
        </DataPanel>
      </template>
    </AsyncState>
  </div>
</template>

<style scoped>
.strategy-header { display: flex; min-height: 15rem; align-items: center; justify-content: space-between; gap: 2rem; padding: clamp(1.5rem, 4vw, 3.2rem); color: white; border-radius: 1.5rem; background: #1b1d20; }
.instrument-line { display: flex; align-items: center; gap: .75rem; color: #9da2a7; font: 700 .7rem var(--font-numeric); letter-spacing: .1em; }
.strategy-header h2 { margin: .85rem 0 .5rem; font: 500 clamp(2rem, 5vw, 3.8rem) var(--font-display); letter-spacing: -.05em; }
.strategy-header p { max-width: 36rem; margin: 0; color: #b6b9bc; font-size: .82rem; line-height: 1.7; }
.score { min-width: 8.5rem; text-align: center; }
.score strong { display: block; font: 500 4.5rem var(--font-display); letter-spacing: -.07em; }
.score span { color: #92979c; font-size: .67rem; letter-spacing: .1em; }
.strategy-metrics { grid-template-columns: repeat(4, 1fr); }
.side-stack { display: grid; align-content: start; gap: var(--space-5); }
.boundary { display: flex; align-items: center; gap: .65rem; padding: .8rem 0; color: var(--color-positive); border-bottom: 1px solid var(--color-line); font-size: .73rem; }
.boundary--danger { color: var(--color-negative); }
.disclaimer { margin: .9rem 0 0; color: var(--color-ink-tertiary); font-size: .66rem; line-height: 1.55; }
.events { display: grid; gap: .8rem; padding: 0; margin: 0; list-style: none; }
.events li { display: flex; align-items: flex-start; gap: .6rem; color: var(--color-ink-secondary); font-size: .72rem; line-height: 1.5; }
.events svg { flex: none; color: var(--color-accent); }
.audit { display: grid; gap: .8rem; margin: 0; }
.audit div { display: grid; gap: .2rem; }
.audit dt { color: var(--color-ink-tertiary); font-size: .62rem; text-transform: uppercase; }
.audit dd { overflow-wrap: anywhere; margin: 0; font: .67rem var(--font-numeric); }
.culture-panel { margin-top: var(--space-6); }
.culture-notice { max-width: 58rem; margin: 0 0 1rem; padding: .75rem .9rem; color: #755b30; border: 1px solid #e6d8bc; border-radius: .75rem; background: #fffaf0; font-size: .7rem; line-height: 1.55; }
@media (max-width: 700px) { .strategy-header { align-items: flex-start; flex-direction: column; }.score { text-align: left; }.strategy-metrics { grid-template-columns: 1fr 1fr; } }
</style>

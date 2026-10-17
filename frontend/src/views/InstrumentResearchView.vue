<script setup lang="ts">
import { BarChart3, CalendarClock, Crosshair, ListFilter, ShieldAlert } from 'lucide-vue-next'
import { computed, ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'

import AsyncState from '../components/AsyncState.vue'
import DataPanel from '../components/DataPanel.vue'
import DimensionBars from '../components/DimensionBars.vue'
import FreshnessBadge from '../components/FreshnessBadge.vue'
import IndicatorBarChart from '../components/IndicatorBarChart.vue'
import ResearchWorkbench from '../components/ResearchWorkbench.vue'
import EvidenceSummary from '../components/EvidenceSummary.vue'
import {useExperience} from '../composables/useExperience'
import {instrumentPath} from '../utils/marketNavigation'
import { useDashboard } from '../composables/useDashboard'
import { formatNumber, formatTime } from '../utils/format'

const { store, state, prediction, error } = useDashboard()
const asyncState = computed(() => (state.value === 'idle' ? 'loading' : state.value))
const viewMode = ref<'barchart' | 'detail'>('barchart')
const route=useRoute()
const {isSimple}=useExperience()
watch([prediction,()=>route.hash],async()=>{
  if(route.hash!=='#trade-plan'||!prediction.value)return
  await nextTick()
  document.getElementById('trade-plan')?.scrollIntoView({block:'start'})
},{immediate:true,flush:'post'})
</script>

<template>
  <div class="page-stack">
    <nav class="research-breadcrumbs" aria-label="品种研究导航"><RouterLink to="/strategy">← 返回研究工具</RouterLink><RouterLink :to="instrumentPath(store.symbol)">查看品种行情 ↗</RouterLink></nav>
    <AsyncState :state="asyncState" :error-message="error" @retry="store.load()">
      <template v-if="prediction">
        <section v-if="isSimple" class="simple-research"><h2>{{prediction.displayName}}：先核对资料与依据</h2><p>研究结果用于提出观察方向，不是下单指令。先核对数据时间和可用证据，再按需展开风险情景与指标。</p><FreshnessBadge :status="prediction.dataStatus" :timestamp="prediction.dataTimestamp"/><RouterLink to="/learn#terms">模型分数为什么不是胜率？ ↗</RouterLink></section>
        <details class="research-disclosure" :open="!isSimple||route.hash==='#trade-plan'||route.query.stage==='review'"><summary>风险试算与计划复盘 · 手动输入账户情景</summary><ResearchWorkbench :symbol="store.symbol" :initial-tab="route.query.stage==='review'?'JOURNAL':'PLAN'" /></details>
        <DataPanel title="证据完整度与模型边界" eyebrow="证据核验"><EvidenceSummary :prediction="prediction" /></DataPanel>
        <details class="research-disclosure" :open="!isSimple"><summary>进阶查看：指标拆解、全维参考与模型边界</summary><div class="page-stack">
        <section class="strategy-header">
          <div>
            <div class="instrument-line">
              <span>{{ prediction.symbol }}</span>
              <FreshnessBadge :status="prediction.dataStatus" :timestamp="prediction.dataTimestamp" />
            </div>
            <h2>全维参考 · {{ prediction.signal }}</h2>
            <p>以下拆解包含文化参考；交易计划的模式、方向与风险以上方核算为准。</p>
          </div>
          <div class="score">
            <strong>{{ Math.round(prediction.compositeScore) }}</strong>
            <span>全维参考分 · 非胜率</span>
          </div>
        </section>

        <div class="metric-grid strategy-metrics">
          <div class="metric">
            <span>模型比例 · 非账户风险</span>
            <strong>{{ formatNumber(prediction.recommendedPositionPct*100, 1) }}%</strong>
          </div>
          <div class="metric">
            <span>目标价格</span>
            <strong>{{ formatNumber(prediction.targetPrice) }}</strong>
          </div>
          <div class="metric">
            <span>止损价格</span>
            <strong>{{ formatNumber(prediction.stopLossPrice) }}</strong>
          </div>
          <div class="metric">
            <span>盈利概率校准</span>
            <strong>未完成</strong>
          </div>
        </div>

        <!-- 视图切换栏：中国人使用习惯的多空柱状图 vs 经典指标列表 -->
        <div class="view-switch-bar">
          <div class="switch-title">
            <h3>量化指标研判</h3>
            <span class="switch-subtitle">
              包含 11 维真实量化实证指标 + 3 维中华传统时历指标（共 14 维度 · 红涨绿跌习惯）
            </span>
          </div>
          <div class="switch-tabs" role="tablist">
            <button
              type="button"
              class="switch-btn"
              :class="{ active: viewMode === 'barchart' }"
              role="tab"
              :aria-selected="viewMode === 'barchart'"
              @click="viewMode = 'barchart'"
            >
              <BarChart3 :size="15" />
              <span>多空柱状图 (红涨绿跌)</span>
            </button>
            <button
              type="button"
              class="switch-btn"
              :class="{ active: viewMode === 'detail' }"
              role="tab"
              :aria-selected="viewMode === 'detail'"
              @click="viewMode = 'detail'"
            >
              <ListFilter :size="15" />
              <span>逐项明细列表</span>
            </button>
          </div>
        </div>

        <!-- 柱状图模式 (默认激活，符合国内看盘与多空对比习惯) -->
        <div v-if="viewMode === 'barchart'" class="barchart-container">
          <IndicatorBarChart
            :dimensions="prediction.dimensions"
            :cultural-dimensions="prediction.culturalReferences"
          />

          <div class="page-grid guardrail-grid">
            <DataPanel class="span-4" title="风险边界" eyebrow="Execution guardrail">
              <div class="boundary">
                <Crosshair :size="18" />
                <span>{{ prediction.signal==='HOLD'?'等待方向，不生成目标建议':`参考目标 ${formatNumber(prediction.targetPrice)}` }}</span>
              </div>
              <div class="boundary boundary--danger">
                <ShieldAlert :size="18" />
                <span>{{ prediction.signal==='HOLD'?'保护价请结合实际持仓单独核算':`${prediction.stopLossPrice>prediction.price?'突破':'跌破'}参考保护价 ${formatNumber(prediction.stopLossPrice)}` }}</span>
              </div>
              <p class="disclaimer">策略输出是研究辅助信息，不构成收益承诺或自动下单授权。</p>
            </DataPanel>
            <DataPanel class="span-4" title="观察条件" eyebrow="Recalculation triggers">
              <ul class="events">
                <li v-for="event in prediction.eventWindows" :key="event">
                  <CalendarClock :size="16" />
                  <span>{{ event }}</span>
                </li>
              </ul>
            </DataPanel>
            <DataPanel class="span-4" title="可追溯性" eyebrow="Audit trail">
              <dl class="audit">
                <div>
                  <dt>模型版本</dt>
                  <dd>{{ prediction.modelVersion }}</dd>
                </div>
                <div>
                  <dt>数据时间</dt>
                  <dd>{{ formatTime(prediction.dataTimestamp) }}</dd>
                </div>
                <div>
                  <dt>Trace ID</dt>
                  <dd>{{ prediction.traceId }}</dd>
                </div>
              </dl>
            </DataPanel>
          </div>
        </div>

        <!-- 经典逐项明细列表模式 -->
        <div v-else class="detail-container">
          <div class="page-grid">
            <DataPanel class="span-8" title="十一维真实量化证据" eyebrow="11 empirical dimensions · scored">
              <DimensionBars :dimensions="prediction.dimensions" />
            </DataPanel>
            <div class="span-4 side-stack">
              <DataPanel title="风险边界" eyebrow="Execution guardrail">
                <div class="boundary">
                  <Crosshair :size="18" />
                  <span>{{ prediction.signal==='HOLD'?'等待方向，不生成目标建议':`参考目标 ${formatNumber(prediction.targetPrice)}` }}</span>
                </div>
                <div class="boundary boundary--danger">
                  <ShieldAlert :size="18" />
                  <span>{{ prediction.signal==='HOLD'?'保护价请结合实际持仓单独核算':`${prediction.stopLossPrice>prediction.price?'突破':'跌破'}参考保护价 ${formatNumber(prediction.stopLossPrice)}` }}</span>
                </div>
                <p class="disclaimer">策略输出是研究辅助信息，不构成收益承诺或自动下单授权。</p>
              </DataPanel>
              <DataPanel title="观察条件" eyebrow="Recalculation triggers">
                <ul class="events">
                  <li v-for="event in prediction.eventWindows" :key="event">
                    <CalendarClock :size="16" />
                    <span>{{ event }}</span>
                  </li>
                </ul>
              </DataPanel>
              <DataPanel title="可追溯性" eyebrow="Audit trail">
                <dl class="audit">
                  <div>
                    <dt>模型版本</dt>
                    <dd>{{ prediction.modelVersion }}</dd>
                  </div>
                  <div>
                    <dt>数据时间</dt>
                    <dd>{{ formatTime(prediction.dataTimestamp) }}</dd>
                  </div>
                  <div>
                    <dt>Trace ID</dt>
                    <dd>{{ prediction.traceId }}</dd>
                  </div>
                </dl>
              </DataPanel>
            </div>
          </div>

          <DataPanel class="culture-panel" title="中华传统文化时历参考" eyebrow="配置权重 9% · 实际比例随可用数据变化">
            <p class="culture-notice">
              <strong>非实证文化参考：</strong>六爻、易经与奇门基于当前真实时间与中国传统历法透明计算，以辅助参考形式（各占 3% 权重，合计 9%）纳入综合决策评分，不应被视为经过实证验证的市场信号。
            </p>
            <DimensionBars :dimensions="prediction.culturalReferences" reference />
          </DataPanel>
        </div>
        </div></details>
      </template>
    </AsyncState>
  </div>
</template>

<style scoped>
.research-breadcrumbs{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;font-size:.73rem}.research-breadcrumbs a{color:var(--color-accent);text-decoration:none}.simple-research{padding:1.5rem;border:1px solid var(--color-line);border-radius:.9rem;background:var(--color-surface)}.simple-research h2{font-size:1.1rem;margin:0}.simple-research p{font-size:.76rem;line-height:1.9;color:var(--color-ink-secondary)}.simple-research>a{display:block;margin-top:.8rem;font-size:.7rem;color:var(--color-accent)}.research-disclosure{min-width:0}.research-disclosure>summary{padding:1rem;border:1px solid var(--color-line);border-radius:.7rem;color:var(--color-accent);font-size:.8rem;background:var(--color-surface);cursor:pointer;margin-bottom:1rem}

.barchart-container { min-width: 0; grid-template-columns: minmax(0, 1fr); }
.strategy-header {
  display: flex;
  min-height: 15rem;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  padding: clamp(1.5rem, 4vw, 3.2rem);
  color: white;
  border-radius: 1.5rem;
  background: #1b1d20;
}
.instrument-line {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: #9da2a7;
  font: 700 0.7rem var(--font-numeric);
  letter-spacing: 0.1em;
}
.strategy-header h2 {
  margin: 0.85rem 0 0.5rem;
  font: 500 clamp(2rem, 5vw, 3.8rem) var(--font-display);
  letter-spacing: -0.05em;
}
.strategy-header p {
  max-width: 36rem;
  margin: 0;
  color: #b6b9bc;
  font-size: 0.82rem;
  line-height: 1.7;
}
.score {
  min-width: 8.5rem;
  text-align: center;
}
.score strong {
  display: block;
  font: 500 4.5rem var(--font-display);
  letter-spacing: -0.07em;
}
.score span {
  color: #92979c;
  font-size: 0.67rem;
  letter-spacing: 0.1em;
}
.strategy-metrics {
  grid-template-columns: repeat(4, 1fr);
}

/* 视图模式切换栏 */
.view-switch-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 1.25rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.switch-title h3 {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 650;
  color: var(--color-ink);
}

.switch-subtitle {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.68rem;
  color: var(--color-ink-tertiary);
}

.switch-tabs {
  display: inline-flex;
  padding: 3px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  background: #f1efe9;
}

.switch-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.85rem;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--color-ink-secondary);
  font-size: 0.73rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast) ease;
}

.switch-btn:hover {
  color: var(--color-ink);
}

.switch-btn.active {
  background: white;
  color: var(--color-accent);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.barchart-container {
  display: grid;
  gap: var(--space-5);
}

.guardrail-grid {
  margin-top: 0.25rem;
}

.side-stack {
  display: grid;
  align-content: start;
  gap: var(--space-5);
}
.boundary {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.8rem 0;
  color: var(--color-positive);
  border-bottom: 1px solid var(--color-line);
  font-size: 0.73rem;
}
.boundary--danger {
  color: var(--color-negative);
}
.disclaimer {
  margin: 0.9rem 0 0;
  color: var(--color-ink-tertiary);
  font-size: 0.66rem;
  line-height: 1.55;
}
.events {
  display: grid;
  gap: 0.8rem;
  padding: 0;
  margin: 0;
  list-style: none;
}
.events li {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  color: var(--color-ink-secondary);
  font-size: 0.72rem;
  line-height: 1.5;
}
.events svg {
  flex: none;
  color: var(--color-accent);
}
.audit {
  display: grid;
  gap: 0.8rem;
  margin: 0;
}
.audit div {
  display: grid;
  gap: 0.2rem;
}
.audit dt {
  color: var(--color-ink-tertiary);
  font-size: 0.62rem;
  text-transform: uppercase;
}
.audit dd {
  overflow-wrap: anywhere;
  margin: 0;
  font: 0.67rem var(--font-numeric);
}
.culture-panel {
  margin-top: var(--space-6);
}
.culture-notice {
  max-width: 58rem;
  margin: 0 0 1rem;
  padding: 0.75rem 0.9rem;
  color: #755b30;
  border: 1px solid #e6d8bc;
  border-radius: 0.75rem;
  background: #fffaf0;
  font-size: 0.7rem;
  line-height: 1.55;
}
@media (max-width: 700px) {
  .strategy-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .score {
    text-align: left;
  }
  .strategy-metrics {
    grid-template-columns: 1fr 1fr;
  }
  .view-switch-bar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

<script setup lang="ts">
import { Activity, BrainCircuit, Database, Network, RefreshCw, Server } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import DataPanel from '../components/DataPanel.vue'
import { useDashboard } from '../composables/useDashboard'
import { api } from '../services/api'
import { formatTime } from '../utils/format'

const { store, state, quote, prediction, lastLoadedAt } = useDashboard()
const gateway = ref<'checking' | 'up' | 'down'>('checking')
const checkedAt = ref('')

async function checkHealth() {
  gateway.value = 'checking'
  try {
    const health = await api.health()
    gateway.value = health.status === 'UP' ? 'up' : 'down'
  } catch { gateway.value = 'down' }
  checkedAt.value = new Date().toISOString()
}
onMounted(() => void checkHealth())

const services = computed(() => [
  { name: 'API 网关', detail: '路由、限流与追踪', icon: Network, status: gateway.value },
  { name: '行情服务', detail: quote.value ? `最近数据 ${formatTime(quote.value.dataTimestamp)}` : '尚无成功响应', icon: Database, status: quote.value ? 'up' : 'down' },
  { name: '策略服务', detail: prediction.value ? `模型 ${prediction.value.modelVersion}` : '尚无成功响应', icon: BrainCircuit, status: prediction.value ? 'up' : 'down' },
  { name: '算法服务', detail: prediction.value ? `Trace ${prediction.value.traceId.slice(0, 10)}` : '由策略服务探测', icon: Server, status: prediction.value ? 'up' : 'down' },
])
</script>

<template>
  <div class="page-stack">
    <div class="section-intro">
      <p>系统页只呈现能够被当前浏览器实际观测到的状态。下游基础设施的深层健康信息应由 Prometheus 与告警平台读取。</p>
      <button class="ghost-button" type="button" @click="checkHealth"><RefreshCw :size="15" />重新探测</button>
    </div>


    <div class="system-summary" :class="`system-summary--${gateway}`">
      <Activity :size="22" aria-hidden="true" />
      <div><strong>{{ gateway === 'up' ? '网关响应正常' : gateway === 'checking' ? '正在探测网关' : '网关当前不可达' }}</strong><span>最近探测 {{ checkedAt ? formatTime(checkedAt) : '尚未完成' }}</span></div>
    </div>

    <div class="service-grid">
      <DataPanel v-for="service in services" :key="service.name" class="service-card">
        <div class="service-card__head"><component :is="service.icon" :size="20" /><span class="status-dot" :class="`status-dot--${service.status}`" /></div>
        <h2>{{ service.name }}</h2>
        <p>{{ service.detail }}</p>
        <span class="status-label">{{ service.status === 'up' ? '可用' : service.status === 'checking' ? '检查中' : '未确认' }}</span>
      </DataPanel>
    </div>

    <div class="page-grid">
      <DataPanel class="span-7" title="降级策略" eyebrow="Reliability posture">
        <div class="policy-list"><div><span>算法超时</span><strong>熔断 + 最近成功结果</strong></div><div><span>Redis 不可用</span><strong>回源 PostgreSQL</strong></div><div><span>实时行情中断</span><strong>标记 DEGRADED，不伪装实时</strong></div><div><span>请求拥塞</span><strong>合并同合约并发计算</strong></div></div>
      </DataPanel>
      <DataPanel class="span-5" title="当前会话" eyebrow="Browser observation">
        <dl class="session"><div><dt>业务加载状态</dt><dd>{{ state }}</dd></div><div><dt>数据模式</dt><dd>真实行情服务</dd></div><div><dt>最近业务加载</dt><dd>{{ lastLoadedAt ? formatTime(lastLoadedAt) : '尚未加载' }}</dd></div><div><dt>前端版本</dt><dd>2.0.0</dd></div></dl>
        <button class="primary-button reload" type="button" @click="store.load()">重新加载业务数据</button>
      </DataPanel>
    </div>
  </div>
</template>

<style scoped>
.system-summary { display: flex; align-items: center; gap: 1rem; padding: 1.25rem 1.4rem; color: var(--color-warning); border: 1px solid #ded1ad; border-radius: var(--radius-lg); background: var(--color-warning-soft); }
.system-summary--up { color: var(--color-positive); border-color: #bcd3c5; background: var(--color-positive-soft); }
.system-summary--down { color: var(--color-negative); border-color: #ddc0bd; background: var(--color-negative-soft); }
.system-summary div { display: grid; gap: .2rem; }.system-summary strong { font-size: .84rem; }.system-summary span { font-size: .68rem; opacity: .78; }
.service-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-4); }
.service-card__head { display: flex; align-items: center; justify-content: space-between; color: var(--color-accent); }
.service-card h2 { margin: 1.2rem 0 .35rem; font: 500 1.25rem var(--font-display); }.service-card p { min-height: 2.2rem; margin: 0 0 .9rem; color: var(--color-ink-tertiary); font-size: .66rem; line-height: 1.5; }
.status-dot { width: .55rem; height: .55rem; border-radius: 50%; background: var(--color-warning); box-shadow: 0 0 0 4px var(--color-warning-soft); }.status-dot--up { background: var(--color-positive); box-shadow: 0 0 0 4px var(--color-positive-soft); }.status-dot--down { background: var(--color-negative); box-shadow: 0 0 0 4px var(--color-negative-soft); }
.status-label { color: var(--color-ink-secondary); font-size: .65rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.policy-list { display: grid; }.policy-list div { display: flex; justify-content: space-between; gap: 2rem; padding: .9rem 0; border-bottom: 1px solid var(--color-line); font-size: .73rem; }.policy-list div:last-child { border: 0; }.policy-list span { color: var(--color-ink-secondary); }.policy-list strong { text-align: right; }
.session { display: grid; gap: .8rem; margin: 0; }.session div { display: flex; justify-content: space-between; gap: 1rem; }.session dt { color: var(--color-ink-tertiary); font-size: .68rem; }.session dd { margin: 0; font: .68rem var(--font-numeric); text-align: right; }.reload { width: 100%; margin-top: 1.2rem; }
@media (max-width: 1050px) { .service-grid { grid-template-columns: 1fr 1fr; } } @media (max-width: 560px) { .service-grid { grid-template-columns: 1fr; } }
</style>

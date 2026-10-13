<script setup lang="ts">
import { ArrowUpRight } from 'lucide-vue-next'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import FreshnessBadge from '../components/FreshnessBadge.vue'

const route = useRoute()
const title = computed(() => String(route.meta.title ?? '总览'))
</script>

<template>
  <section class="placeholder" aria-labelledby="placeholder-title">
    <div class="placeholder__copy">
      <FreshnessBadge status="CACHED" timestamp="等待业务数据接入" />
      <p class="placeholder__index">0{{ route.path === '/overview' ? 1 : route.path === '/market' ? 2 : route.path === '/strategy' ? 3 : 4 }}</p>
      <h2 id="placeholder-title">{{ title }}工作区</h2>
      <p>
        应用框架与可信数据状态已经就绪。下一阶段将在这里接入真实行情、十一维策略结果和系统可观测数据。
      </p>
    </div>
    <div class="placeholder__note">
      <span>模块状态</span>
      <strong>Foundation ready</strong>
      <ArrowUpRight :size="19" aria-hidden="true" />
    </div>
  </section>
</template>

<style scoped>
.placeholder {
  position: relative;
  display: grid;
  min-height: 32rem;
  grid-template-columns: minmax(0, 1fr) minmax(14rem, 20rem);
  gap: var(--space-8);
  overflow: hidden;
  padding: clamp(2rem, 6vw, 5rem);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-raised);
}

.placeholder::after {
  position: absolute;
  right: -5rem;
  bottom: -9rem;
  width: 20rem;
  height: 20rem;
  border: 1px solid var(--color-line);
  border-radius: 50%;
  content: '';
}

.placeholder__copy {
  position: relative;
  z-index: 1;
  align-self: center;
  max-width: 42rem;
}

.placeholder__index {
  margin: var(--space-12) 0 var(--space-3);
  color: var(--color-line-strong);
  font-family: var(--font-numeric);
  font-size: 0.72rem;
  letter-spacing: 0.12em;
}

.placeholder h2 {
  max-width: 10ch;
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(2.7rem, 6vw, 5.4rem);
  font-weight: 500;
  letter-spacing: -0.055em;
  line-height: 0.96;
}

.placeholder__copy > p:last-child {
  max-width: 35rem;
  margin: var(--space-6) 0 0;
  color: var(--color-ink-secondary);
  font-size: 0.93rem;
  line-height: 1.85;
}

.placeholder__note {
  position: relative;
  z-index: 1;
  display: grid;
  align-self: end;
  grid-template-columns: 1fr auto;
  gap: var(--space-1) var(--space-3);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-line-strong);
}

.placeholder__note span {
  grid-column: 1 / -1;
  color: var(--color-ink-tertiary);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.placeholder__note strong {
  font-family: var(--font-numeric);
  font-size: 0.78rem;
  font-weight: 500;
}

@media (max-width: 920px) {
  .placeholder {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .placeholder {
    min-height: 29rem;
    padding: var(--space-8) var(--space-6);
  }
}
</style>

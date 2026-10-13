<script setup lang="ts">
import { CircleCheck, Clock3, TriangleAlert } from 'lucide-vue-next'
import { computed } from 'vue'

export type FreshnessStatus = 'FRESH' | 'CACHED' | 'DEGRADED'

const props = defineProps<{
  status: FreshnessStatus
  timestamp?: string
}>()

const content = computed(() => ({
  FRESH: { label: '实时', icon: CircleCheck },
  CACHED: { label: '缓存', icon: Clock3 },
  DEGRADED: { label: '降级', icon: TriangleAlert },
})[props.status])
</script>

<template>
  <span class="freshness" :class="`freshness--${status.toLowerCase()}`" :title="timestamp">
    <component :is="content.icon" :size="13" :stroke-width="2" aria-hidden="true" />
    <span>{{ content.label }}</span>
    <span v-if="timestamp" class="sr-only">，数据时间 {{ timestamp }}</span>
  </span>
</template>

<style scoped>
.freshness {
  display: inline-flex;
  align-items: center;
  gap: 0.34rem;
  min-height: 1.6rem;
  padding: 0.15rem 0.55rem;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  font-size: 0.72rem;
  font-weight: 650;
  letter-spacing: 0.025em;
}

.freshness--fresh {
  color: var(--color-positive);
  background: var(--color-positive-soft);
  border-color: rgb(36 112 78 / 13%);
}

.freshness--cached {
  color: var(--color-accent);
  background: var(--color-accent-soft);
  border-color: rgb(44 99 133 / 13%);
}

.freshness--degraded {
  color: var(--color-warning);
  background: var(--color-warning-soft);
  border-color: rgb(139 101 29 / 15%);
}
</style>

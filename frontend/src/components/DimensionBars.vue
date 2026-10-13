<script setup lang="ts">
import type { Dimension } from '../services/api'

defineProps<{ dimensions: Dimension[]; limit?: number }>()
</script>

<template>
  <div class="dimensions">
    <article v-for="item in dimensions.slice(0, limit ?? dimensions.length)" :key="item.key" class="dimension">
      <div class="dimension__head"><strong>{{ item.name }}</strong><span>{{ Math.round(item.score) }}</span></div>
      <div class="track" role="meter" :aria-label="`${item.name}评分`" aria-valuemin="-100" aria-valuemax="100" :aria-valuenow="item.score">
        <span :style="{ width: `${Math.max(0, Math.min(100, (item.score + 100) / 2))}%` }" />
      </div>
      <p>{{ item.recommendation }}</p>
    </article>
  </div>
</template>

<style scoped>
.dimensions { display: grid; gap: var(--space-4); }
.dimension__head { display: flex; justify-content: space-between; gap: var(--space-4); font-size: .78rem; }
.dimension__head strong { font-weight: 630; }
.dimension__head span { color: var(--color-accent); font-family: var(--font-numeric); font-size: .72rem; font-weight: 700; }
.track { height: 4px; margin-top: .45rem; overflow: hidden; border-radius: var(--radius-pill); background: #e9e6df; }
.track span { display: block; height: 100%; border-radius: inherit; background: var(--color-accent); }
.dimension p { margin: .42rem 0 0; color: var(--color-ink-tertiary); font-size: .68rem; line-height: 1.45; }
</style>

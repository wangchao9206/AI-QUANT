<script setup lang="ts">
import type { Dimension } from '../services/api'

defineProps<{ dimensions: Dimension[]; limit?: number; reference?: boolean }>()
</script>

<template>
  <div class="dimensions">
    <article v-for="item in dimensions.slice(0, limit ?? dimensions.length)" :key="item.key" class="dimension" :class="{ 'dimension--reference': reference }">
      <div class="dimension__head">
        <strong>{{ item.name }}</strong>
        <span v-if="item.score !== null">{{ Math.round(item.score) }}</span>
        <em v-else>{{ item.dataStatus === 'REFERENCE' ? '参考' : '不可用' }}</em>
      </div>
      <div v-if="item.score !== null" class="track" role="meter" :aria-label="`${item.name}评分`" aria-valuemin="-100" aria-valuemax="100" :aria-valuenow="item.score">
        <span :style="{ width: `${Math.max(0, Math.min(100, (item.score + 100) / 2))}%` }" />
      </div>
      <p class="summary">{{ item.summary }}</p>
      <dl v-if="Object.keys(item.keyMetrics).length" class="metrics">
        <div v-for="(value, key) in item.keyMetrics" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></div>
      </dl>
      <div class="dimension__meta">
        <span>样本 {{ item.sampleSize }}</span><span v-if="item.includedInScore">权重 {{ Math.round(item.weight * 100) }}%</span>
        <a v-if="item.sourceUrl" :href="item.sourceUrl" target="_blank" rel="noopener noreferrer">{{ item.sourceName }}</a>
        <span v-else>{{ item.sourceName }}</span>
      </div>
      <p class="recommendation">{{ item.recommendation }}</p>
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
.dimension { padding-bottom: .3rem; }
.dimension--reference { padding: .9rem; border: 1px solid var(--color-line); border-radius: .9rem; background: #faf9f6; }
.dimension__head em { color: #8a6a33; font-size: .62rem; font-style: normal; letter-spacing: .08em; }
.dimension p { margin: .42rem 0 0; color: var(--color-ink-tertiary); font-size: .68rem; line-height: 1.5; }
.dimension .summary { color: var(--color-ink-secondary); }
.metrics { display: flex; flex-wrap: wrap; gap: .35rem .8rem; margin: .65rem 0 0; }
.metrics div { display: flex; gap: .3rem; font-size: .61rem; }
.metrics dt { color: var(--color-ink-tertiary); }
.metrics dd { margin: 0; color: var(--color-ink-secondary); font-family: var(--font-numeric); }
.dimension__meta { display: flex; flex-wrap: wrap; gap: .45rem .8rem; margin-top: .65rem; color: var(--color-ink-tertiary); font-size: .58rem; }
.dimension__meta a { color: var(--color-accent); text-decoration: none; }
.dimension .recommendation { padding-left: .55rem; border-left: 2px solid var(--color-line); }
</style>

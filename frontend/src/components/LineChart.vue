<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ values: number[]; label: string; height?: number }>(), { height: 190 })
const width = 720
const padding = 10
const points = computed(() => {
  if (!props.values.length) return ''
  const min = Math.min(...props.values)
  const max = Math.max(...props.values)
  const range = max - min || 1
  return props.values.map((value, index) => {
    const x = padding + index * ((width - padding * 2) / Math.max(props.values.length - 1, 1))
    const y = padding + (max - value) * ((props.height - padding * 2) / range)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})
</script>

<template>
  <svg class="chart" :viewBox="`0 0 ${width} ${height}`" role="img" :aria-label="label" preserveAspectRatio="none">
    <title>{{ label }}</title>
    <line v-for="n in 4" :key="n" x1="0" :y1="n * height / 5" :x2="width" :y2="n * height / 5" class="grid" />
    <polyline v-if="points" :points="points" class="line" />
  </svg>
</template>

<style scoped>
.chart { display: block; width: 100%; min-height: 8rem; overflow: visible; }
.grid { stroke: var(--color-line); stroke-width: 1; vector-effect: non-scaling-stroke; }
.line { fill: none; stroke: var(--color-accent); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
</style>

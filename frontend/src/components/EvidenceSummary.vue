<script setup lang="ts">
import { computed } from 'vue'
import type { Prediction } from '../services/api'
import { evidenceSummary } from '../utils/evidence'
const props = defineProps<{prediction: Prediction}>()
const evidence = computed(() => evidenceSummary(props.prediction))
</script>

<template>
  <div class="evidence-summary">
    <div class="evidence-numbers">
      <div><strong>{{ Math.round(evidence.coverage*100) }}<small>%</small></strong><span>实证配置权重覆盖</span></div>
      <div><strong>{{ evidence.available }}<small> / {{ evidence.total }}</small></strong><span>可用实证维度</span></div>
      <div><strong class="uncalibrated">未校准</strong><span>盈利概率 / 预测胜率</span></div>
    </div>
    <div class="coverage-track" role="progressbar" aria-label="实证配置权重覆盖" :aria-valuenow="Math.round(evidence.coverage*100)" aria-valuemin="0" aria-valuemax="100"><i :style="{width:`${evidence.coverage*100}%`}" /></div>
    <p v-if="evidence.missing.length">本次缺少：{{ evidence.missing.join('、') }}。</p>
    <p>多项维度共用量价输入；覆盖率、方向一致度与指标内部评分均不代表胜率。</p>
    <details><summary>查看全维参考权重</summary><p>现有全维评分中文化参考实际占 {{ (evidence.culturalShare*100).toFixed(1) }}%；缺失实证数据会改变归一化比例。交易计划默认采用实证模式，可单独切换文化对照。</p><p>指标内部置信评分 {{ Math.round(prediction.confidence*100) }}%，尚无对应的胜率校准。</p></details>
  </div>
</template>

<style scoped>
.evidence-numbers{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}.evidence-numbers>div{display:grid;gap:.45rem}.evidence-numbers strong{font:500 2rem var(--font-numeric)}.evidence-numbers small{font-size:.8rem;color:var(--color-ink-tertiary)}.evidence-numbers span{font-size:.68rem;color:var(--color-ink-secondary)}.evidence-numbers .uncalibrated{font:600 1.15rem var(--font-sans);padding-top:.55rem}.coverage-track{height:5px;background:var(--color-line);border-radius:5px;margin:1.1rem 0;overflow:hidden}.coverage-track i{display:block;height:100%;background:var(--color-accent)}p,summary{font-size:.72rem;line-height:1.7;color:var(--color-ink-secondary)}summary{cursor:pointer;color:var(--color-accent)}
</style>

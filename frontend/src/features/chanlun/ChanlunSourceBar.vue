<script setup lang="ts">
import type {Dataset,Analysis} from './api'
import {instrumentLabel} from '../../utils/instrumentNames'
defineProps<{analysis?:Analysis|null;dataset?:Dataset|null}>()
</script>
<template><section class="source" aria-label="缠论历史来源"><strong>冻结历史研究 · {{analysis?.dataset.displayName??dataset?.displayName??'尚未载入数据集'}}</strong><template v-if="analysis||dataset"><p>数据集 {{(analysis?.dataset??dataset)!.id}} · {{instrumentLabel((analysis?.dataset??dataset)!.symbol)}} · {{(analysis?.dataset??dataset)!.frequency}}</p><p v-if="analysis">当前分析 {{analysis.runId}} · 观察截止 {{analysis.observedAsOfDate}} · 记录于 {{analysis.recordedAt}}</p><p v-else>输入窗口 {{dataset?.start}} — {{dataset?.end}}；尚未创建本次分析。</p><details><summary>来源版本与价格口径</summary><p>数据摘要 {{analysis?.datasetHash??dataset?.sha256}}</p><p>{{analysis?.priceBasis??dataset?.priceBasis}}</p><p v-if="analysis">引擎 {{analysis.engineId}} · {{analysis.engineVersion}} · 规则 {{analysis.profileHash}}</p></details></template><p>这是独立历史数据集，不随当前看盘合约换月；图上端点、首次观察与实际记录时间分别保留，不作为当前行情或计划执行资格。</p></section></template>
<style scoped>.source{padding:1rem;margin:1rem 0;border:1px solid #d7d8cc;border-left:3px solid #8b7851;border-radius:.5rem;background:#f6f4ec;min-width:0;font-size:.78rem;line-height:1.8}.source p{margin:.4rem 0;color:#657066;overflow-wrap:anywhere}.source details{overflow-wrap:anywhere}.source summary{cursor:pointer}</style>

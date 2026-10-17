<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { api } from '../services/api'
import type { ValidationSnapshot } from '../types/research'
import { formatPct,formatTime } from '../utils/format'
const snapshot=ref<ValidationSnapshot|null>(null);const error=ref('');const selected=ref('HOLISTIC_14D')
const strategyNames:Record<string,string>={HOLISTIC_14D:'全维融合',MOMENTUM_BREAKOUT:'动量突破',BOLLINGER_REVERSAL:'布林回归',DUAL_THRUST:'Dual Thrust',ADAPTIVE_CTA:'自适应 CTA',BUY_AND_HOLD:'持有基准',HOLISTIC_NO_CULTURE:'移除文化因素对照'}
const options=computed(()=>[...new Set(snapshot.value?.strategies.map(s=>s.strategy)??[])])
const rows=computed(()=>snapshot.value?.strategies.filter(s=>s.strategy===selected.value)??[])
onMounted(async()=>{try{snapshot.value=await api.validation()}catch(e){error.value=e instanceof Error?e.message:'验证记录暂不可用'}})
</script>
<template>
  <section class="validation-panel">
    <header><div><p>固定参数 / 可追溯历史复核</p><h2>先看策略在哪些条件下失效</h2></div><span class="validation-tag">样本外与盈利能力：未验证</span></header>
    <p v-if="error" role="alert" class="validation-note">{{ error }}。不影响自定义回测。</p>
    <p v-else-if="!snapshot" class="validation-note">正在读取验证记录…</p>
    <template v-else>
      <p v-if="snapshot.status!=='RETROSPECTIVE_CHECKED'" class="validation-note">{{ snapshot.status==='NEEDS_RECHECK'?'报告来自其他版本，当前模型需要重新复核。':snapshot.message??'尚无当前版本验证记录' }}</p>
      <div v-if="snapshot.period" class="validation-facts"><span>{{ snapshot.period.start }} — {{ snapshot.period.end }}</span><span>{{ snapshot.assets }} 个品种 / {{ snapshot.cases }} 组历史情景</span><span>报告模型 {{ snapshot.modelVersion }}</span><span>{{ formatTime(snapshot.generatedAt) }}</span></div>
      <p class="validation-note">执行一致性检查与策略有效性分开验收。下表是固定参数的历史诊断，不能作为当前自定义参数的样本外结果。</p>
      <div v-if="snapshot.executionChecks" class="execution-checks"><span>开仓日止损遗漏 <b>{{ snapshot.executionChecks.missedStops }}</b></span><span>不符合最小价位的成交 <b>{{ snapshot.executionChecks.offTickFills }}</b></span><span>资金舍入最大差额 <b>¥{{ snapshot.executionChecks.cashDifference }}</b></span></div>
      <template v-if="options.length"><label class="strategy-select">查看固定策略<select v-model="selected"><option v-for="option in options" :key="option" :value="option">{{ strategyNames[option]??option }}</option></select></label><div class="validation-table"><table><caption class="sr-only">固定参数历史成本压力对照</caption><thead><tr><th>品种</th><th>原成本区间收益</th><th>双倍成本收益</th><th>原成本最大回撤</th><th>平仓笔数</th></tr></thead><tbody><tr v-for="row in rows" :key="row.symbol+row.strategy"><td>{{ row.symbol }}</td><td>{{ formatPct(row.baseReturn) }}</td><td>{{ row.stressedReturn==null?'未运行':formatPct(row.stressedReturn) }}</td><td>{{ row.maxDrawdown.toFixed(2) }}%</td><td>{{ row.trades }}</td></tr></tbody></table></div></template>
      <details><summary>数据、成本与证据限制</summary><ul><li v-for="limit in snapshot.limits" :key="limit">{{ limit }}</li></ul></details>
    </template>
  </section>
</template>
<style scoped>
.validation-panel{padding:1.4rem 1.6rem;border:1px solid var(--color-line);border-radius:1rem;background:var(--color-surface);margin:1.25rem 0}.validation-panel header{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}.validation-panel header p{font-size:.65rem;color:var(--color-accent);margin:0 0 .5rem}.validation-panel h2{font-size:1.05rem;margin:0}.validation-tag{padding:.45rem .6rem;background:var(--color-warning-soft);color:var(--color-warning);border-radius:.5rem;font-size:.67rem}.validation-facts{display:flex;flex-wrap:wrap;gap:.7rem 1.5rem;margin:1.25rem 0;font:500 .7rem var(--font-numeric);color:var(--color-ink-secondary)}.validation-note{font-size:.72rem;line-height:1.8;color:var(--color-ink-secondary)}.execution-checks{display:flex;gap:.75rem 1.5rem;flex-wrap:wrap;font-size:.69rem;padding:.85rem 0;border-block:1px solid var(--color-line)}.execution-checks b{margin-left:.35rem;font-family:var(--font-numeric)}.strategy-select{display:flex;align-items:center;gap:.8rem;font-size:.73rem;margin:1rem 0}.strategy-select select{border:1px solid var(--color-line);border-radius:.4rem;padding:.5rem;background:#fff}.validation-table{overflow:auto}.validation-table table{width:100%;border-collapse:collapse;font-size:.72rem}.validation-table th{text-align:right;color:var(--color-ink-secondary);font-weight:500}.validation-table th:first-child,.validation-table td:first-child{text-align:left}.validation-table th,.validation-table td{padding:.8rem;border-bottom:1px solid var(--color-line);white-space:nowrap}.validation-table td{text-align:right;font-family:var(--font-numeric)}details{margin-top:1rem;font-size:.7rem;line-height:1.8;color:var(--color-ink-secondary)}summary{cursor:pointer;color:var(--color-accent)}
</style>

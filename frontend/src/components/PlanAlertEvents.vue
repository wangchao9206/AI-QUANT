<script setup lang="ts">
import {RouterLink} from 'vue-router'
import type {PlanAlertEvent} from '../services/planAlerts'
import {formatTime,formatNumber} from '../utils/format'
import {instrumentLabel} from '../utils/instrumentNames'
defineProps<{items:PlanAlertEvent[];canWrite:boolean;busy:boolean}>()
defineEmits<{ack:[string]}>()
const labels={ENTRY:'入场参考穿越',STOP:'保护参考穿越',TARGET:'目标参考穿越',EXPIRED:'计划到期'}
function number(event:PlanAlertEvent,key:string,field:string){const row=event.evidence[key];const v=row&&typeof row==='object'?(row as Record<string,unknown>)[field]:null;return typeof v==='number'&&Number.isFinite(v)?formatNumber(v,4):'—'}
</script>
<template><div class="plan-alert-events"><article v-for="event in items" :key="event.id"><header><strong>{{labels[event.kind]}} · v{{event.version}}</strong><span>{{instrumentLabel(event.symbol)}}</span></header><p>观测 / 到期 {{formatTime(event.observedAt)}} · 记录 {{formatTime(event.createdAt)}}</p><p v-if="event.kind!=='EXPIRED'">采样价 {{number(event,'previousObservation','price')}} → {{number(event,'currentObservation','price')}} · 计划参考 {{number(event,'plan',({ENTRY:'entry',STOP:'stop',TARGET:'target',EXPIRED:'validUntil'})[event.kind])}}</p><RouterLink :to="{path:'/paper/decisions/'+event.caseId,query:{plan:event.planId}}">还原该计划版本 ↗</RouterLink> <button v-if="canWrite&&!event.acknowledgedAt" :disabled="busy" @click="$emit('ack',event.id)">标记已读</button><span v-else-if="event.acknowledgedAt">已读</span><details><summary>触发时的计划、行情与依据</summary><pre>{{JSON.stringify(event.evidence,null,2)}}</pre></details></article></div></template>
<style scoped>
article{padding:1rem 0;border-bottom:1px solid var(--color-line);overflow-wrap:anywhere}header{display:flex;flex-wrap:wrap;gap:.6rem;justify-content:space-between}article,p,summary,a,button{font-size:.73rem;line-height:1.8}p,header span{color:var(--color-ink-secondary)}a{color:var(--color-accent)}button{border:1px solid var(--color-line);border-radius:.4rem;background:var(--color-accent-soft);color:var(--color-accent);padding:.35rem .6rem;cursor:pointer}button:disabled{opacity:.5}details{margin-top:.6rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:22rem;overflow:auto;font-size:.68rem}
</style>

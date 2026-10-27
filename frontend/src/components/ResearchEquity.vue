<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import type {CurvePoint} from '../services/researchLibrary'
const props=defineProps<{curve:CurvePoint[];initial:number}>()
const selected=ref(0)
watch(()=>props.curve,()=>selected.value=Math.max(0,props.curve.length-1),{immediate:true})
const bounds=computed(()=>{
  const values=props.curve.map(p=>p.equity),low=Math.min(props.initial,...values),high=Math.max(props.initial,...values),span=Math.max(1,high-low)
  return {low:low-span*.08,high:high+span*.08}
})
const y=(value:number)=>194-(value-bounds.value.low)/(bounds.value.high-bounds.value.low)*178
const x=(i:number)=>34+i/Math.max(1,props.curve.length-1)*690
const path=computed(()=>props.curve.map((p,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(p.equity).toFixed(2)}`).join(' '))
const point=computed(()=>props.curve[selected.value])
function hover(event:PointerEvent){const rect=(event.currentTarget as SVGElement).getBoundingClientRect();selected.value=Math.max(0,Math.min(props.curve.length-1,Math.round(((event.clientX-rect.left)/rect.width*750-34)/690*(props.curve.length-1))))}
const cash=(v:number)=>v.toLocaleString('zh-CN',{maximumFractionDigits:2})
</script>
<template>
  <div class="equity-chart" v-if="curve.length">
    <div class="chart-value"><span>{{point?.date}}</span><strong>权益 ¥ {{cash(point?.equity??initial)}}</strong></div>
    <svg viewBox="0 0 750 220" role="img" aria-label="所选场景每日账户权益曲线" @pointermove="hover">
      <line x1="34" x2="724" :y1="y(initial)" :y2="y(initial)" stroke="currentColor" stroke-dasharray="4 5" opacity=".2"/>
      <path :d="path" fill="none" stroke="var(--color-accent)" stroke-width="2" vector-effect="non-scaling-stroke"/>
      <line :x1="x(selected)" :x2="x(selected)" y1="14" y2="200" stroke="currentColor" opacity=".2"/>
      <circle v-if="point" :cx="x(selected)" :cy="y(point.equity)" r="4" fill="var(--color-accent)"/>
      <text x="34" y="216">{{curve[0]?.date}}</text><text x="724" y="216" text-anchor="end">{{curve.at(-1)?.date}}</text>
    </svg>
    <label>查看日期 <input type="range" min="0" :max="curve.length-1" v-model.number="selected" aria-label="查看每日权益" /></label>
  </div>
  <p v-else class="empty">尚无冻结后新日线记录。</p>
</template>
<style scoped>
.equity-chart{padding:.9rem 0}.chart-value{display:flex;justify-content:space-between;gap:.6rem;font:.74rem var(--font-numeric)}.chart-value span{color:var(--color-ink-tertiary)}svg{display:block;width:100%;height:auto;overflow:visible}text{font-size:11px;fill:var(--color-ink-tertiary)}label{display:flex;align-items:center;gap:1rem;font-size:.67rem;color:var(--color-ink-tertiary)}input{flex:1;min-width:0;accent-color:var(--color-accent)}.empty{font-size:.8rem;color:var(--color-ink-tertiary)}
</style>

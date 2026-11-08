<script setup lang="ts">
import {RouterLink,useRoute,type LocationQueryRaw} from 'vue-router'
import {chanObject,deliverySymbol,marketOrigin} from '../../utils/chanlunContext'
const props=withDefaults(defineProps<{active:string;context?:LocationQueryRaw;sessionId?:string}>(),{context:()=>({})})
const route=useRoute()
const items=[['workbench','工作台'],['radar','信号雷达'],['multiframe','多周期观察'],['compare','引擎对照'],['replay','逐根训练'],['lab','策略实验'],['academy','原典课堂'],['judgments','判断档案'],['reviews','复盘档案'],['settings','规则与引擎']]
function query(id:string):LocationQueryRaw {
 if(id===props.active)return route.query
 if(id==='replay')return props.sessionId?{session:props.sessionId}:{}
 if(id==='multiframe'){const symbol=deliverySymbol(route.query.symbol);return symbol?marketOrigin(route.query,symbol):{}}
 if(['workbench','academy','judgments','settings','compare'].includes(id)){
  const run=chanObject(props.context.run),structure=chanObject(props.context.structure)
  return run?{run,...id!=='compare'&&structure?{structure}:{}}:{}
 }
 return {}
}
</script>
<template><nav class="chan-navigation" aria-label="缠论中心导航"><RouterLink v-for="[id,label] in items" :key="id" :to="{path:`/chanlun/${id}`,query:query(id)}" :aria-current="props.active===id?'page':undefined">{{label}}</RouterLink></nav></template>
<style scoped>
.chan-navigation{display:flex;gap:.5rem;flex-wrap:wrap;border-bottom:1px solid #dedfd5;padding-bottom:.9rem;margin-bottom:1.2rem}.chan-navigation a{padding:.55rem .8rem;color:#657066;text-decoration:none;font-size:.8rem;border-radius:.35rem}.chan-navigation a[aria-current=page]{color:#293b31;background:#e6ede1;font-weight:600}.chan-navigation a:focus-visible{outline:2px solid #9e784b;outline-offset:3px}@media(max-width:600px){.chan-navigation{gap:.1rem}.chan-navigation a{padding:.5rem;font-size:.75rem}}@media(pointer:coarse){.chan-navigation a{min-height:44px;display:inline-flex;align-items:center}}
</style>

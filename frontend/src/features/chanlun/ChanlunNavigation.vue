<script setup lang="ts">
import {RouterLink,type LocationQueryRaw} from 'vue-router'
const props=withDefaults(defineProps<{active:string;context?:LocationQueryRaw;sessionId?:string}>(),{context:()=>({})})
const items=[['workbench','工作台'],['radar','信号雷达'],['multiframe','多周期观察'],['compare','引擎对照'],['replay','逐根训练'],['lab','策略实验'],['academy','原典课堂'],['judgments','判断档案'],['reviews','复盘档案'],['settings','规则与引擎']]
</script>
<template><nav class="chan-navigation" aria-label="缠论中心导航"><RouterLink v-for="[id,label] in items" :key="id" :to="{path:`/chanlun/${id}`,query:id==='replay'?(props.sessionId?{session:props.sessionId}:{}):props.context}" :aria-current="props.active===id?'page':undefined">{{label}}</RouterLink></nav></template>
<style scoped>
.chan-navigation{display:flex;gap:.5rem;flex-wrap:wrap;border-bottom:1px solid #dedfd5;padding-bottom:.9rem;margin-bottom:1.2rem}.chan-navigation a{padding:.55rem .8rem;color:#657066;text-decoration:none;font-size:.8rem;border-radius:.35rem}.chan-navigation a[aria-current=page]{color:#293b31;background:#e6ede1;font-weight:600}.chan-navigation a:focus-visible{outline:2px solid #9e784b;outline-offset:3px}@media(max-width:600px){.chan-navigation{gap:.1rem}.chan-navigation a{padding:.5rem;font-size:.75rem}}@media(pointer:coarse){.chan-navigation a{min-height:44px;display:inline-flex;align-items:center}}
</style>

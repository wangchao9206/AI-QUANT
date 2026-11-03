<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {RouterLink} from 'vue-router'
import ChanlunNavigation from './ChanlunNavigation.vue'
import {monitorApi,type MonitorReview} from './monitor'
const entries=ref<MonitorReview[]>([]),error=ref(''),loading=ref(true)
async function load(){loading.value=true;error.value='';try{entries.value=await monitorApi.reviews()}catch(e){error.value=e instanceof Error?e.message:'复盘读取失败'}finally{loading.value=false}}
onMounted(load)
</script>
<template><main class="reviews"><ChanlunNavigation active="reviews"/><h1>监控复盘档案</h1><p>复盘绑定当时行情前缀、单个候选快照和服务器实际发现时间。已保存内容保留，新观点请另存一条。</p><RouterLink to="/chanlun/judgments">查看工作台与逐根训练判断</RouterLink><button @click="load" :disabled="loading">刷新档案</button><p v-if="loading" role="status">正在读取复盘…</p><p v-if="error" role="alert">{{error}}</p><p v-if="!loading&&!entries.length">尚无监控复盘；从雷达事件打开当时证据后保存。</p><article v-for="e in entries" :key="e.id"><h2>{{e.evidence.analysis.symbol}} · {{e.evidence.event.signalType}} · {{e.outlook==='WAIT'?'等待':e.outlook==='UP'?'看多':'看空'}}</h2><p class="meta">{{e.evidence.analysis.frequency}} · 实际发现 {{e.evidence.detectedAt}} · 保存 {{e.createdAt}}</p><p class="content">{{e.content}}</p><p v-if="e.lessonNumber">参考原文第 {{e.lessonNumber}} 课</p><RouterLink :to="{path:'/chanlun/radar',query:{monitor:e.monitorId,event:String(e.eventSeq)}}">恢复当时行情与候选</RouterLink><details><summary>冻结规则摘要</summary><code>{{e.evidence.analysis.profileHash}}</code></details></article></main></template>
<style scoped>.reviews{max-width:1100px;margin:auto;color:#293b31}h1{font-size:1.7rem}h2{font-size:1rem}p{font-size:.85rem;line-height:1.8}.reviews>a,button{font-size:.8rem;margin-right:1rem}button{padding:.5rem;border:1px solid #c6cdbf;background:#fff;border-radius:.3rem;color:inherit}article{margin:1rem 0;padding:1rem;border:1px solid #dedfd5;border-radius:.4rem}.content{white-space:pre-wrap}.meta{color:#657066;font-size:.75rem}code{overflow-wrap:anywhere}summary{font-size:.8rem;cursor:pointer}a:focus-visible,button:focus-visible{outline:2px solid #9e784b;outline-offset:3px}</style>

<script setup lang="ts">
import {ref,watch,onUnmounted,computed} from 'vue'
import {RouterLink} from 'vue-router'
import {authState} from '../services/auth'
import {decisionsApi,type DecisionMonitor,type DecisionCase} from '../services/decisions'
import {monitoringApi,type MonitorJob} from '../services/monitoring'
import {formatTime} from '../utils/format'
import Pagination from './Pagination.vue'
const props=defineProps<{caseId:string;planId:string;symbol:string;links:DecisionMonitor[];editable:boolean}>()
const emit=defineEmits<{saved:[DecisionCase]}>()
const jobs=ref<MonitorJob[]>([]),page=ref(1),total=ref(0),opened=ref(false),busy=ref(false),error=ref('')
const statuses=ref<Record<string,string>>({})
const context=computed(()=>JSON.stringify([props.caseId,props.planId,props.symbol,authState.user?.id,authState.user?.tenantId,authState.user?.permissions]))
let generation=0
watch(context,()=>{++generation;jobs.value=[];opened.value=false;error.value='';statuses.value={};busy.value=false;page.value=1})
onUnmounted(()=>{++generation})
async function list(){const ticket=++generation;busy.value=true;error.value='';opened.value=true;try{const r=await monitoringApi.jobs('FUTURE',props.symbol,page.value);if(ticket===generation){jobs.value=r.items.filter(j=>j.symbol===props.symbol);total.value=r.total}}catch(e){if(ticket===generation)error.value=e instanceof Error?e.message:'任务暂不可用'}finally{if(ticket===generation)busy.value=false}}
watch(page,()=>{if(opened.value)void list()})
async function bind(job:MonitorJob){if(busy.value||!props.editable)return;const ticket=++generation;busy.value=true;error.value='';try{const result=await decisionsApi.bindMonitor(props.caseId,props.planId,job.id);if(ticket===generation)emit('saved',result)}catch(e){if(ticket===generation)error.value=e instanceof Error?e.message:'关联失败，请重试。'}finally{if(ticket===generation)busy.value=false}}
async function status(link:DecisionMonitor){const ticket=generation;try{const r=await monitoringApi.get('FUTURE',link.monitorId);if(ticket===generation)statuses.value[link.monitorId]=r.symbol!==props.symbol?'任务合约已变化，请重新核对':r.version!==link.snapshot.version?'任务已修改或启停，请核对新版本；旧关联快照保留':(r.enabled?'已启用':'已暂停')+' · '+r.status+' · '+formatTime(r.checkedAt)}catch{if(ticket===generation)statuses.value[link.monitorId]='任务不可读取或已归档；原快照保留'}}
</script>
<template>
 <section class="monitor-links"><h3>本版本关联的预警规则</h3><p>关联工作空间已有的同合约任务，保留此刻规则快照。任务仍由原调度器运行；不复制私人计划参数，不自动启停，也不把规则触发当作计划成交。</p>
  <p v-if="error" role="alert">{{error}}</p>
  <article v-for="link in links" :key="link.monitorId"><strong>{{link.snapshot.name}} · 规则 v{{link.snapshot.version}}</strong><p>关联于 {{formatTime(link.createdAt)}} · 当时{{link.snapshot.enabled?'启用':'暂停'}}</p><button :disabled="busy" @click="status(link)">核对当前任务</button> <RouterLink :to="{path:'/live',query:{monitor:link.monitorId,case:caseId,plan:planId,symbol,period:String(link.snapshot.seconds),tab:'monitors'}}">任务与触发记录 ↗</RouterLink><p v-if="statuses[link.monitorId]" role="status">{{statuses[link.monitorId]}}</p><details><summary>关联时的规则快照</summary><pre>{{JSON.stringify(link.snapshot,null,2)}}</pre></details></article>
  <p v-if="!links.length">本计划版本尚未关联规则任务。</p>
  <template v-if="editable"><button :disabled="busy" @click="list">选择已有同合约任务</button><div v-if="opened"><p>按合约搜索；仅显示本页中实际合约完全一致的任务。</p><article v-for="job in jobs" :key="job.id"><span>{{job.name}} · v{{job.version}} · {{job.enabled?'启用':'暂停'}}</span> <button :disabled="busy||links.some(l=>l.monitorId===job.id)" @click="bind(job)">{{links.some(l=>l.monitorId===job.id)?'已关联':'关联到本计划版本'}}</button></article><p v-if="!busy&&!jobs.length">本页没有可关联任务，可到交易台创建规则后再选择。</p><Pagination v-model:page="page" :page-size="20" :total="total" label="规则任务搜索分页"/></div></template>
  <p v-else>仅最新、已保存且未过期的计划可新增关联。</p>
 </section>
</template>
<style scoped>
.monitor-links{border:1px solid var(--color-line);border-radius:.8rem;padding:1rem;background:var(--color-surface);min-width:0}.monitor-links h3{font-size:.95rem}.monitor-links p,.monitor-links article,.monitor-links summary{font-size:.73rem;line-height:1.8}.monitor-links p{color:var(--color-ink-secondary)}.monitor-links article{padding:.8rem 0;border-bottom:1px solid var(--color-line);overflow-wrap:anywhere}.monitor-links button{padding:.5rem .65rem;border:1px solid var(--color-line);background:var(--color-accent-soft);color:var(--color-accent);border-radius:.4rem;cursor:pointer;font-size:.72rem}.monitor-links button:disabled{opacity:.5;cursor:default}.monitor-links a{color:var(--color-accent)}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:16rem;overflow:auto;font-size:.68rem}
</style>

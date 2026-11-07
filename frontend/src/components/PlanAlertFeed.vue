<script setup lang="ts">
import {computed,ref,watch,onUnmounted} from 'vue'
import {authState,hasPermission} from '../services/auth'
import {planAlertsApi,type PlanAlertPage} from '../services/planAlerts'
import PlanAlertEvents from './PlanAlertEvents.vue'
import Pagination from './Pagination.vue'
const page=ref(1),unread=ref(true),data=ref<PlanAlertPage|null>(null),loading=ref(false),error=ref(''),busy=ref(false)
const scope=computed(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId,authState.user?.permissions]))
const canRead=computed(()=>!!authState.user&&hasPermission('market.read')&&hasPermission('paper.read')),canWrite=computed(()=>hasPermission('paper.write'))
let generation=0,inflight=false
async function load(quiet=false){if(!canRead.value||inflight||busy.value)return;const ticket=++generation;inflight=true;if(!quiet){loading.value=true;data.value=null;error.value=''}try{const r=await planAlertsApi.events(unread.value,page.value);if(ticket===generation){data.value=r;error.value=''}}catch(e){if(ticket===generation)error.value=e instanceof Error?e.message:'提醒列表暂不可用。'}finally{if(ticket===generation){loading.value=false;inflight=false}}}
watch(scope,()=>{++generation;inflight=false;loading.value=false;busy.value=false;page.value=1;data.value=null;error.value='';void load()},{immediate:true})
watch([page,unread],()=>{++generation;inflight=false;busy.value=false;void load()})
function filter(){page.value=1}
async function ack(id:string){const ticket=++generation;inflight=false;busy.value=true;try{await planAlertsApi.ack(id);if(ticket===generation){busy.value=false;await load()}}catch(e){if(ticket===generation)error.value=e instanceof Error?e.message:'标记失败。'}finally{if(ticket===generation)busy.value=false}}
const timer=window.setInterval(()=>{if(!document.hidden)void load(true)},15000)
onUnmounted(()=>{++generation;window.clearInterval(timer)})
</script>
<template><section v-if="canRead" class="plan-alert-feed" aria-label="我的计划提醒"><header><h3>我的计划提醒</h3><div><label><input v-model="unread" type="checkbox" @change="filter"/>仅未读</label><button :disabled="loading||busy" @click="load()">刷新记录</button></div></header><p>本人启用的计划专属提醒，保留原计划版本与观测依据。价格提醒为分钟采样穿越，不表示已成交；每类至多一次。</p><p v-if="error" role="alert">{{error}}<span v-if="data"> 下方为上次成功快照。</span></p><p v-if="loading" role="status">正在读取提醒记录…</p><template v-if="data"><PlanAlertEvents :items="data.items" :can-write="canWrite" :busy="busy" @ack="ack"/><p v-if="!data.items.length">{{unread?'暂无未读的计划专属提醒。':'暂无计划专属触发记录。'}}</p><Pagination v-model:page="page" :page-size="20" :total="data.total" label="计划提醒分页"/></template></section></template>
<style scoped>
.plan-alert-feed{padding:1.2rem;border:1px solid var(--color-line);border-radius:.8rem;background:var(--color-surface);min-width:0}header,header>div{display:flex;align-items:center;gap:.8rem;justify-content:space-between;flex-wrap:wrap}h3{margin:.4rem 0;font-size:.95rem}p,label,button{font-size:.73rem;line-height:1.8}p{color:var(--color-ink-secondary)}button{border:1px solid var(--color-line);border-radius:.4rem;background:var(--color-accent-soft);color:var(--color-accent);padding:.5rem .7rem;cursor:pointer}button:disabled{opacity:.5}[role=alert]{padding:.6rem;background:#fff0ee;color:#9e352d;border-radius:.4rem}
</style>

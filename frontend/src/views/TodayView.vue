<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {RouterLink} from 'vue-router'
import {authState,hasPermission} from '../services/auth'
import {decisionsApi,type DecisionInbox,type InboxFilter} from '../services/decisions'
import {workspaceNavigation} from '../utils/workspaceNavigation'
import {instrumentLabel} from '../utils/instrumentNames'
import {formatTime,formatTradingDateTime} from '../utils/format'
import Pagination from '../components/Pagination.vue'
import PlanAlertFeed from '../components/PlanAlertFeed.vue'

const filter=ref<InboxFilter>('ALL'),page=ref(1),data=ref<DecisionInbox|null>(null),loading=ref(false),error=ref('')
const scope=computed(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId,authState.user?.permissions]))
const canRead=computed(()=>!!authState.user&&hasPermission('paper.read')&&hasPermission('market.read'))
const links=computed(()=>workspaceNavigation(authState.user).groups.filter(g=>g.id!=='today'))
const filters:{id:InboxFilter;key:keyof DecisionInbox['counts'];label:string;hint:string}[]=[
 {id:'ALL',key:'all',label:'全部档案',hint:'本人服务端保存的观察与计划'},
 {id:'EXPIRED',key:'expired',label:'已过有效期',hint:'保留原计划，进入档案复核'},
 {id:'EXPIRING',key:'expiring',label:'24小时内到期',hint:'按最新保存版本的有效期'},
 {id:'REVIEW',key:'review',label:'模拟待复盘',hint:'已关联模拟，尚未记录模拟复盘'},
 {id:'UNPLANNED',key:'unplanned',label:'尚未形成计划',hint:'已保存观察，未保存手工计划'},
]
const timing={UNPLANNED:'观察待完善',EXPIRING:'24小时内到期',EXPIRED:'已过有效期',PLANNED:'已保存计划'}
const outcomes:Record<string,string>={WAITING:'继续观察',ABANDONED:'已记放弃',PAPER_REVIEW:'已记模拟复盘'}
let generation=0
function validate(value:DecisionInbox){
 const date=(v:unknown)=>typeof v==='string'&&Number.isFinite(Date.parse(v))
 const count=(v:unknown)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0
 if(!value||!date(value.asOf)||!value.counts||!filters.every(f=>count(value.counts[f.key]))||!count(value.total)||!Array.isArray(value.items)||!value.items.every(i=>i&&typeof i.id==='string'&&!!i.id&&typeof i.symbol==='string'&&typeof i.label==='string'&&Object.hasOwn(timing,i.timing)&&typeof i.needsReview==='boolean'&&(i.validUntil===null||date(i.validUntil)))||value.filter!==filter.value||value.page!==page.value||value.size!==20)throw new Error('今日待办数据结构异常，请刷新重试。')
 return value
}
async function load(){
 const ticket=++generation;data.value=null;error.value='';loading.value=false
 if(!canRead.value)return
 loading.value=true
 try{const result=await decisionsApi.inbox(filter.value,page.value);if(ticket===generation)data.value=validate(result)}
 catch(e){if(ticket===generation)error.value=e instanceof Error?e.message:'待办读取失败，请稍后重试。'}
 finally{if(ticket===generation)loading.value=false}
}
function choose(value:InboxFilter){filter.value=value;if(page.value!==1)page.value=1;else void load()}
watch(scope,()=>{page.value=1;filter.value='ALL';void load()},{immediate:true})
watch(page,()=>void load())
onUnmounted(()=>{++generation})
</script>

<template>
 <div class="today-desk">
  <header class="today-intro"><div><p class="eyebrow">MY WORKSPACE / 从自己的计划开始</p><h2>先处理已有计划，再寻找机会。</h2><p>把有效期、观察和复盘放在一起。需要重新判断时，回到原始依据与保存版本。</p></div><button v-if="canRead" :disabled="loading" @click="load">{{loading?'正在更新…':'刷新待办'}}</button></header>
  <p class="coverage">覆盖范围：本人在本系统保存的决策档案与关联模拟。有效期按服务器时间计算；不含外部账户、未关联模拟及本机尚未导入的日志。</p>
  <section v-if="!canRead" class="today-card"><h3>当前账号暂不能读取决策待办</h3><p>需要行情与模拟档案读取权限。仍可从下方进入已授权的工作区。</p></section>
  <template v-else>
   <p v-if="error" class="today-error" role="alert">{{error}} <button @click="load">重新载入</button></p>
   <div class="task-counts" aria-label="待办分类"><button v-for="f in filters" :key="f.id" :aria-pressed="filter===f.id" :disabled="loading" @click="choose(f.id)"><span>{{f.label}}</span><strong>{{data?data.counts[f.key]:'—'}}</strong><small>{{f.hint}}</small></button></div>
   <section class="today-card" aria-label="我的待办列表" :aria-busy="loading">
    <header class="task-heading"><h3>{{filters.find(f=>f.id===filter)?.label}}</h3><small v-if="data">快照 {{formatTime(data.asOf)}} · 只读汇总</small></header>
    <p v-if="loading" role="status">正在读取本人计划…</p>
    <template v-else-if="data">
     <div v-if="!data.items.length" class="today-empty"><h4>{{data.counts.all===0?'还没有保存的决策档案':'这一类暂时没有待办'}}</h4><p>{{data.counts.all===0?'从行情预警或品种研究保存一条观察，后续计划和复盘会在这里汇总。':'可切换其他分类，或继续查看原档案。'}}</p><RouterLink to="/paper/decisions">打开我的档案 ↗</RouterLink></div>
     <article v-for="task in data.items" :key="task.id" class="task-row"><div><div class="task-badges"><span :class="task.timing.toLowerCase()">{{timing[task.timing]}}</span><span v-if="task.needsReview">模拟待复盘</span><span v-if="task.latestOutcome">{{outcomes[task.latestOutcome]??task.latestOutcome}}</span></div><RouterLink class="task-title" :to="'/paper/decisions/'+task.id">{{instrumentLabel(task.symbol)}} · {{task.label}}</RouterLink><p>{{task.version?'最新计划 v'+task.version:'尚无手工计划'}}<template v-if="task.validUntil"> · 有效至 {{formatTradingDateTime(task.validUntil)}}</template><template v-if="task.sourceKind==='LOCAL_IMPORT'"> · 本机导入，来源未核验</template></p></div><div class="task-actions"><RouterLink :to="'/paper/decisions/'+task.id">{{task.needsReview?'查看计划与复盘':'打开档案'}} ↗</RouterLink><RouterLink v-if="task.sessionId" :to="{path:'/paper',query:{session:task.sessionId,decision:task.id}}">关联模拟账本 ↗</RouterLink></div></article>
     <Pagination v-model:page="page" :page-size="20" :total="data.total" label="今日待办分页"/>
    </template>
    <p v-else-if="error">待办暂不可用，恢复后重新载入。</p>
    <p class="task-definition">分类可以重叠。“模拟待复盘”表示最新计划已关联模拟，且尚无该版本的模拟复盘、最近也未记为放弃；不表示已经成交或平仓。到期分类不改变计划，行情与风险需进入档案重新核验。</p>
   </section>
  </template>
  <PlanAlertFeed/>
  <section class="workspace-start"><h3>继续工作</h3><div><RouterLink v-for="link in links" :key="link.id" :to="link.to"><strong>{{link.label}} ↗</strong><span>{{({opportunities:'查看市场变化与事件',trade:'打开图表、预警与模拟',strategies:'编辑规则、实验与版本',review:'还原原计划与判断'})[link.id as 'opportunities'|'trade'|'strategies'|'review']}}</span></RouterLink></div></section>
 </div>
</template>

<style scoped>
.today-desk{display:grid;gap:1.25rem;min-width:0}.today-intro,.task-heading{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}.eyebrow{font-size:.67rem;color:var(--color-accent);letter-spacing:.08em}.today-intro h2{font-size:clamp(1.35rem,2vw,1.9rem);margin:.6rem 0}.today-intro p,.coverage,.today-card p{font-size:.77rem;line-height:1.8;color:var(--color-ink-secondary)}.coverage{padding:.8rem 1rem;background:var(--color-accent-soft);border-radius:.6rem;margin:0}.today-desk button{cursor:pointer;font:inherit;border:1px solid var(--color-line);background:var(--color-surface);color:var(--color-accent);padding:.65rem .85rem;border-radius:.6rem;font-size:.76rem}.today-desk button:disabled{cursor:wait;opacity:.6}.task-counts{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.7rem}.task-counts button{text-align:left;display:grid;gap:.65rem;padding:1rem}.task-counts button[aria-pressed=true]{border-color:var(--color-accent);background:var(--color-accent-soft)}.task-counts strong{font:500 1.9rem var(--font-numeric)}.task-counts small{font-size:.65rem;line-height:1.6;color:var(--color-ink-secondary)}.today-card{background:var(--color-surface);border:1px solid var(--color-line);border-radius:.9rem;padding:1.3rem;min-width:0}.today-card h3,.workspace-start h3{font-size:.95rem;margin:0}.task-heading small{color:var(--color-ink-secondary);font-size:.68rem}.task-row{display:flex;justify-content:space-between;gap:1rem;align-items:center;padding:1.2rem 0;border-bottom:1px solid var(--color-line)}.task-row>div{min-width:0}.task-title{font-size:.9rem;color:var(--color-ink);font-weight:650;text-decoration:none;overflow-wrap:anywhere}.task-row p{margin:.5rem 0 0}.task-badges{display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.6rem}.task-badges span{padding:.22rem .5rem;border-radius:.3rem;font-size:.62rem;background:var(--color-accent-soft);color:var(--color-accent)}.task-badges .expired{background:#fff0ee;color:#9e352d}.task-badges .expiring{background:#fff5dd;color:#876019}.task-actions{display:grid;gap:.6rem;flex-shrink:0}.task-actions a,.today-empty a{font-size:.74rem;color:var(--color-accent)}.today-empty{padding:1.5rem 0}.today-empty h4{font-size:1rem;margin:.7rem 0}.task-definition{border-top:1px solid var(--color-line);padding-top:.8rem}.today-error{padding:1rem;background:#fff0ee;color:#9e352d;border-radius:.6rem;font-size:.8rem}.workspace-start>div{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin-top:.9rem}.workspace-start a{display:grid;gap:.7rem;text-decoration:none;color:var(--color-accent);border:1px solid var(--color-line);border-radius:.7rem;padding:1rem}.workspace-start strong{font-size:.82rem}.workspace-start span{font-size:.7rem;color:var(--color-ink-secondary);line-height:1.6}@media(max-width:1100px){.task-counts{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:600px){.task-counts{grid-template-columns:repeat(2,minmax(0,1fr))}.task-counts button:first-child{grid-column:1/-1}.workspace-start>div{grid-template-columns:repeat(2,minmax(0,1fr))}.task-row{align-items:flex-start;flex-direction:column}.task-actions{display:flex;flex-wrap:wrap}.today-card{padding:1rem}}
</style>

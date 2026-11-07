<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {useRoute,useRouter,RouterLink} from 'vue-router'
import {decisionsApi,type DecisionCase,type PlanFields,type Readiness} from '../services/decisions'
import {liveApi,type IntradaySnapshot,type LiveFrequency,LIVE_PERIODS} from '../services/live'
import {frozenDecisionGeometry} from '../utils/decisionGeometry'
import {requestUuid} from '../utils/requestId'
import {decisionDetail,decisionPage} from '../utils/decisionResponses'
import {formatTime,formatNumber} from '../utils/format'
import {instrumentLabel} from '../utils/instrumentNames'
import {hasPermission,authState} from '../services/auth'
import TongdaxinChart from '../components/TongdaxinChart.vue'
import Pagination from '../components/Pagination.vue'
import DecisionResearchSources from '../components/DecisionResearchSources.vue'
import DecisionMonitorLinks from '../components/DecisionMonitorLinks.vue'
import PlanAlertPanel from '../components/PlanAlertPanel.vue'

const route=useRoute(),router=useRouter(),cases=ref<DecisionCase[]>([]),item=ref<DecisionCase|null>(null)
// Vue Router represents an omitted optional segment as '', not necessarily undefined.
const identityScope=computed(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId,authState.user?.permissions]))
const caseId=computed(()=>typeof route.params.id==='string'&&route.params.id.length>0?route.params.id:undefined)
const listPage=ref(1),listTotal=ref(0),loading=ref(false)
const error=ref(''),busy=ref(false),chartError=ref(''),chart=ref<IntradaySnapshot|null>(null),view=ref<'THEN'|'NOW'>('THEN')
type DraftFields=Omit<PlanFields,'side'>&{side:''|'LONG'|'SHORT'}
const defaults=():DraftFields=>({side:'',entry:0,stop:0,target:0,lots:1,equity:100000,budget:1000,hypothesis:'',invalidation:'',validUntil:new Date(Date.now()+4*3600000).toISOString()})
const selectedPlan=ref(''),fields=ref<DraftFields>(defaults())
const expiry=computed({get:()=>{const d=new Date(fields.value.validUntil);return Number.isFinite(d.getTime())?new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16):''},set:(v:string)=>{fields.value.validUntil=v?new Date(v).toISOString():''}})
const baseline=ref(''),notes=ref(''),outcome=ref('WAITING'),readiness=ref<Readiness|null>(null),message=ref('')
const saveCommand=ref(requestUuid()),paperCommand=ref(requestUuid()),reviewCommand=ref(requestUuid())
const clock=ref(Date.now()),verifiedAt=ref(0),checkTimer=window.setInterval(()=>{clock.value=Date.now()},1000)
let generation=0,chartGeneration=0
const canWrite=computed(()=>hasPermission('paper.write'))
const plan=computed(()=>item.value?.plans.find(p=>p.id===selectedPlan.value))
const dirty=computed(()=>JSON.stringify(fields.value)!==baseline.value)
const evidence=computed(()=>item.value?.origin.evidence??{})
const frequency=computed<LiveFrequency|null>(()=>{
 const n=Number(evidence.value.triggerSeconds)
 return [15,30,60,180,300,900].includes(n)?n as LiveFrequency:n===86400?'DAY':null
})
const asOf=computed(()=>String(evidence.value.featureAt??item.value?.origin.observedAt??''))
const points=computed(()=>{const rows=chart.value?.points??[];return view.value==='NOW'?rows:rows.filter(p=>Date.parse(p.timestamp)<=Date.parse(asOf.value))})
const geometry=computed(()=>view.value==='THEN'?frozenDecisionGeometry(evidence.value.geometry,points.value,String(evidence.value.availableAt??item.value?.origin.createdAt??'')):chart.value?.geometry)
const latest=computed(()=>!!plan.value&&plan.value.version===item.value?.version)
const binding=computed(()=>item.value?.paper.find(b=>b.planId===selectedPlan.value))
const freshCheck=computed(()=>verifiedAt.value>0&&clock.value-verifiedAt.value<30000)
const canSimulate=computed(()=>canWrite.value&&!dirty.value&&latest.value&&readiness.value?.ready&&freshCheck.value&&!busy.value)
function reason(e:unknown){return e instanceof Error?e.message:'请求失败，请重试。'}
function monitorSaved(value:DecisionCase){if(value.id!==item.value?.id)return;item.value.monitors=decisionDetail(value,value.id).monitors;message.value='已关联本计划版本，原规则任务保持原状。'}
function applyPlan(){
 const f=plan.value?.fields
 fields.value=f?{...f}:defaults()
 baseline.value=JSON.stringify(fields.value);readiness.value=null;notes.value='';outcome.value='WAITING';saveCommand.value=requestUuid();paperCommand.value=requestUuid();reviewCommand.value=requestUuid();message.value=''
}
async function load(){
 const ticket=++generation;error.value='';item.value=null;chart.value=null;readiness.value=null;loading.value=true
 try{
  const id=caseId.value
  if(id){
   const response=await decisionsApi.detail(id);if(ticket!==generation)return
   const loaded=decisionDetail(response,id)
   if(route.query.plan!==undefined&&(typeof route.query.plan!=='string'||!loaded.plans.some(p=>p.id===route.query.plan)))throw new Error('指定计划版本不存在于本档案，请核对原链接。')
   item.value=loaded;selectedPlan.value=loaded.plans.find(p=>p.id===route.query.plan)?.id??loaded.plans[0]?.id??'';applyPlan();if(route.query.plan===undefined&&selectedPlan.value)await router.replace({query:{...route.query,plan:selectedPlan.value}});if(ticket!==generation)return;void loadChart()
  }else{const response=await decisionsApi.list(listPage.value);if(ticket===generation){const rows=decisionPage(response);cases.value=rows.items;listTotal.value=rows.total}}
 }catch(e){if(ticket===generation)error.value=reason(e)}finally{if(ticket===generation)loading.value=false}
}
async function loadChart(){
 const ticket=++chartGeneration,target=item.value?.symbol,f=frequency.value;chart.value=null;chartError.value=''
 if(item.value?.sourceKind==='LOCAL_IMPORT'&&view.value==='THEN'){chartError.value='本机导入的历史时点未经核验，仅保留原文；可主动切换现在查看当前行情。';return}
 if(!target||!f){chartError.value='原事件没有可靠的周期元数据，保留证据，暂不重建历史图。';return}
 try{const loaded=await liveApi.bars(target,f);if(ticket!==chartGeneration||target!==item.value?.symbol)return
  if(loaded.symbol!==target||(typeof f==='number'?loaded.seconds!==f:loaded.period!==f))throw new Error('图表合约或周期不符，已停止展示。')
  chart.value=loaded
 }catch(e){if(ticket===chartGeneration)chartError.value=reason(e)}
}
async function act(task:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await task()}catch(e){error.value=reason(e)}finally{busy.value=false}}
function save(){void act(async()=>{
 const c=item.value,d=fields.value;if(!c)return;if(!d.side){error.value='请先明确选择自己的研究方向。';return}
 const response=await decisionsApi.save(c.id,c.version,{...d,side:d.side},saveCommand.value);if(item.value?.id!==c.id)return
 const result=decisionDetail(response,c.id)
 item.value=result;selectedPlan.value=result.plans[0]?.id??'';applyPlan();if(route.query.plan!==undefined)await router.replace({query:{...route.query,plan:selectedPlan.value}});message.value='新版本已保存到服务端；旧计划与复盘保留。'
})}
function check(){readiness.value=null;verifiedAt.value=0;void act(async()=>{const c=item.value,p=plan.value;if(!c||!p)return;const result=await decisionsApi.check(c.id,p.id);if(item.value?.id===c.id&&plan.value?.id===p.id&&!dirty.value){readiness.value=result;verifiedAt.value=Date.now();clock.value=Date.now()}})}
function simulate(){void act(async()=>{
 const c=item.value,p=plan.value;if(!c||!p||dirty.value)return
 readiness.value=null;verifiedAt.value=0
 const result=await decisionsApi.paper(c.id,p.id,paperCommand.value)
 await router.push({path:'/paper',query:{session:result.sessionId,decision:c.id}})
})}
function review(){void act(async()=>{
 const c=item.value,p=plan.value;if(!c||!p)return
 const response=await decisionsApi.review(c.id,p.id,outcome.value,notes.value,reviewCommand.value)
 if(item.value?.id===c.id){const result=decisionDetail(response,c.id);item.value=result;notes.value='';reviewCommand.value=requestUuid();message.value='私人复盘已保存，原计划保持不变。'}
})}
watch(selectedPlan,()=>{applyPlan();if(!loading.value&&!busy.value&&selectedPlan.value&&route.query.plan!==selectedPlan.value)void router.replace({query:{...route.query,plan:selectedPlan.value}})},{flush:'sync'})
watch(fields,()=>{readiness.value=null},{deep:true,flush:'sync'})
watch(()=>[caseId.value,route.query.plan,identityScope.value] as const,([id,requested,scope],before)=>{const identityChanged=before&&before[2]!==scope;if(identityChanged){++generation;item.value=null;chart.value=null;readiness.value=null;if(!authState.user||!hasPermission('paper.read')||!hasPermission('market.read')){error.value='当前身份不能读取此档案。';return}}const current=item.value;if(!identityChanged&&current&&current.id===id&&typeof requested==='string'&&current.plans.some(p=>p.id===requested)){if(selectedPlan.value!==requested)selectedPlan.value=requested;return}++chartGeneration;view.value='THEN';void load()},{immediate:true})
watch(listPage,()=>{if(!caseId.value)void load()})
watch(view,()=>{if(item.value?.sourceKind==='LOCAL_IMPORT')void loadChart()})
onUnmounted(()=>{++generation;++chartGeneration;window.clearInterval(checkTimer)})
</script>

<template>
 <main class="decision-desk">
  <header class="desk-heading"><div><p>交易决策工作台</p><h2>{{item?(item.sourceKind&&item.sourceKind!=='MONITOR_EVENT'?'围绕原研究形成判断与计划':'从原事件形成自己的计划'):'我的决策档案'}}</h2><span>预警 / 研究依据 → 计划版本 → 手动模拟 / 继续等待 → 私人复盘</span></div><nav><RouterLink to="/live">行情与预警</RouterLink><RouterLink to="/strategy">研究工作台</RouterLink><RouterLink to="/paper/decisions">我的档案</RouterLink></nav></header>
  <p v-if="error" class="notice error" role="alert">{{error}} <button :disabled="busy" @click="load">重新载入</button>（重新载入会恢复服务端保存版本）</p>
  <p v-if="message" class="notice" role="status">{{message}}</p>
  <template v-if="item">
   <section class="context-bar" aria-label="决策上下文"><strong>{{instrumentLabel(item.symbol)}}</strong><span>{{item.sourceKind==='SERVER_CALC'?'研究来源 · ':item.sourceKind==='LOCAL_IMPORT'?'本机导入 · ':'原事件 #'}}{{item.origin.id}}</span><span>决策档案 {{item.id}}</span><span>{{item.sourceKind&&item.sourceKind!=='MONITOR_EVENT'?'模型':'规则'}} {{item.origin.algorithmVersion}}</span><span>{{item.sourceKind==='LOCAL_IMPORT'?'未核验旧记录':item.sourceKind==='SERVER_CALC'?'服务端研究归档':'LIVE来源 · 事件回看'}}</span></section>
   <section class="origin card"><h3>{{item.origin.label}}</h3><div class="time-grid"><span>{{item.sourceKind==='LOCAL_IMPORT'?'自报资料时点':item.sourceKind==='SERVER_CALC'?'原资料截止':'行情发生'}}：{{formatTime(item.origin.observedAt)}}</span><span>{{item.sourceKind&&item.sourceKind!=='MONITOR_EVENT'?'参考资料日期':'特征柱'}}：{{formatTime(asOf)}}</span><span>首次可知：{{evidence.availableAt||evidence.confirmedAt?formatTime(String(evidence.availableAt??evidence.confirmedAt)):'原记录未提供'}}</span><span>系统记录：{{formatTime(item.origin.createdAt)}}</span></div><p>{{item.sourceKind==='LOCAL_IMPORT'?'此处保留本机声明的时间与内容，不证明当时行情或实际执行。':item.sourceKind==='SERVER_CALC'?'此处引用服务端当次核算，不代表当前行情、有效策略或执行资格。':'此处是原事件的冻结引用，后来修改规则不会覆盖它；触发不等于入场建议。'}}</p><details><summary>原始条件、统计与图层证据</summary><pre>{{JSON.stringify(evidence,null,2)}}</pre></details></section>
   <div class="desk-grid">
    <div><DecisionResearchSources :sources="item.sources??[]" :case-id="item.id" :plan-id="selectedPlan||undefined" :period="typeof route.query.period==='string'?route.query.period:undefined"/><section class="card"><header class="row"><h3>图表与原依据</h3><div><button :aria-pressed="view==='THEN'" @click="view='THEN'">当时</button><button :aria-pressed="view==='NOW'" @click="view='NOW'">现在</button><button @click="loadChart">刷新图表</button></div></header>
     <p>{{view==='THEN'?'历史重建：行情按原特征柱截止；不是触发时保存的完整行情快照。仅使用原事件保存的几何线，缺失不补造。':'当前行情：独立读取最新数据与图层，不覆盖原事件或旧计划。'}} · {{LIVE_PERIODS.find(p=>p.value===frequency)?.label??'周期未知'}}</p>
     <p v-if="chartError" role="alert">{{chartError}}</p><TongdaxinChart v-if="points.length" :key="item.id+view" :points="points" :symbol="item.symbol" :height="380" :geometry="geometry" :drawing-tools="false" :readonly-geometry="true" time-label-mode="datetime-seconds"/>
     <p v-else>该时间段不在当前可读取窗口内，或行情尚不可用。原证据仍可查看，不替换为今天的图。</p>
    </section>
    <DecisionMonitorLinks v-if="plan" :case-id="item.id" :plan-id="plan.id" :symbol="item.symbol" :links="(item.monitors??[]).filter(m=>m.planId===plan?.id)" :editable="canWrite&&latest&&!dirty&&Date.parse(plan.fields.validUntil)>clock" @saved="monitorSaved"/>
    <PlanAlertPanel v-if="plan" :key="plan.id" :case-id="item.id" :plan-id="plan.id" :editable="canWrite&&latest&&!dirty&&!busy&&Date.parse(plan.fields.validUntil)>clock"/>
    <section class="card"><h3>私人复盘</h3><p>可记录继续等待或放弃。此处不填写虚构成交或收益；实际订单和成交由模拟账本记录。</p><form v-if="plan&&canWrite" @submit.prevent="review"><label>对应版本<strong>v{{plan.version}}</strong></label><label>结果<select v-model="outcome"><option value="WAITING">继续观察</option><option value="ABANDONED">放弃计划</option><option value="PAPER_REVIEW">模拟过程复盘</option></select></label><label>依据与偏差<textarea v-model="notes" required maxlength="4000" rows="3"/></label><button :disabled="busy||!notes.trim()">保存私人复盘</button></form>
     <article v-for="r in item.reviews" :key="r.id" class="review"><strong>v{{r.version}} · {{r.outcome==='WAITING'?'继续观察':r.outcome==='ABANDONED'?'放弃计划':'模拟过程复盘'}}</strong><time>{{formatTime(r.createdAt)}}</time><p>{{r.notes}}</p></article>
    </section></div>
    <section class="card plan"><h3>计划与风险</h3><p v-if="!plan">尚未形成手工计划。下方为空白草稿，方向与参数需自行明确，不会把等待或减仓结果变成入场。</p><label v-if="item.plans.length">已保存版本<select v-model="selectedPlan"><option v-for="p in item.plans" :key="p.id" :value="p.id">v{{p.version}}{{p.version===item.version?' · 最新':' · 历史只读'}}</option></select></label>
     <p v-if="plan&&!latest" class="notice">正在阅读历史版本。切回最新版本后才能修订或送入模拟。</p>
     <form @submit.prevent="save"><fieldset :disabled="!canWrite||busy||!!plan&&!latest"><div class="field-grid"><label>方向<select v-model="fields.side" required><option value="" disabled>请选择研究方向</option><option value="LONG">多头研究</option><option value="SHORT">空头研究</option></select></label><label>模拟资金<input v-model.number="fields.equity" type="number" min="1000" max="1000000000" step="0.01" required/></label><label>入场参考<input v-model.number="fields.entry" type="number" min="0.000001" step="any" required/></label><label>保护价<input v-model.number="fields.stop" type="number" min="0.000001" step="any" required/></label><label>目标参考<input v-model.number="fields.target" type="number" min="0.000001" step="any" required/></label><label>手数<input v-model.number="fields.lots" type="number" min="1" max="100000" step="1" required/></label><label>单笔风险预算<input v-model.number="fields.budget" type="number" min="0.01" max="1000000000" step="0.01" required/></label></div><label>计划有效至（本机时区）<input v-model="expiry" type="datetime-local" required/></label><label>为什么观察<textarea v-model="fields.hypothesis" maxlength="2000" required rows="2"/></label><label>等待条件与失效理由<textarea v-model="fields.invalidation" maxlength="2000" required rows="2"/></label><button :disabled="!dirty&&!!plan">保存新版本 v{{item.version+1}}</button></fieldset></form>
     <p v-if="dirty" class="notice">有未保存修改；先保存再核验。旧版本保留。</p><p>保存草稿不代表风险核验通过。模拟资金为本计划手填情景，未接外部账户或组合敞口。</p>
     <button v-if="plan&&canWrite" :disabled="busy||dirty||!latest" @click="check">核验当前保存版本</button>
     <div v-if="readiness" class="notice" role="status"><strong>{{readiness.ready?'具备手动模拟账户准备条件':'暂不能进入新模拟'}}</strong><p>检查于 {{formatTime(readiness.checkedAt)}}</p><p v-if="readiness.ready&&!freshCheck">本次界面核验已过30秒，请重新核验；后台创建时仍会再次检查。</p><p v-if="readiness.scenarioLoss!=null">保护价情景损失（含费用预留）：{{formatNumber(readiness.scenarioLoss)}} 元 · 保证金：{{formatNumber(readiness.marginRequired)}} 元</p><ul><li v-for="r in readiness.reasons" :key="r">{{r}}</li></ul><p>{{readiness.assumptions}}</p><p>{{readiness.meaning}}</p></div>
     <p>创建本版本关联的手动模拟账户后，服务端会在新增开仓及成交时核对方向、持仓与挂单合计手数、风险预算、有效期和版本。已发生亏损与手续费持续占用预算，盈利不冲抵已发生亏损；保护价仅用于情景试算，不自动止损止盈。模拟账本沿用工作空间共享权限，只有计划本人可新增开仓和撮合开仓挂单，私人参数仍仅本人可读。不会生成实盘订单。</p>
     <RouterLink v-if="binding" :to="{path:'/paper',query:{session:binding.sessionId,decision:item.id}}">打开本版本关联的模拟账本 ↗</RouterLink><button v-else :disabled="!canSimulate" @click="simulate">创建关联的手动模拟账户</button>
    </section>
   </div>
  </template>
  <section v-else-if="!error" class="card"><p v-if="loading">正在读取服务端档案…</p><template v-else><p v-if="!cases.length">还没有决策档案。可从行情预警或研究工作台保存观察，也可预览导入自己的本机旧日志。</p><article v-for="c in cases" :key="c.id" class="case-row"><RouterLink :to="'/paper/decisions/'+c.id">{{instrumentLabel(c.symbol)}} · {{c.origin.label}}</RouterLink><span>v{{c.version}} · {{formatTime(c.updatedAt)}}</span></article><Pagination v-model:page="listPage" :page-size="20" :total="listTotal" label="决策档案分页"/></template></section>
 </main>
</template>

<style scoped>
.decision-desk{display:grid;gap:1rem;min-width:0}.desk-heading,.row,.context-bar,.case-row{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}.desk-heading h2{margin:.4rem 0}.desk-heading p{font-size:.7rem;color:var(--color-accent)}nav{display:flex;gap:1rem}.card,.context-bar{padding:1.25rem;border:1px solid var(--color-line);border-radius:1rem;background:var(--color-surface)}.context-bar{justify-content:flex-start;font-size:.73rem;overflow-wrap:anywhere}.desk-grid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:1rem;align-items:start}.desk-grid>div{display:grid;gap:1rem;min-width:0}.card{min-width:0}.card h3{margin:0 0 1rem;font-size:1rem}.card p,.time-grid,.review,.case-row{font-size:.76rem;line-height:1.8;color:var(--color-ink-secondary)}.time-grid,.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem}.time-grid{margin-bottom:1rem}label{display:grid;gap:.4rem;font-size:.76rem;margin-bottom:.8rem}input,select,textarea{box-sizing:border-box;width:100%;min-width:0;border:1px solid var(--color-line);background:var(--color-surface);color:var(--color-ink);padding:.65rem;border-radius:.5rem;font:inherit}fieldset{border:0;padding:0;margin:0;min-width:0}button{border:1px solid var(--color-line);border-radius:.5rem;padding:.6rem .8rem;background:var(--color-accent-soft);color:var(--color-accent);cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}button[aria-pressed=true]{outline:2px solid var(--color-accent)}.row>div{display:flex;gap:.5rem;flex-wrap:wrap}.notice{padding:1rem;background:var(--color-accent-soft);border-radius:.6rem;font-size:.76rem;line-height:1.8}.error{background:#fff0ee;color:#9e352d}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.7rem;max-height:25rem;overflow:auto}summary{font-size:.78rem;cursor:pointer}.review,.case-row{border-top:1px solid var(--color-line);padding:1rem 0}.review time{display:block;font-size:.7rem}.review p{white-space:pre-wrap}@media(max-width:1000px){.desk-grid{grid-template-columns:minmax(0,1fr)}}@media(max-width:550px){.field-grid,.time-grid{grid-template-columns:minmax(0,1fr)}.card,.context-bar{padding:1rem}.desk-heading h2{font-size:1.2rem}}
</style>

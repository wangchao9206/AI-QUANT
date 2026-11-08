<script setup lang="ts">
import {computed,ref,watch,onUnmounted} from 'vue'
import {RouterLink,useRoute,useRouter} from 'vue-router'
import {authState,hasPermission} from '../services/auth'
import {api} from '../services/api'
import {decisionsApi,type DecisionCase} from '../services/decisions'
import {decisionDetail} from '../utils/decisionResponses'
import {tradingQuery,contextUuid,contextPeriod} from '../utils/tradingContext'
import {optionQuery,optionReference} from '../utils/optionContext'
import {multiframeApi,type MultiframeRun} from '../features/chanlun/multiframe'
import {multiframeQuery,multiframeResult,frozenSelection} from '../utils/chanlunContext'
import {validInstrument,instrumentPath,researchPath} from '../utils/marketNavigation'
import {LIVE_PERIODS} from '../services/live'
import {instrumentLabel} from '../utils/instrumentNames'
import {formatTime} from '../utils/format'
const route=useRoute(),router=useRouter(),item=ref<DecisionCase|null>(null),chosenPlan=ref(''),session=ref(''),paperSymbol=ref(''),paperMode=ref(''),error=ref(''),loading=ref(false)
const isCase=computed(()=>route.name==='decision-desk'&&typeof route.params.id==='string'&&!!route.params.id)
const isPaper=computed(()=>route.path==='/paper')
const isOptions=computed(()=>route.path==='/options')
const isMulti=computed(()=>route.path==='/chanlun/multiframe')
const visible=computed(()=>route.path==='/live'||isMulti.value||isOptions.value||isCase.value||isPaper.value||['instrument','research'].includes(String(route.name)))
const parsed=computed(()=>isMulti.value?multiframeQuery(route.query):isOptions.value?optionQuery(route.query):tradingQuery(isPaper.value?{period:route.query.period}:route.query,isCase.value))
const symbol=computed(()=>paperSymbol.value||validInstrument(route.params.symbol)||parsed.value.symbol||item.value?.symbol||'')
const compatible=computed(()=>!!item.value&&symbol.value===item.value.symbol)
const period=computed(()=>String(route.query.period===undefined&&route.query.seconds===undefined&&item.value?(contextPeriod(String(item.value.origin.evidence?.triggerSeconds))??(Number(item.value.origin.evidence?.triggerSeconds)===86400?'DAY':parsed.value.frequency)):parsed.value.frequency))
const plan=computed(()=>item.value?.plans.find(p=>p.id===chosenPlan.value))
const binding=computed(()=>item.value?.paper.find(p=>p.planId===chosenPlan.value))
const chanSource=ref<MultiframeRun|null>(null),chanError=ref('')
const chanReference=computed(()=>chanSource.value?{chanObservation:chanSource.value.id,...typeof route.query.chanFrame==='string'?{chanFrame:route.query.chanFrame}:{},...typeof route.query.chanStructure==='string'?{chanStructure:route.query.chanStructure}:{}}:{})
const query=computed(()=>({symbol:symbol.value,period:period.value,...optionReference(route.query,symbol.value),...chanReference.value,...compatible.value?{case:item.value!.id,...chosenPlan.value?{plan:chosenPlan.value}:{}}:{}}))
const chanTarget=computed(()=>({path:'/chanlun/multiframe',query:{symbol:symbol.value,period:period.value,...compatible.value?{case:item.value!.id,...chosenPlan.value?{plan:chosenPlan.value}:{}}:{},...chanSource.value?{observation:chanSource.value.id,frames:chanSource.value.request.frames,...typeof route.query.chanFrame==='string'?{frame:route.query.chanFrame}:{},...typeof route.query.chanStructure==='string'?{structure:route.query.chanStructure}:{}}:{}}}))
const allow=computed(()=>!loading.value&&!error.value&&!parsed.value.errors.length&&!!symbol.value)
let generation=0
let chanGeneration=0
watch(()=>JSON.stringify([visible.value,isMulti.value,route.query.chanObservation,route.query.chanFrame,route.query.chanStructure,symbol.value,authState.user?.id,authState.user?.tenantId,authState.user?.permissions]),async()=>{
 const ticket=++chanGeneration;chanSource.value=null;chanError.value=''
 if(!visible.value||isMulti.value||route.query.chanObservation===undefined)return
 try{
  if(!hasPermission('chanlun.read'))throw new Error('当前身份不能读取原缠论观察。')
  const parsed=multiframeQuery({symbol:symbol.value,observation:route.query.chanObservation,frame:route.query.chanFrame,structure:route.query.chanStructure})
  if(parsed.errors.length)throw new Error(parsed.errors.join(' '))
  const value=multiframeResult(await multiframeApi.get(parsed.observation),parsed.observation)
  if(ticket!==chanGeneration)return
  if(value.request.symbol!==symbol.value)throw new Error('原缠论观察与当前合约不同，未关联其他月份。')
  frozenSelection(value,parsed.frame,parsed.structure);chanSource.value=value
 }catch(e){if(ticket===chanGeneration)chanError.value=e instanceof Error?e.message:'原缠论观察不可读取。'}
},{immediate:true})
watch(()=>JSON.stringify([visible.value,route.path,route.query.case,route.query.plan,route.query.session,route.query.contract,authState.user?.id,authState.user?.tenantId,authState.user?.permissions]),async()=>{
 const ticket=++generation;item.value=null;chosenPlan.value='';session.value='';paperSymbol.value='';paperMode.value='';error.value='';loading.value=false
 if(!visible.value)return
 let caseId=isCase.value?contextUuid(route.params.id):contextUuid(route.query.case),planId=contextUuid(route.query.plan)
 if(isCase.value&&!caseId){error.value='档案标识无效，请核对原链接。';return}
 if(isPaper.value&&!route.query.session)return
 if(!caseId&&!isPaper.value)return
 if(!authState.user||!hasPermission('paper.read')||!hasPermission('market.read')){error.value='当前身份不能核验关联档案。';return}
 loading.value=true
 try{
  if(isPaper.value){const sid=contextUuid(route.query.session);if(!sid)throw new Error('模拟账户标识无效。');const s=await api.paperSession(sid);if(ticket!==generation)return;if(s.id!==sid||!['LIVE','HISTORICAL'].includes(s.mode))throw new Error('模拟账户响应与原链接不一致。');paperSymbol.value=validInstrument(s.currentContract)||validInstrument(s.symbol);paperMode.value=s.mode;session.value=sid;if(!paperSymbol.value)throw new Error('模拟账户的实际合约不可核验。')
   const source=await decisionsApi.forSession(sid);if(ticket!==generation)return;caseId=contextUuid(source.caseId);planId=contextUuid(source.planId);if(!caseId)return;if(!planId)throw new Error('账户的计划关联版本不可核验。')
  }
  const c=decisionDetail(await decisionsApi.detail(caseId),caseId);if(ticket!==generation)return
  const selected=planId?c.plans.find(p=>p.id===planId):c.plans.find(p=>p.version===c.version)
  if(planId&&!selected)throw new Error('指定计划版本不在此档案中。')
  if(isPaper.value&&!c.paper.some(p=>p.sessionId===session.value&&p.planId===planId))throw new Error('模拟账户与计划关联不一致。')
  item.value=c;chosenPlan.value=selected?.id??''
 }catch(e){if(ticket===generation)error.value=e instanceof Error?e.message:'当前关联暂不能核验。'}finally{if(ticket===generation)loading.value=false}
},{immediate:true})
onUnmounted(()=>{++generation;++chanGeneration})
function clearChan(){const q={...route.query};for(const k of ['chanObservation','chanFrame','chanStructure'])delete q[k];void router.replace({path:route.path,query:q})}
function clear(){const q={...route.query};for(const k of ['case','plan','decision','monitor','mode','asOf','period','seconds','tab','chanObservation','chanFrame','chanStructure',...isMulti.value?['observation','frame','structure','frames']:[],...isOptions.value?['chain','option','side','lots','rate','dividend']:[]])delete q[k];if(!validInstrument(q.symbol)||(isOptions.value||isMulti.value)&&!/^[A-Z]{1,4}\d{3,4}$/.test(String(q.symbol)))delete q.symbol;void router.replace({path:route.path,query:q})}
</script>
<template><section v-if="visible" class="trading-context" aria-label="交易上下文"><header><div><small>{{isOptions||isMulti?'请求的期货标的':'当前交易对象'}}</small><strong>{{symbol?instrumentLabel(symbol):isOptions?'期权链与标的见下方':'尚未选择合约'}}</strong><span>{{paperMode==='HISTORICAL'?'历史模拟':isPaper?'模拟账本':isCase?'档案版本回看':isOptions?'当前期权研究':isMulti?'缠论观察浏览':'当前市场浏览'}}</span><span v-if="!isPaper">看盘周期 {{LIVE_PERIODS.find(p=>String(p.value)===period)?.label}}</span></div><p v-if="loading" role="status">正在核验关联…</p></header>
 <p v-if="error||parsed.errors.length" class="context-error" role="alert">{{error||parsed.errors.join(' ')}} <button v-if="!isCase&&!isPaper" @click="clear">清除关联后继续浏览</button></p>
 <p v-if="item">原档案：{{instrumentLabel(item.symbol)}} · {{plan?'计划 v'+plan.version:'观察记录'}} · 原依据时点 {{formatTime(item.origin.observedAt)}}<span v-if="!compatible"> · 当前合约不同，跨页不会携带此档案关联。</span></p>
 <p v-if="paperMode==='HISTORICAL'">行情与研究入口打开当前市场；模拟账本仍保留原回放时点。</p>
 <p v-if="route.name==='research'">看盘周期会保留；研究结果使用其标注的资料周期。</p>
 <p v-if="isMulti">这里只携带原计划与返回看盘周期；多周期观察按独立主源重建，不自动采集，不把15分钟看盘周期替换成30分/5分证据。</p>
 <p v-if="chanSource">原缠论观察：{{chanSource.report?'冻结重建':'尚未完成'}}<template v-if="chanSource.report"> · 重建界限 {{formatTime(chanSource.report.asOf)}} · 实际采集 {{formatTime(chanSource.report.capturedAt)}}</template>。这是浏览回链，不是原计划当时已引用的证据。</p>
 <p v-if="chanError" class="context-error" role="alert">{{chanError}} <button @click="clearChan">清除观察引用</button></p>
 <p v-if="isOptions">本页使用当前期权快照；看盘周期用于返回期货行情。实际标的、链和合约以下方核验为准，期货计划不会转成期权执行资格。</p>
 <nav v-if="allow" aria-label="当前对象操作"><RouterLink v-if="hasPermission('market.read')" :to="{path:'/live',query:{...query,tab:'futures'}}">{{paperMode==='HISTORICAL'?'查看当前行情':'行情图表'}}</RouterLink><RouterLink v-if="hasPermission('research.read')" :to="{path:researchPath(symbol),query}" >{{paperMode==='HISTORICAL'?'查看当前研究':'研究与判断'}}</RouterLink><RouterLink v-if="hasPermission('options.read')&&hasPermission('market.read')" :to="{path:'/live',query:{...query,tab:'options'}}">对应期权</RouterLink><RouterLink v-if="!isOptions&&hasPermission('options.read')&&/^[A-Z]{1,4}\d{3,4}$/.test(symbol)" :to="{path:'/options',query}">专业期权链</RouterLink><RouterLink v-if="!isMulti&&hasPermission('chanlun.read')&&/^[A-Z]{1,4}\d{3,4}$/.test(symbol)" :to="chanTarget">{{chanSource?'返回缠论观察':'缠论多周期'}}</RouterLink><RouterLink v-if="hasPermission('market.read')" :to="{path:instrumentPath(symbol),query}">品种资料</RouterLink><RouterLink v-if="compatible&&item" :to="{path:'/paper/decisions/'+item.id,query:{plan:chosenPlan||undefined,period}}">{{plan?'返回计划 v'+plan.version:'返回原档案'}}</RouterLink><RouterLink v-if="compatible&&binding" :to="{path:'/paper',query:{session:binding.sessionId,period}}">本版本模拟账本</RouterLink></nav>
 </section></template>
<style scoped>
.trading-context{padding:1rem 1.15rem;border:1px solid var(--color-line);border-radius:.75rem;background:var(--color-surface);margin-bottom:1.3rem;min-width:0}.trading-context header>div,.trading-context nav{display:flex;align-items:center;gap:.65rem;flex-wrap:wrap}.trading-context small{font-size:.65rem;color:var(--color-ink-secondary)}.trading-context strong{font-size:.88rem;overflow-wrap:anywhere}.trading-context span,.trading-context p{font-size:.72rem;line-height:1.8;color:var(--color-ink-secondary)}.trading-context p{margin:.55rem 0}.trading-context nav{margin-top:.8rem}.trading-context a,.trading-context button{font:inherit;font-size:.73rem;padding:.45rem .65rem;border:1px solid var(--color-line);border-radius:.4rem;background:var(--color-accent-soft);color:var(--color-accent);text-decoration:none}.context-error{padding:.6rem;background:#fff0ee;color:#9e352d!important;border-radius:.4rem}
</style>

<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {api,type PaperSession,type BacktestPresets,type PaperAutomationState,type StartPaperAutomation} from '../services/api'
import {workflowsApi,type WorkflowVersion} from '../services/workflows'
import {formatTime,formatTradingDate} from '../utils/format'
import {hasPermission} from '../services/auth'
import {MA20_MACD_BACKTEST_PATH,PAPER_STRATEGIES,type PaperStrategyId} from '../utils/paperStrategies'
import {TRINITY_DEFAULT,TRINITY_STRATEGY_ID,isTrinityPaperContract,trinityPaperConfig,type TrinityDraft} from '../utils/personalTrinity'
const props=defineProps<{session:PaperSession;presets:BacktestPresets|null;busy:boolean;initialStrategy?:PaperStrategyId;selectedTrinity?:TrinityDraft|null;trinityLaunchMissing?:boolean}>()
const emit=defineEmits<{locked:[value:boolean];refresh:[]}>()
const state=ref<PaperAutomationState>({runs:[],events:[]}),error=ref(''),working=ref(false),loading=ref(false)
const versions=ref<WorkflowVersion[]>([])
const form=ref<StartPaperAutomation>({contract:'',strategy:'MA20_MACD',lots:1,stopLossTicks:10,stopLossAtr:0,takeProfitAtr:0,intradayOnly:true})
const active=computed(()=>state.value.runs.find(r=>r.contract===props.session.currentContract&&r.enabled))
const lastRun=computed(()=>active.value??state.value.runs.find(r=>r.contract===props.session.currentContract))
const names:Record<string,string>=Object.fromEntries(PAPER_STRATEGIES.map(({id,name})=>[id,name]))
const strategies=computed(()=>PAPER_STRATEGIES.map(({id,name})=>({id,name:props.presets?.strategies?.find(s=>s.id===id)?.name??name})))
const isTrinity=computed(()=>form.value.strategy===TRINITY_STRATEGY_ID)
const trinitySupported=computed(()=>isTrinityPaperContract(props.session.currentContract))
const trinity=computed(()=>trinityPaperConfig(props.selectedTrinity?.config??TRINITY_DEFAULT))
const trinityLots=computed(()=>trinity.value.addMode==='NONE'?1:2)
const trinityConfirmation={either:'缠论或威科夫',chan:'仅缠论',wyckoff:'仅威科夫'}
const trinityAddMode={MINUTE_ADD:'新分钟信号加仓',MA10_ADD:'日线收敛后等分钟确认加仓',NONE:'只做一手'}
const canWrite=computed(()=>hasPermission('paper.write'))
const canStart=computed(()=>canWrite.value&&!working.value&&!loading.value&&!props.busy&&!active.value&&props.session.multiInstrument&&(!isTrinity.value||trinitySupported.value&&!props.trinityLaunchMissing))
const statuses:Record<string,string>={STARTING:'启动中',REFRESHING:'正在拉取最新数据',RUNNING:'后台运行',WAITING:'等待开市 / 行情',WARMING:'等待指标',PAUSED:'账户已暂停',ERROR:'暂未执行',FORBIDDEN:'权限失效已停止',STOPPED:'已停止'}
const actions:Record<string,string>={DATA_READY:'数据更新',BUY:'开多',SELL:'开空',ADD_LONG:'多头加仓',FLATTEN:'平仓',HOLD:'等待',WARMING:'指标准备中'}
let timer:number|undefined,generation=0,disposed=false
watch(()=>[active.value?.id,loading.value],()=>emit('locked',loading.value||!!active.value))
async function refresh(){
 const id=props.session.id,ticket=++generation
 window.clearTimeout(timer);loading.value=!state.value.runs.length
 try {const result=await api.paperAutomation(id);if(ticket!==generation||disposed)return;state.value=result;error.value='';emit('refresh')}
 catch(e){if(ticket===generation&&!disposed)error.value=e instanceof Error?e.message:'运行状态暂不可用'}
 finally{if(ticket===generation&&!disposed){loading.value=false;timer=window.setTimeout(()=>void refresh(),5000)}}
}
watch(()=>props.session.id,()=>{state.value={runs:[],events:[]};void refresh()},{immediate:true})
watch(()=>props.session.currentContract,()=>emit('locked',loading.value||!!active.value))
watch(()=>form.value.strategy,async (strategy,previous)=>{
 const optionalProtection=['MA20_MACD','BUY_AND_HOLD',TRINITY_STRATEGY_ID].includes(strategy)
 form.value.stopLossTicks=strategy==='MA20_MACD'?10:0
 form.value.stopLossAtr=optionalProtection?0:2
 form.value.takeProfitAtr=optionalProtection?0:3
 if(strategy===TRINITY_STRATEGY_ID)form.value.intradayOnly=false
 else if(previous===TRINITY_STRATEGY_ID)form.value.intradayOnly=true
 delete form.value.workflowVersionId
 if(strategy==='WORKFLOW')try{versions.value=await workflowsApi.versions()}catch(e){error.value=e instanceof Error?e.message:'工作流读取失败'}
})
watch(()=>props.initialStrategy,(strategy,previous)=>{if(strategy||previous)form.value.strategy=strategy??'MA20_MACD'},{immediate:true})
async function start(){
 if(!canStart.value)return
 const id=props.session.id,contract=props.session.currentContract;working.value=true;error.value='';const ticket=++generation;window.clearTimeout(timer)
 const payload:StartPaperAutomation={...form.value,contract}
 if(isTrinity.value)Object.assign(payload,{lots:trinityLots.value,intradayOnly:false,trinity:{...trinity.value}})
 try{const result=await api.startPaperAutomation(id,payload);if(disposed||ticket!==generation||props.session.id!==id)return;state.value=result;emit('locked',!!active.value);emit('refresh')}
 catch(e){error.value=e instanceof Error?e.message:'启动失败'}
 finally{working.value=false;if(!disposed&&ticket===generation)timer=window.setTimeout(()=>void refresh(),5000)}
}
async function stop(run:string){
 if(!canWrite.value||working.value||props.busy)return
 const id=props.session.id;working.value=true;error.value='';const ticket=++generation;window.clearTimeout(timer)
 try{const result=await api.stopPaperAutomation(id,run);if(disposed||ticket!==generation||props.session.id!==id)return;state.value=result;emit('locked',!!active.value);emit('refresh')}
 catch(e){error.value=e instanceof Error?e.message:'停止失败'}
 finally{working.value=false;if(!disposed&&ticket===generation)timer=window.setTimeout(()=>void refresh(),5000)}
}
onUnmounted(()=>{disposed=true;++generation;window.clearTimeout(timer);emit('locked',false)})
</script>
<template>
 <section id="paper-automation" class="automation-panel" aria-label="量化自动执行">
  <header><div><small>STRATEGY AUTOMATION</small><h3>量化自动执行 · {{session.currentContract}}</h3></div><span :class="{running:active}">{{lastRun?statuses[lastRun.status]??lastRun.status:'未启动'}}</span></header>
  <p>每个合约可选择一份策略，共用账户资金。点击启动后由后台运行，关闭网页仍继续；已有手动持仓和挂单需先处理。</p>
  <p>每次启动先从天勤重新拉取该合约的日线与分钟线，更新完成前不允许开新仓。服务重启后也会先更新数据。</p>
  <p v-if="!session.multiInstrument">请先在上方添加或切换品种，启用多品种账户。</p>
  <p v-if="!canWrite">当前账号仅可查看执行状态。</p>
  <form v-if="!active" @submit.prevent="start"><fieldset :disabled="!canWrite||working||busy||!!active||!session.multiInstrument">
   <label>执行策略<select v-model="form.strategy" aria-label="自动执行策略"><option v-for="s in strategies" :key="s.id" :value="s.id">{{s.name}}</option></select></label>
   <label v-if="form.strategy==='WORKFLOW'">冻结发布版本<select v-model="form.workflowVersionId" aria-label="自动执行工作流" required><option :value="undefined">选择已发布版本</option><option v-for="v in versions.filter(v=>v.engineVersion==='workflow-daily-v1')" :key="v.id" :value="v.id">{{v.name}} · v{{v.version}} · {{v.lots}}手</option></select></label>
   <label v-else-if="!isTrinity">每次开仓手数<input v-model.number="form.lots" aria-label="自动执行手数" type="number" min="1" max="1000000" required /></label>
   <label>固定止损（跳，0关闭）<input v-model.number="form.stopLossTicks" aria-label="自动止损跳数" type="number" min="0" max="10000" required /></label>
   <template v-if="!['MA20_MACD','WORKFLOW','BUY_AND_HOLD'].includes(form.strategy)"><label>ATR止损倍数<input v-model.number="form.stopLossAtr" type="number" min="0" max="20" step="0.1" /></label><label>ATR止盈倍数（0关闭）<input v-model.number="form.takeProfitAtr" type="number" min="0" max="50" step="0.1" /></label></template>
   <label v-if="!isTrinity" class="intraday"><input v-model="form.intradayOnly" type="checkbox" />日内：收盘前一分钟清仓</label>
   <button type="submit" :disabled="!canStart">启动所选合约策略</button>
  </fieldset></form>
  <p v-if="!active&&form.strategy==='MA20_MACD'" class="rules">按已完成的1分钟线计算MA20，日线MACD(12,26,9)过滤方向；新突破入场，逆向偏离MA20三跳平仓，不设止盈、不立即反手。<RouterLink :to="MA20_MACD_BACKTEST_PATH">历史回测</RouterLink></p>
  <p v-else-if="!active&&isTrinity&&trinityLaunchMissing" role="alert">未找到从编辑器传入的策略参数。<RouterLink to="/strategy/self-developed-trinity">返回编辑器重新选择</RouterLink></p>
  <template v-else-if="!active&&isTrinity">
   <p class="rules">{{selectedTrinity?.name??'内置参数'}} · MA{{trinity.fastPeriod}}／{{trinity.mediumPeriod}}／{{trinity.slowPeriod}} · {{trinity.entryMinutes}} 分钟 · {{trinityConfirmation[trinity.confirmation]}} · {{trinityAddMode[trinity.addMode]}} · 最长等待 {{trinity.waitTradingDays}} 个交易日。</p>
   <p class="rules">首笔 1 手，最多 {{trinityLots}} 手，允许跨日。<RouterLink to="/strategy/self-developed-trinity">编辑参数与回测</RouterLink></p>
   <p v-if="!trinitySupported" role="status">三位一体目前支持玻璃、纯碱、苹果和红枣的实际交割合约，请从上方切换合约。</p>
  </template>
  <p v-else-if="!active" class="rules">内置策略与工作流按已完成日线决策；工作流使用冻结版本的手数及ATR保护参数。</p>
  <p v-if="lastRun&&!active">{{lastRun.message}}</p>
  <article v-for="run in state.runs.filter(r=>r.enabled)" :key="run.id" class="run"><div><strong>{{run.contract}} · {{names[run.strategy]??run.strategy}} · {{run.trinity?'最多 ':''}}{{run.lots}}手</strong><span>{{statuses[run.status]??run.status}}<template v-if="run.checkedAt"> · {{formatTime(run.checkedAt)}}</template></span><p>{{run.message}}</p><small>止损 {{run.stopLossTicks}} 跳 · {{run.intradayOnly?'日内清仓':'允许跨日'}}<template v-if="run.workflow?.name"> · {{run.workflow.name}} v{{run.workflow.version}}</template><template v-if="run.trinity"> · MA{{run.trinity.fastPeriod}}／{{run.trinity.mediumPeriod}}／{{run.trinity.slowPeriod}} · {{run.trinity.entryMinutes}} 分钟 · {{trinityConfirmation[run.trinity.confirmation]}} · {{trinityAddMode[run.trinity.addMode]}}</template></small></div><button type="button" :disabled="!canWrite||working||busy" @click="stop(run.id)">停止 {{run.contract}} 策略</button></article>
  <p>停止会撤销该策略挂单，已有持仓保留，可改为手动平仓。断线、休市或行情过期时不成交；止损和收盘清仓也需要有效行情。</p>
  <p v-for="run in state.runs.filter(r=>r.enabled&&r.dataRefresh?.completedAt)" :key="'data-'+run.id" class="rules" :aria-label="run.contract+' 数据更新回执'">
   {{run.contract}} · {{run.status==='REFRESHING'?'上次数据更新':'最新数据已拉取'}}：日线至 {{formatTradingDate(run.dataRefresh?.latestDailyTime)}}（{{run.dataRefresh?.dailyCount}}根），1分钟线至 {{formatTime(run.dataRefresh?.latestMinuteTime)}}（{{run.dataRefresh?.minuteCount}}根）；拉取完成 {{formatTime(run.dataRefresh?.completedAt)}}。
  </p>
  <p v-if="error" role="alert">{{error}} <button type="button" :disabled="working" @click="refresh">刷新状态</button></p>
  <details><summary>策略决策记录 · 最近50条</summary><div class="events"><table><thead><tr><th>时间 / 合约</th><th>动作</th><th>执行状态</th><th>依据</th></tr></thead><tbody><tr v-for="event in state.events" :key="event.id"><td>{{formatTime(event.signalTime)}} · {{event.contract}}</td><td>{{actions[event.signal]??event.signal}}</td><td>{{event.status}}</td><td>{{event.reason}}</td></tr><tr v-if="!state.events.length"><td colspan="4">启动后显示计算结果及执行原因；当前没有决策记录。</td></tr></tbody></table></div></details>
 </section>
</template>
<style scoped>
.automation-panel{min-width:0;padding:1.1rem 1.25rem;border:1px solid var(--color-line);border-left:3px solid #577c69;border-radius:.75rem;background:#f7faf7}.automation-panel header{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}.automation-panel header small{font-size:.6rem;letter-spacing:.12em;color:#587566}.automation-panel h3{font-size:1rem;margin:.4rem 0}.automation-panel header>span{font-size:.75rem;color:#6b766f}.automation-panel .running{color:#226442;font-weight:600}.automation-panel p{font-size:.71rem;line-height:1.7;color:var(--color-ink-secondary)}fieldset{border:0;padding:0;margin:.8rem 0;display:flex;gap:.8rem;align-items:flex-end;flex-wrap:wrap}.automation-panel label{display:grid;gap:.4rem;font-size:.7rem}.automation-panel input:not([type=checkbox]),select{box-sizing:border-box;padding:.55rem .6rem;max-width:100%;border:1px solid #bfd1c5;border-radius:.4rem;background:white}.automation-panel input[type=number]{width:9rem}.automation-panel button{border:1px solid #a8c4b3;border-radius:.4rem;background:white;color:#28533d;padding:.6rem .8rem;font-size:.7rem;cursor:pointer}.automation-panel button[type=submit]{background:#285a43;color:white}.automation-panel button:disabled{opacity:.45;cursor:default}.intraday{display:flex!important;align-items:center;align-self:center}.run{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:.8rem;margin:.6rem 0;background:white;border:1px solid #cfddd2;border-radius:.45rem}.run strong,.run span,.run small{display:block;font-size:.7rem}.run span{margin-top:.4rem;color:#42715a}.run p{margin:.4rem 0}.events{overflow-x:auto;max-height:20rem}table{width:100%;border-collapse:collapse;font-size:.69rem}th,td{text-align:left;padding:.65rem;border-bottom:1px solid var(--color-line)}th{white-space:nowrap}.automation-panel summary{font-size:.75rem;cursor:pointer}@media(max-width:600px){.automation-panel{padding:.85rem}fieldset>label{width:100%}.automation-panel input:not([type=checkbox]),select{width:100%}.run{align-items:flex-start;flex-direction:column}.run button{width:100%}}
</style>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { ArrowRight, Calculator, ClipboardList, Download, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import {useExperience} from '../composables/useExperience'
import { api } from '../services/api'
import type { PlanRequest, ResearchContext, ResearchMode, ResearchPlan } from '../types/research'
import { formatNumber, formatTime } from '../utils/format'
import { journalEntry, readJournal, writeJournal, type JournalEntry } from '../utils/planJournal'

const {isSimple}=useExperience()
const props=defineProps<{symbol:string;initialTab?:'PLAN'|'JOURNAL'}>()
const context=ref<ResearchContext|null>(null)
const contextError=ref(''); const planError=ref(''); const loading=ref(false); const working=ref(false)
const tab=ref<'PLAN'|'JOURNAL'>(props.initialTab??'PLAN'); const plan=ref<ResearchPlan|null>(null)
let savedMode: ResearchMode='EMPIRICAL'
try { if(localStorage.getItem('aiquant.research-mode')==='CULTURAL_COMPARE') savedMode='CULTURAL_COMPARE' } catch {}
const mode=ref<ResearchMode>(savedMode)
const form=reactive<PlanRequest>({symbol:props.symbol,mode:'EMPIRICAL',equity:1_000_000,riskPct:1,marginBudgetPct:30,
  maxLeverage:2,dailyLossLimitPct:2,dailyLoss:0,totalRiskLimitPct:3,otherRisk:0,otherMargin:0,otherNotional:0,
  positionSide:'FLAT',existingLots:0,feeRate:.0001,slippageTicks:1,marginRate:.12})
const journal=ref<JournalEntry[]>(readJournal())
const journalError=ref(''); const saveMessage=ref(''); const lastSignature=ref('')
const lastContextSignature=ref('')
let contextGeneration=0; let planGeneration=0
const evidence=computed(()=>context.value?.modes[mode.value])
const currentEntries=computed(()=>journal.value.filter(e=>e.plan.symbol===context.value?.symbol||e.plan.symbol===props.symbol))
const stateLabel:Record<string,string>={LIVE:'交易中 · 行情有效',CLOSED_CACHE:'休市缓存 · 可准备计划',STALE:'行情已过期 · 暂停新增',DISCONNECTED:'行情连接中断',WARMING:'交割合约采集中',UNKNOWN:'交易时段待确认'}
const signalLabel:Record<string,string>={BUY:'偏多研究',SELL:'偏空研究',HOLD:'等待方向确认',UNAVAILABLE:'证据未就绪'}
const actionLabel:Record<string,string>={WAIT:'空仓等待',HOLD_POSITION:'持仓观察',REDUCE:'评估减仓',REVIEW_EXIT:'评估原持仓退出',PREPARE:'仅准备情景',CONDITIONAL_ENTRY:'条件式计划'}
const request=():PlanRequest=>({...form,symbol:props.symbol,mode:mode.value,expectedContract:context.value?.execution.contract??undefined,
  entryPrice:form.entryPrice||undefined,stopPrice:form.stopPrice||undefined,targetPrice:form.targetPrice||undefined})
const contextSignature=()=>JSON.stringify({quote:context.value?.execution.quote,state:context.value?.execution.marketState,contract:context.value?.execution.contract,evidence:evidence.value,model:context.value?.modelVersion})
const dirty=computed(()=>!!plan.value&&(lastSignature.value!==JSON.stringify(request())||lastContextSignature.value!==contextSignature()||!!contextError.value))
const money=(n:number|null|undefined)=>n==null?'—':`¥${formatNumber(n,2)}`

async function refresh() {
  const generation=++contextGeneration; const symbol=props.symbol
  loading.value=true
  try { const result=await api.researchContext(symbol); if(generation===contextGeneration&&symbol===props.symbol){if(!context.value||result.execution.checkedAt>=context.value.execution.checkedAt)context.value=result;contextError.value=''} }
  catch(e){if(generation===contextGeneration) contextError.value=e instanceof Error?e.message:'研究资料暂不可用'}
  finally{if(generation===contextGeneration)loading.value=false}
}
async function calculate() {
  const generation=++planGeneration; const body=request();const signature=JSON.stringify(body)
  working.value=true;planError.value='';saveMessage.value=''
  try { const result=await api.researchPlan(body);if(generation===planGeneration&&signature===JSON.stringify(request())){if(result.researchContext)context.value=result.researchContext;plan.value=result;lastSignature.value=signature;lastContextSignature.value=contextSignature()} }
  catch(e){if(generation===planGeneration)planError.value=e instanceof Error?e.message:'风险核算失败'}
  finally{if(generation===planGeneration)working.value=false}
}
function persist(rows:JournalEntry[]) { try{writeJournal(rows);journal.value=rows;journalError.value='';return true}catch{journalError.value='本机保存失败，请导出计划备份';return false} }
function savePlan(){if(!plan.value||dirty.value)return;if(journal.value.some(e=>e.id===plan.value!.planId)){saveMessage.value='此计划已保存，原有复盘记录保持不变';return}const entry=journalEntry(plan.value);if(persist([entry,...journal.value]))saveMessage.value='计划快照已保存到本机复盘日志'}
function saveReview(entry:JournalEntry){if(persist([...journal.value]))saveMessage.value=`${entry.plan.contract} 复盘记录已保存`}
function download(){const blob=new Blob([JSON.stringify(journal.value,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`AI-QUANT-交易日志-${new Date().toISOString().slice(0,10)}.json`;link.click();URL.revokeObjectURL(url)}
function sideChanged(){form.existingLots=form.positionSide==='FLAT'?0:Math.max(1,form.existingLots);form.stopPrice=undefined;form.targetPrice=undefined}
function setMarginRate(event:Event){form.marginRate=Number((event.target as HTMLInputElement).value)/100}
watch(mode,value=>{try{localStorage.setItem('aiquant.research-mode',value)}catch{};planError.value='';saveMessage.value=''})
watch(()=>props.initialTab,value=>{if(value)tab.value=value})
watch(()=>props.symbol,()=>{contextGeneration++;planGeneration++;working.value=false;context.value=null;plan.value=null;planError.value='';form.entryPrice=undefined;form.stopPrice=undefined;form.targetPrice=undefined;form.positionSide='FLAT';form.existingLots=0;void refresh()},{immediate:true})
const timer=window.setInterval(()=>{if(!loading.value&&!working.value)void refresh()},30000)
onUnmounted(()=>{window.clearInterval(timer);contextGeneration++;planGeneration++})
</script>

<template>
  <section id="trade-plan" class="research-workbench">
    <header class="workbench-header"><div><p>日线研究 / 账户风险试算</p><h2>先定义风险，再形成计划</h2></div><button class="quiet-button" type="button" :disabled="loading" @click="refresh"><RefreshCw :size="15" :class="{spinning:loading}"/>{{ loading?'核验中':'刷新资料' }}</button></header>
    <div class="workbench-tabs" role="tablist" aria-label="交易研究流程"><button type="button" role="tab" :aria-selected="tab==='PLAN'" @click="tab='PLAN'"><Calculator :size="16"/>盘前计划</button><button type="button" role="tab" :aria-selected="tab==='JOURNAL'" @click="tab='JOURNAL'"><ClipboardList :size="16"/>盘后复盘 <small>{{ currentEntries.length }}</small></button></div>
    <p v-if="contextError" class="notice error" role="alert">{{ contextError }}。保留旧资料供查阅，暂停新核算。</p>
    <p v-if="!context&&!contextError" class="notice" role="status">正在核验交割合约、市场状态和证据覆盖…</p>
    <template v-if="tab==='PLAN'&&context&&evidence">
      <div v-if="!isSimple||mode==='CULTURAL_COMPARE'" class="mode-switch" aria-label="研究模式"><button type="button" :aria-pressed="mode==='EMPIRICAL'" @click="mode='EMPIRICAL'">实证研究 <small>默认</small></button><button type="button" :aria-pressed="mode==='CULTURAL_COMPARE'" @click="mode='CULTURAL_COMPARE'">加入文化参考对照（实验性）</button></div>
      <div class="research-brief"><div><span>研究方向</span><strong>{{ signalLabel[evidence.signal]??evidence.signal }}</strong><small>{{ evidence.score.toFixed(1) }} 分 · 研究分数非胜率</small></div><div><span>实际交割合约</span><strong>{{ context.execution.contract??'采集中' }}</strong><small>最新观测 {{ formatNumber(context.execution.quote?.price) }}</small></div><div><span>实证证据覆盖</span><strong>{{ Math.round(evidence.empiricalCoverage*100) }}%</strong><small>{{ evidence.availableDimensions }}/{{ evidence.totalDimensions }} 维可用</small></div><div><span>交易状态</span><strong class="state-text">{{ stateLabel[context.execution.marketState]??'待核验' }}</strong><small>{{ formatTime(context.execution.quote?.dataTimestamp) }}</small></div></div>
      <p class="mode-explanation">{{ mode==='EMPIRICAL'?'仅使用可用实证维度，文化参考不参与本计划方向与仓位。':`文化参考在本次对照中的实际权重为 ${(evidence.culturalEffectiveWeight*100).toFixed(1)}%，其市场预测增益尚未验证。` }} {{ context.dimensionNote }}</p>
      <p v-if="context.execution.quote?.priceBasis==='COMPLETED_DAILY_CLOSE'" class="notice">休市价格基准：已完成的交割合约日线收盘价，日期见上方；当前没有有效最新成交价，仅供准备情景。</p>
      <p v-if="evidence.missing.length" class="missing-evidence">缺失证据：{{ evidence.missing.join('、') }}。不补造分数。</p>
      <div class="plan-layout">
        <form class="risk-form" @submit.prevent="calculate">
          <div class="section-heading"><ShieldCheck :size="17"/><h3>账户风险参数</h3><span>手动情景 · 默认值为示例</span></div>
          <div class="form-grid">
            <label>账户净值（元）<input v-model.number="form.equity" name="equity" type="number" min="1" max="1000000000000" step="any" required /></label>
            <label>单笔风险上限（%）<input v-model.number="form.riskPct" name="riskPct" type="number" min="0.01" max="100" step="any" required /></label>
            <label>本合约持仓状态<select v-model="form.positionSide" name="positionSide" @change="sideChanged"><option value="FLAT">空仓</option><option value="LONG">持有多单</option><option value="SHORT">持有空单</option></select></label>
            <label>已有手数<input v-model.number="form.existingLots" name="existingLots" type="number" :min="form.positionSide==='FLAT'?0:1" max="1000000" step="1" :disabled="form.positionSide==='FLAT'" required /></label>
            <label>情景入场 / 持仓标记价<input v-model.number="form.entryPrice" name="entryPrice" type="number" min="0.0001" step="any" placeholder="留空用交割合约最新价" /></label>
            <label>保护价<input v-model.number="form.stopPrice" name="stopPrice" type="number" min="0.0001" step="any" placeholder="留空按方向估算 2 ATR" /></label>
          </div>
          <details class="advanced"><summary>保证金、当日亏损与其他持仓约束</summary><div class="form-grid">
            <label>保证金占用上限（%）<input v-model.number="form.marginBudgetPct" name="marginBudgetPct" type="number" min="0.1" max="100" step="any" required /></label>
            <label>名义杠杆上限（倍）<input v-model.number="form.maxLeverage" name="maxLeverage" type="number" min="0.1" max="20" step="any" required /></label>
            <label>估算保证金率下限（%）<input :value="form.marginRate*100" name="marginRate" type="number" min="0.1" max="100" step="any" required @input="setMarginRate" /></label>
            <label>单日亏损限额（%）<input v-model.number="form.dailyLossLimitPct" name="dailyLossLimitPct" type="number" min="0.01" max="100" step="any" required /></label>
            <label>当日已亏损（元）<input v-model.number="form.dailyLoss" name="dailyLoss" type="number" min="0" step="any" required /></label>
            <label>账户保护风险上限（%）<input v-model.number="form.totalRiskLimitPct" name="totalRiskLimitPct" type="number" min="0.01" max="100" step="any" required /></label>
            <label>其他持仓保护风险（元）<input v-model.number="form.otherRisk" name="otherRisk" type="number" min="0" step="any" required /></label>
            <label>其他持仓保证金（元）<input v-model.number="form.otherMargin" name="otherMargin" type="number" min="0" step="any" required /></label>
            <label>其他持仓名义敞口（元）<input v-model.number="form.otherNotional" name="otherNotional" type="number" min="0" step="any" required /></label>
            <label>情景目标价<input v-model.number="form.targetPrice" name="targetPrice" type="number" min="0.0001" step="any" placeholder="留空按保护距离 2.5 倍估算" /></label>
            <label>手续费率（小数）<input v-model.number="form.feeRate" name="feeRate" type="number" min="0" max="0.01" step="any" required /></label>
            <label>单边不利滑点（跳）<input v-model.number="form.slippageTicks" name="slippageTicks" type="number" min="0" max="100" step="any" required /></label>
          </div><p>“其他持仓”不包含本合约；总风险按所填保护风险相加，不假设相关品种可以自动抵消。</p></details>
          <button type="submit" class="calculate-button" :disabled="working||!context.execution.quote||!!contextError"><Calculator :size="17"/>{{ working?'核算中…':'核算风险与手数' }}<ArrowRight :size="16"/></button>
          <p class="form-note">手数取风险预算、保证金和名义敞口约束中的最小整数；不会提交交易委托。</p>
          <p class="form-note">当前波动尺度：{{ context.atrBasis }} · {{ formatNumber(context.atr) }}。可直接填写并确认保护价。</p>
        </form>
        <aside class="plan-output" aria-live="polite">
          <p v-if="planError" class="notice error" role="alert">{{ planError }}</p>
          <template v-if="plan">
            <p v-if="dirty" class="notice">资料或输入已改变。以下是旧情景，请重新核算后保存。</p>
            <span class="output-eyebrow">{{ plan.contract }} / {{ plan.scenarioDirection==='LONG'?'多头情景':plan.scenarioDirection==='SHORT'?'空头情景':'等待情景' }}</span>
            <h3>{{ actionLabel[plan.action]??plan.action }}</h3><p>{{ plan.actionMessage }}</p>
            <div class="lot-output"><strong>{{ plan.maxLots }}</strong><span>手<br/>风险可承受的总手数上限</span></div>
            <dl class="output-metrics"><div><dt>本次新增计划</dt><dd>{{ plan.newLots }} 手</dd></div><div><dt>保护价触发损失估算</dt><dd>{{ money(plan.plannedLoss) }} / {{ plan.lossPct }}%</dd></div><div><dt>保证金占用估算</dt><dd>{{ money(plan.marginRequired) }} / {{ plan.marginPct }}%</dd></div><div><dt>含其他持仓名义杠杆</dt><dd>{{ plan.notionalLeverage }} 倍</dd></div><div><dt>单手风险 / 可用预算</dt><dd>{{ money(plan.riskPerLot) }} / {{ money(plan.riskBudget) }}</dd></div><div><dt>本合约已有持仓风险</dt><dd>{{ money(plan.existingPositionRisk) }}</dd></div></dl>
            <div class="price-boundaries"><span>情景入场 <b>{{ formatNumber(plan.entryPrice) }}</b></span><span>保护价 <b>{{ plan.stopPrice==null?'待定':formatNumber(plan.stopPrice) }}</b></span><span>情景目标 <b>{{ plan.targetPrice==null?'待定':formatNumber(plan.targetPrice) }}</b></span></div>
            <p class="plan-condition"><b>触发：</b>{{ plan.trigger }}</p><p class="plan-condition"><b>失效：</b>{{ plan.invalidation }}</p>
            <ul v-if="plan.gates.length" class="gate-list"><li v-for="gate in plan.gates" :key="gate">{{ gate }}</li></ul>
            <button class="save-plan" type="button" :disabled="dirty||working" @click="savePlan"><ClipboardList :size="16"/>保存计划快照</button>
            <details class="assumptions"><summary>查看估算假设、有效期与来源</summary><p>{{ plan.holdingHorizon }}</p><p>{{ plan.validity }}</p><ul><li v-for="text in plan.assumptions" :key="text">{{ text }}</li></ul><p>模型 {{ plan.modelVersion }} · 行情 {{ formatTime(plan.dataTimestamp) }}</p></details>
          </template>
          <div v-else class="output-empty"><ShieldCheck :size="30"/><h3>先填写风险边界</h3><p>填写账户情景后，查看整数手数、保证金与保护价触发损失。休市时可准备计划，新增动作保持为 0。</p><p>HOLD：空仓等待；已有持仓进入观察；超出风险上限则提示减仓。</p></div>
        </aside>
      </div>
      <div class="contract-events"><div><strong>合约与事件</strong><span v-if="context.execution.quote">每手乘数 {{ context.execution.quote.volumeMultiple??'—' }} · 最小价位 {{ context.execution.quote.priceTick??'—' }} · 当前每手保证金 {{ money(context.execution.quote.marginPerLot) }}</span></div><p v-for="event in context.events" :key="event.type" :class="{urgent:event.urgent}">{{ event.label }}</p><p>到期日不等于个人账户可持有至交割的日期；提前平仓与加收保证金以期货公司规定为准。</p></div>
    </template>
    <div v-if="tab==='JOURNAL'" class="journal">
      <div class="journal-toolbar"><div><h3>计划与实际表现对照</h3><p>本机保存；列表显示最近 100 条，跨设备未同步。原始计划快照不随复盘修改。</p></div><button type="button" class="quiet-button" :disabled="!journal.length" @click="download"><Download :size="15"/>导出全部日志</button></div>
      <p v-if="!currentEntries.length" class="notice">当前品种还没有计划。先核算风险，再保存第一条计划快照。</p>
      <article v-for="entry in currentEntries.slice(0,100)" :key="entry.id" class="journal-entry"><header><strong>{{ entry.plan.contract }} · {{ actionLabel[entry.plan.action]??entry.plan.action }}</strong><span>{{ formatTime(entry.savedAt) }}</span></header><p>{{ entry.plan.mode==='EMPIRICAL'?'实证研究':'文化参考对照' }} · 风险上限 {{ entry.plan.maxLots }} 手 · 保护价 {{ entry.plan.stopPrice??'待定' }} · 预算内损失估算 {{ money(entry.plan.plannedLoss) }}</p><div class="review-fields"><label>执行情况<select v-model="entry.status"><option value="PLANNED">仅计划</option><option value="EXECUTED">已执行</option><option value="ABANDONED">已放弃</option></select></label><label>实际净盈亏（元，可空）<input v-model.number="entry.actualPnl" type="number" step="0.01"/></label><label class="review-note">执行偏差与复盘<textarea v-model="entry.notes" maxlength="2000" placeholder="记录未按计划执行、滑点、止损和数据变化等原因"/></label></div><button type="button" class="quiet-button" @click="saveReview(entry)">保存复盘</button><details><summary>查看冻结的计划参数</summary><p>{{ entry.plan.modelVersion }} · {{ formatTime(entry.plan.dataTimestamp) }} · 账户净值 {{ money(entry.plan.inputs.equity) }} · 单笔风险 {{ entry.plan.inputs.riskPct }}%</p><p>{{ entry.plan.trigger }}</p><p>{{ entry.plan.invalidation }}</p></details></article>
    </div>
    <p v-if="saveMessage" class="saved-message" role="status">{{ saveMessage }}</p><p v-if="journalError" class="notice error" role="alert">{{ journalError }}</p>
  </section>
</template>

<style scoped>
.research-workbench{border:1px solid var(--color-line);border-radius:1.3rem;background:var(--color-surface);overflow:hidden;scroll-margin-top:1rem}.workbench-header{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1.5rem 1.75rem;background:#1c2429;color:#fff}.workbench-header p{font-size:.67rem;letter-spacing:.08em;color:#9cb2bf;margin:0 0 .5rem}.workbench-header h2{font-size:1.35rem;margin:0}.quiet-button,.save-plan{display:inline-flex;align-items:center;justify-content:center;gap:.45rem;border:1px solid var(--color-line);border-radius:.55rem;background:transparent;padding:.6rem .8rem;font-size:.72rem;color:var(--color-accent);cursor:pointer}.workbench-header .quiet-button{color:#e1ebf0;border-color:#52616b}.workbench-tabs{display:flex;gap:1.5rem;border-bottom:1px solid var(--color-line);padding:0 1.75rem}.workbench-tabs button{display:flex;align-items:center;gap:.5rem;padding:1rem 0;border:0;border-bottom:2px solid transparent;background:none;font-size:.78rem;color:var(--color-ink-secondary);cursor:pointer}.workbench-tabs button[aria-selected=true]{border-bottom-color:var(--color-accent);color:var(--color-accent);font-weight:700}.mode-switch{display:flex;gap:.5rem;padding:1.25rem 1.75rem .5rem}.mode-switch button{padding:.6rem .8rem;border:1px solid var(--color-line);border-radius:.5rem;background:transparent;color:var(--color-ink-secondary);cursor:pointer;font-size:.73rem}.mode-switch button[aria-pressed=true]{background:var(--color-accent-soft);border-color:var(--color-accent);color:var(--color-accent);font-weight:650}.mode-switch small{font-size:.6rem;margin-left:.35rem}.research-brief{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem;padding:1.25rem 1.75rem}.research-brief>div{display:grid;gap:.5rem}.research-brief span{font-size:.67rem;color:var(--color-ink-secondary)}.research-brief strong{font:600 1.15rem var(--font-sans)}.research-brief .state-text{font-size:.83rem}.research-brief small{font-size:.63rem;color:var(--color-ink-tertiary)}.mode-explanation,.missing-evidence{margin:0 1.75rem .85rem;font-size:.7rem;line-height:1.65;color:var(--color-ink-secondary)}.missing-evidence{color:var(--color-warning)}.plan-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);border-top:1px solid var(--color-line)}.risk-form,.plan-output{padding:1.5rem 1.75rem;min-width:0}.risk-form{border-right:1px solid var(--color-line)}.section-heading{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;color:var(--color-accent);margin-bottom:1.1rem}.section-heading h3{margin:0;font-size:.85rem;color:var(--color-ink)}.section-heading span{font-size:.64rem;color:var(--color-ink-tertiary)}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem .8rem}label{display:grid;gap:.4rem;font-size:.69rem;color:var(--color-ink-secondary)}input,select,textarea{box-sizing:border-box;min-width:0;width:100%;border:1px solid var(--color-line-strong);border-radius:.5rem;background:var(--color-surface-raised);padding:.7rem .65rem;color:var(--color-ink);font:500 .78rem var(--font-numeric)}input:focus,select:focus,textarea:focus{outline:2px solid var(--color-accent);outline-offset:2px}input:disabled{background:var(--color-canvas);color:var(--color-ink-tertiary)}input::placeholder{font:400 .64rem var(--font-sans)}.advanced{margin:1.15rem 0}.advanced summary,.assumptions summary,.journal summary{font-size:.7rem;color:var(--color-accent);cursor:pointer;line-height:1.7}.advanced .form-grid{margin-top:1rem}.advanced p,.form-note,.assumptions,.contract-events p{font-size:.66rem;line-height:1.75;color:var(--color-ink-secondary)}.calculate-button{display:flex;align-items:center;justify-content:center;gap:.65rem;width:100%;border:0;border-radius:.6rem;padding:.9rem;background:var(--color-accent);color:#fff;font-size:.8rem;font-weight:650;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}.plan-output{background:#f1f5f5}.plan-output h3{font-size:1.3rem;margin:.55rem 0}.plan-output>p{font-size:.74rem;line-height:1.7;color:var(--color-ink-secondary)}.output-eyebrow{font:600 .67rem var(--font-numeric);color:var(--color-accent)}.lot-output{display:flex;align-items:center;gap:1rem;margin:1.25rem 0}.lot-output strong{font:500 3.5rem var(--font-display);line-height:1}.lot-output span{font-size:.68rem;line-height:1.7;color:var(--color-ink-secondary)}.output-metrics{margin:0}.output-metrics>div{display:flex;justify-content:space-between;gap:.6rem;padding:.7rem 0;border-top:1px solid #d8e1e1;font-size:.69rem}.output-metrics dt{color:var(--color-ink-secondary)}.output-metrics dd{margin:0;text-align:right;font-family:var(--font-numeric)}.price-boundaries{display:flex;flex-wrap:wrap;gap:.8rem;padding:1rem 0;font-size:.66rem}.price-boundaries b{display:block;font:600 .9rem var(--font-numeric);margin-top:.35rem}.plan-condition{font-size:.7rem;line-height:1.7}.gate-list{margin:1rem 0;padding:.7rem .7rem .7rem 1.8rem;background:var(--color-warning-soft);border-radius:.6rem;font-size:.7rem;color:var(--color-warning);line-height:1.8}.save-plan{background:#fff;margin:.4rem 0 .85rem}.assumptions li{margin:.4rem 0}.output-empty{display:grid;align-content:center;min-height:24rem;color:var(--color-accent)}.output-empty p{font-size:.75rem;line-height:1.8;color:var(--color-ink-secondary)}.contract-events{border-top:1px solid var(--color-line);padding:1.25rem 1.75rem}.contract-events>div{display:flex;gap:1rem;flex-wrap:wrap;font-size:.7rem}.contract-events span{color:var(--color-ink-secondary)}.contract-events .urgent{color:var(--color-warning);font-weight:650}.notice{margin:1rem 1.75rem;padding:.85rem 1rem;background:var(--color-warning-soft);color:var(--color-warning);border-radius:.5rem;font-size:.73rem;line-height:1.7}.plan-output .notice{margin:0 0 1rem}.error{background:#fff0ee;color:#a42e25}.saved-message{padding:0 1.75rem 1rem;color:var(--color-success);font-size:.73rem}.journal{padding:1.5rem 1.75rem}.journal-toolbar{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem}.journal h3{font-size:.9rem;margin:0}.journal p{font-size:.7rem;line-height:1.7;color:var(--color-ink-secondary)}.journal-entry{border:1px solid var(--color-line);border-radius:.75rem;padding:1rem;margin-top:1rem}.journal-entry header{display:flex;justify-content:space-between;gap:1rem;font-size:.75rem}.journal-entry header span{font-size:.65rem;color:var(--color-ink-tertiary)}.review-fields{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin:1rem 0}.review-note{grid-column:1/-1}.review-note textarea{font:400 .75rem var(--font-sans);resize:vertical;min-height:4rem}.spinning{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1050px){.plan-layout{grid-template-columns:1fr}.risk-form{border-right:0;border-bottom:1px solid var(--color-line)}.research-brief{grid-template-columns:1fr 1fr}.output-empty{min-height:10rem}}@media(max-width:600px){.workbench-header,.risk-form,.plan-output,.journal{padding:1.2rem}.workbench-header h2{font-size:1.1rem}.workbench-tabs{padding:0 1.2rem}.mode-switch{padding-left:1.2rem;padding-right:1.2rem}.research-brief{padding:1.2rem}.mode-explanation,.missing-evidence{margin-left:1.2rem;margin-right:1.2rem}.form-grid{grid-template-columns:1fr}.journal-toolbar,.journal-entry header{flex-direction:column}.contract-events{padding:1.2rem}}
</style>
<style scoped>
.research-workbench,.journal-entry,.review-fields>label{min-width:0}
.review-fields{grid-template-columns:repeat(2,minmax(0,1fr))}
@media(max-width:600px){.review-fields{grid-template-columns:minmax(0,1fr)}.workbench-header{flex-wrap:wrap}}
</style>

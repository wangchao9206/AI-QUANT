<script setup lang="ts">
import {RouterLink} from 'vue-router'
import {ref,onUnmounted} from 'vue'
import {decisionsApi,type ResearchSource} from '../services/decisions'
import {currentScope} from '../utils/storageScope'
import type {ResearchPlan} from '../types/research'
import type {JournalEntry} from '../utils/planJournal'
import {instrumentLabel} from '../utils/instrumentNames'
import {formatTime,formatNumber} from '../utils/format'
defineProps<{sources:ResearchSource[];caseId:string}>()
const plan=(s:ResearchSource)=>s.kind==='LOCAL_IMPORT'?(s.snapshot as JournalEntry).plan:s.snapshot as ResearchPlan
const legacy=(s:ResearchSource)=>s.snapshot as JournalEntry
const actions:Record<string,string>={WAIT:'空仓等待',HOLD_POSITION:'持仓观察',REDUCE:'评估减仓',REVIEW_EXIT:'评估原持仓退出',PREPARE:'仅准备情景',CONDITIONAL_ENTRY:'条件式计划'}
const error=ref(''),exporting=ref('');let alive=true
async function download(s:ResearchSource){
 if(exporting.value)return;exporting.value=s.id;error.value='';const scope=currentScope()
 try{let raw=JSON.stringify(s.snapshot,null,2);if(s.kind==='LOCAL_IMPORT'){const saved=await decisionsApi.researchSource(s.id);if(!saved.rawPayload)throw new Error('此记录没有保存导入原文。');raw=saved.rawPayload}if(!alive||scope!==currentScope())return
 const blob=new Blob([raw],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`AI-QUANT-${s.kind}-${s.id}.json`;link.click();URL.revokeObjectURL(url)
 }catch(e){if(alive&&scope===currentScope())error.value=e instanceof Error?e.message:'导出失败，请重试。'}finally{if(alive)exporting.value=''}
}
onUnmounted(()=>{alive=false})
</script>
<template>
 <section v-if="sources.length" class="card research-sources" aria-label="研究原文与导入来源">
  <h3>研究原文与来源版本</h3><p>原核算与手工计划分别保存；附加新核算不会覆盖原计划或已有模拟关联。原模型分数不是胜率，来源确认也不代表盈利验证。</p><p v-if="error" role="alert">{{error}}</p>
  <article v-for="s in sources" :key="s.id"><header><strong>{{s.kind==='SERVER_CALC'?'服务端当次核算原文':'本机自报 · 未经服务端核验'}}</strong><time>服务端记录 {{formatTime(s.createdAt)}}</time></header><p>{{instrumentLabel(plan(s).contract)}} · {{plan(s).mode==='EMPIRICAL'?'实证研究':'文化参考对照'}} · 模型 {{plan(s).modelVersion}}</p><p>原动作：<strong>{{actions[plan(s).action]??plan(s).action}}</strong> · {{plan(s).actionMessage}}</p><p>原资料时点 {{formatTime(plan(s).dataTimestamp)}} · 原核算时点 {{formatTime(plan(s).createdAt)}}</p><p>参考分 {{plan(s).modeEvidence?.score??'未提供'}}（非胜率） · 原新增 {{plan(s).newLots}} 手 / 原减仓 {{plan(s).reduceLots}} 手</p><p>{{plan(s).trigger}}</p><p>{{plan(s).invalidation}}</p><ul><li v-for="gate in plan(s).gates??[]" :key="gate">{{gate}}</li></ul>
   <div v-if="s.kind==='LOCAL_IMPORT'" class="unverified"><p>原本机保存时间 {{formatTime(legacy(s).savedAt)}} · 自报状态 {{legacy(s).status}} · 自报净盈亏 {{legacy(s).actualPnl==null?'未填写':formatNumber(legacy(s).actualPnl)}} 元。上述内容不构成模拟账本的成交或收益事实。</p><p class="notes">{{legacy(s).notes}}</p></div>
   <p class="fingerprint">来源指纹：{{s.sourceHash}}</p><RouterLink :to="{path:'/strategy/'+encodeURIComponent(plan(s).symbol),query:{case:caseId},hash:'#trade-plan'}">回研究工作台，为同一档案重新核算 ↗</RouterLink><button type="button" :disabled="!!exporting" @click="download(s)">{{s.kind==='LOCAL_IMPORT'?'下载本次导入原文':'导出研究快照'}}</button><details><summary>查看冻结的原始研究与复盘内容</summary><pre>{{JSON.stringify(s.snapshot,null,2)}}</pre></details>
  </article>
 </section>
</template>
<style scoped>
.card{padding:1.25rem;border:1px solid var(--color-line);border-radius:1rem;background:var(--color-surface);min-width:0}.card h3{margin:0 0 1rem;font-size:1rem}.card p,.card li,.card a,.card summary{font-size:.76rem;line-height:1.8;color:var(--color-ink-secondary)}article{border-top:1px solid var(--color-line);padding:1rem 0}header{display:flex;gap:.8rem;justify-content:space-between;flex-wrap:wrap;font-size:.8rem}time{font-size:.7rem}.notes,pre{white-space:pre-wrap;overflow-wrap:anywhere}.fingerprint{overflow-wrap:anywhere}.unverified{padding:.7rem;background:var(--color-warning-soft);border-radius:.5rem}pre{font-size:.7rem;max-height:25rem;overflow:auto}summary{cursor:pointer;margin-top:.8rem}
</style>

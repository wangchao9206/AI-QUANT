<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import type {MentorOperation,MentorProfile,MentorSource} from '../types/mentors'
import Pagination from './Pagination.vue'
import {usePagination} from '../composables/usePagination'
const props=defineProps<{records:MentorOperation[];profiles:MentorProfile[];sources:MentorSource[];preferredProfileId?:string;version:string}>()
const emit=defineEmits<{profile:[id:string];account:[id:string]}>()
const person=ref(''),evidence=ref(''),action=ref(''),search=ref('')
watch(()=>props.preferredProfileId,id=>{person.value=id??''},{immediate:true})
const personMap=computed(()=>new Map(props.profiles.map(p=>[p.id,p])))
const sourceMap=computed(()=>new Map(props.sources.map(s=>[s.id,s])))
const actions:Record<MentorOperation['action'],string>={OPEN:'建立头寸',CLOSE:'平仓退出',ADD:'增加头寸',REDUCE:'减仓 / 分批退出',HOLD:'持有头寸',REVERSE:'反手',POSITION:'持仓事实'}
const directions={LONG:'多头',SHORT:'空头',UNSPECIFIED:'方向未披露'}
const owners={INDIVIDUAL:'本人操作回忆',GUIDED_TEAM:'团队 / 操作指导账户',CONTROLLED_COMPANIES:'控制公司 / 合并头寸'}
const precision={DAY:'具体日期',MONTH:'月份范围',YEAR:'年度 / 阶段',INTERVAL:'期间范围',UNSPECIFIED:'原文未给具体日期'}
const filtered=computed(()=>{
  const rows=props.records.filter(r=>(!person.value||r.profileId===person.value)&&(!evidence.value||r.sourceType===evidence.value)&&(!action.value||r.action===action.value)&&(!search.value.trim()||`${r.instrument} ${r.contractCodes.join(' ')} ${r.periodLabel} ${r.summary} ${personMap.value.get(r.profileId)?.name??''}`.includes(search.value.trim())))
  if(person.value)return rows
  const seen=new Set<string>(),first:MentorOperation[]=[],rest:MentorOperation[]=[]
  for(const row of rows){if(seen.has(row.profileId))rest.push(row);else{seen.add(row.profileId);first.push(row)}}
  return [...first,...rest]
})
const {items,page,total}=usePagination(filtered,6,[person,evidence,action,search])
const available=computed(()=>props.profiles.filter(p=>props.records.some(r=>r.profileId===p.id)))
function reset(){person.value='';evidence.value='';action.value='';search.value=''}
function exportRecords(){const ids=new Set(filtered.value.flatMap(r=>r.sourceIds));const data={version:props.version,note:'实盘操作与持仓披露片段；不是逐笔交割单，不自动配对或核算收益。',records:filtered.value,profiles:props.profiles.filter(p=>filtered.value.some(r=>r.profileId===p.id)).map(p=>({id:p.id,name:p.name,identityKind:p.identityKind,identityNotes:p.identityNotes})),sources:props.sources.filter(s=>ids.has(s.id))};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='实盘操作资料.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
</script>
<template>
  <section class="operation-desk">
    <header><div><span class="eyebrow">从已发生的行为开始研究</span><h3>实盘操作记录库</h3></div><button type="button" :disabled="!total" @click="exportRecords">导出筛选结果JSON</button></header>
    <p class="intro">目前 {{records.length}} 条操作与持仓记录，涉及 {{available.length}} 位研究对象。综合展示不同人物，筛选人物后可查看其完整已收录过程。时间、价格和手数保持原文精度；记录条数不是成交笔数，观点、预测和教学示例不计入。</p>
    <div class="filters"><label>人物<select v-model="person" aria-label="筛选操作人物"><option value="">全部有记录人物</option><option v-for="p in profiles" :key="p.id" :value="p.id">{{p.name}} · {{records.filter(r=>r.profileId===p.id).length}} 条</option></select></label><label>证据<select v-model="evidence" aria-label="筛选操作证据"><option value="">全部证据类型</option><option value="REGULATORY_DISCLOSURE">监管原文披露</option><option value="FIRST_PERSON_RECALL">本人操作回忆</option></select></label><label>行为<select v-model="action" aria-label="筛选操作行为"><option value="">全部行为</option><option v-for="(text,key) in actions" :key="key" :value="key">{{text}}</option></select></label><label>检索<input v-model="search" type="search" aria-label="检索操作记录" placeholder="品种、合约、年份…"/></label><button type="button" @click="reset">重置筛选</button></div>
    <p v-if="!total" class="empty">当前筛选没有已收录操作。该人物可能只有赛期账户汇总或背景资料；切换“账户与赛期”可继续核对已取得数据。</p>
    <div class="operation-grid"><article v-for="r in items" :key="r.id" class="operation-card">
      <div class="card-top"><span class="evidence" :class="{official:r.sourceType==='REGULATORY_DISCLOSURE'}">{{r.sourceType==='REGULATORY_DISCLOSURE'?'监管原文披露':'本人操作回忆 · 未独立核验'}}</span><span>{{precision[r.datePrecision]}}</span></div>
      <h4>{{personMap.get(r.profileId)?.name??r.profileId}} <small>{{actions[r.action]}} · {{directions[r.direction]}}</small></h4>
      <p class="period">{{r.periodLabel}} <span> / {{r.market}}</span></p>
      <strong class="instrument">{{r.instrument}}</strong><p v-if="r.contractCodes.length" class="contracts">{{r.contractCodes.join(' · ')}}</p>
      <p class="fact">{{r.summary}}</p>
      <dl><div><dt>披露价格</dt><dd>{{r.priceLabel}}</dd></div><div><dt>披露数量</dt><dd>{{r.quantityLabel}}</dd></div><div><dt>主体口径</dt><dd>{{owners[r.ownerScope]}}</dd></div><div><dt>资料发布</dt><dd>{{r.publishedAt??'原文日期待核'}}</dd></div></dl>
      <div class="reading"><b>研究者解读 · 待验证</b><p>{{r.interpretation}}</p></div>
      <details><summary>核对原文位置与缺失字段</summary><p>{{r.sourceLocator}}</p><ul><li v-for="limit in r.limitations" :key="limit">{{limit}}</li></ul><p>验证问题：{{r.researchQuestion}}</p></details>
      <footer><div><a v-for="id in r.sourceIds" :key="id" :href="sourceMap.get(id)?.url" target="_blank" rel="noopener noreferrer">{{sourceMap.get(id)?.publisher??'原始资料'}} ↗</a></div><div><button type="button" @click="emit('profile',r.profileId)">人物档案</button><button v-if="personMap.get(r.profileId)?.linkedAccountId" type="button" @click="emit('account',r.profileId)">对应账户统计</button></div></footer>
    </article></div>
    <Pagination v-model:page="page" :page-size="6" :total="total" label="实盘操作记录分页"/>
  </section>
</template>
<style scoped>
.operation-desk{min-width:0}header,.card-top,footer{display:flex;justify-content:space-between;gap:.7rem;align-items:center;flex-wrap:wrap}.eyebrow{color:var(--color-accent);font-size:.66rem}h3{font-size:1.2rem;margin:.6rem 0}.intro{font-size:.76rem;line-height:1.9;color:var(--color-ink-secondary);max-width:66rem}.filters{display:flex;gap:.7rem;align-items:flex-end;flex-wrap:wrap;background:white;padding:1rem;border:1px solid var(--color-line);border-radius:.6rem;margin:1.1rem 0}.filters label{display:grid;gap:.4rem;font-size:.68rem;min-width:0}.filters input,.filters select{padding:.6rem;border:1px solid var(--color-line);border-radius:.4rem;background:white;font:inherit;max-width:100%}button{padding:.55rem .7rem;border:1px solid var(--color-line);border-radius:.4rem;background:white;color:inherit;font:inherit;font-size:.7rem;cursor:pointer}button:disabled{opacity:.45;cursor:default}.operation-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.operation-card{padding:1.2rem;border:1px solid var(--color-line);border-radius:.7rem;background:white;min-width:0;display:flex;flex-direction:column}.card-top{font-size:.62rem;color:var(--color-ink-secondary)}.evidence{padding:.35rem .5rem;background:#f5f0e3;color:#806338;border-radius:.3rem}.evidence.official{background:#eaf1ed;color:#3c6651}h4{font-size:1.15rem;margin:1rem 0 .5rem}h4 small{display:block;margin-top:.5rem;font-size:.7rem;font-weight:400;color:var(--color-accent)}.period{font-size:.73rem;margin:.5rem 0}.period span{color:var(--color-ink-secondary)}.instrument{font-size:.8rem;display:block;line-height:1.8}.contracts{font:500 .75rem var(--font-numeric);color:var(--color-accent);margin:.4rem 0}.fact{font-size:.75rem;line-height:1.9;color:var(--color-ink-secondary);min-height:2.8rem}dl{display:grid;grid-template-columns:1fr 1fr;gap:.9rem;padding:.9rem;background:#f6f7f4;border-radius:.45rem;margin:.3rem 0 1rem}dt{font-size:.62rem;color:var(--color-ink-secondary);margin-bottom:.35rem}dd{font-size:.7rem;line-height:1.8;margin:0;overflow-wrap:anywhere}.reading{padding:.9rem;border-left:2px solid #aec1a5;background:#f4f7f0}.reading b{font-size:.67rem;color:var(--color-accent)}.reading p,details p,details li{font-size:.7rem;line-height:1.85;color:var(--color-ink-secondary);margin:.4rem 0}details{margin:.8rem 0}details ul{padding-left:1.2rem}summary{font-size:.7rem;cursor:pointer}footer{padding-top:.8rem;border-top:1px solid var(--color-line);margin-top:auto}footer a{font-size:.67rem;color:var(--color-accent)}footer>div:last-child{display:flex;gap:.4rem}.empty{padding:1.1rem;border-radius:.45rem;background:#f5f0e3;font-size:.76rem;line-height:1.9}@media(max-width:850px){.operation-grid{grid-template-columns:1fr}.filters label{flex:1 1 40%}.filters input,.filters select{width:100%}}@media(max-width:500px){.operation-card{padding:1rem}dl{grid-template-columns:1fr}.filters{padding:.8rem}}
</style>

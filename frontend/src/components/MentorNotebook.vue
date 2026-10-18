<script setup lang="ts">
import {computed,ref} from 'vue'
import type {LearningTemplate} from '../types/mentors'
import Pagination from './Pagination.vue'
import {usePagination} from '../composables/usePagination'
const props=defineProps<{templates:LearningTemplate[];person:string;personId?:string;legacyNameMatch?:boolean}>()
type Note={id:string;person:string;subjectId?:string;templateId:string;title:string;hypothesis:string;failure:string;result:string;status:string;updatedAt:string}
const key='aiquant.mentor-notes.v1',notes=ref<Note[]>([]),error=ref(''),message=ref(''),selected=ref('')
let storageReadable=true
try{const raw=localStorage.getItem(key);if(raw){const parsed:unknown=JSON.parse(raw);if(!Array.isArray(parsed)||!parsed.every(n=>n&&['id','person','templateId','title','hypothesis','failure','result','status','updatedAt'].every(k=>typeof n[k]==='string')))throw Error();notes.value=parsed}}catch{storageReadable=false;error.value='本地笔记暂时无法读取。未覆盖原有资料；请复制保留当前草稿，修复旧资料后再保存。'}
const draft=ref<Note|null>(null),ordered=computed(()=>[...notes.value].sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt)))
const {items,page,total}=usePagination(ordered,5)
function start(template:LearningTemplate){
  selected.value=template.id;message.value=''
  const existing=notes.value.find(n=>n.templateId===template.id&&(n.subjectId===props.personId&&!!props.personId||!n.subjectId&&(!props.personId||props.legacyNameMatch)&&n.person===props.person))
  draft.value=existing?{...existing,subjectId:props.personId}:{id:crypto.randomUUID(),person:props.person,subjectId:props.personId,templateId:template.id,title:template.title,hypothesis:'',failure:template.failure,result:'',status:'PLANNED',updatedAt:''}
  if(existing)message.value='已打开原有笔记，未覆盖你的内容。'
}
function edit(note:Note){draft.value={...note};selected.value=note.templateId;message.value=''}
function save(){
  if(!draft.value)return
  if(!storageReadable){error.value='旧资料读取失败，已阻止覆盖。请先复制保留草稿与旧资料。';return}
  if(!draft.value.hypothesis.trim()||!draft.value.failure.trim()){message.value='请先写清可验证假设和失败条件';return}
  const next={...draft.value,updatedAt:new Date().toISOString()};const updated=[...notes.value.filter(n=>n.id!==next.id),next]
  try{localStorage.setItem(key,JSON.stringify(updated));notes.value=updated;draft.value={...next};message.value='已保存到本浏览器。结论仍是你的研究记录，未经独立验证。';error.value=''}catch{error.value='本地保存失败，请先复制保留笔记内容。'}
}
const statuses:Record<string,string>={PLANNED:'待验证',TESTING:'验证中',REVIEWED:'已复盘（自评）',REJECTED:'假设不成立'}
</script>
<template>
  <section class="notebook">
    <header><span class="eyebrow">把启发变成可以失败的假设</span><h3>我的借鉴实验</h3><p>先用自己的资金、时间与信息条件写出规则，再预留未看过的时期检验。笔记仅保存在本浏览器，不会自动下单，也不代表系统认证了收益能力。</p></header>
    <div class="templates"><article v-for="t in templates" :key="t.id"><h4>{{t.title}}</h4><p>{{t.question}}</p><dl><dt>练习</dt><dd>{{t.practice}}</dd><dt>所需证据</dt><dd>{{t.required}}</dd><dt>推翻条件</dt><dd>{{t.failure}}</dd></dl><button type="button" @click="start(t)">围绕{{person}}建立练习</button></article></div>
    <form v-if="draft" class="draft" @submit.prevent="save"><h4>{{draft.person}} · {{draft.title}}</h4><label>可验证假设<textarea v-model="draft.hypothesis" required rows="3" maxlength="5000" placeholder="明确市场、规则、仓位和观察期限；避免只写顺势、耐心等口号"/></label><label>什么结果会推翻假设<textarea v-model="draft.failure" required rows="2" maxlength="5000"/></label><label>状态<select v-model="draft.status"><option v-for="(text,value) in statuses" :key="value" :value="value">{{text}}</option></select></label><label>证据与复盘<textarea v-model="draft.result" rows="3" maxlength="10000" placeholder="记录数据期间、资金约束、费用和反例；正面结果也不证明未来有效"/></label><button type="submit">保存学习笔记</button></form>
    <p v-if="message" role="status">{{message}}</p><p v-if="error" role="alert">{{error}}</p>
    <div class="practice-links"><RouterLink to="/paper">去模拟交易练习 →</RouterLink><RouterLink to="/backtest">去历史回测检验 →</RouterLink><span>这里未提供前辈的完整算法，练习不能称为复刻大佬收益。</span></div>
    <h4>已保存的实验</h4><p v-if="!total">还没有笔记。从上面的一个问题开始。</p><article v-for="note in items" :key="note.id" class="saved"><div><strong>{{note.person}} · {{note.title}}</strong><span>{{statuses[note.status]??note.status}}</span></div><p>{{note.hypothesis}}</p><button type="button" @click="edit(note)">打开笔记</button></article><Pagination v-model:page="page" :page-size="5" :total="total" label="学习笔记分页"/>
  </section>
</template>
<style scoped>
.notebook{padding:1.3rem;background:white;border:1px solid var(--color-line);border-radius:.7rem}.eyebrow{font-size:.66rem;color:var(--color-accent)}h3{font-size:1.1rem;margin:.5rem 0}header p,p,dd{font-size:.74rem;line-height:1.9;color:var(--color-ink-secondary)}.templates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.templates article{padding:1rem;border:1px solid var(--color-line);border-radius:.5rem;background:#fafbf8}h4{font-size:.84rem;margin:.6rem 0}dt{font-size:.66rem;font-weight:600;margin-top:.6rem}dd{margin:.2rem 0}.draft{margin-top:1.2rem;padding:1rem;background:#f4f6f1;border-radius:.5rem}label{display:grid;gap:.5rem;margin:.8rem 0;font-size:.73rem}textarea,select{width:100%;box-sizing:border-box;min-width:0;padding:.6rem;border:1px solid var(--color-line);border-radius:.4rem;background:white;font:inherit}button{padding:.6rem .8rem;border:1px solid var(--color-line);border-radius:.4rem;background:white;color:var(--color-accent);font-size:.7rem;cursor:pointer}.practice-links{display:flex;gap:1rem;flex-wrap:wrap;margin:1.5rem 0;font-size:.72rem}.practice-links a{color:var(--color-accent)}.practice-links span{width:100%;color:var(--color-ink-secondary)}.saved{padding:.8rem 0;border-bottom:1px solid var(--color-line)}.saved div{display:flex;align-items:center;justify-content:space-between;gap:1rem;font-size:.73rem}.saved div span{font-size:.65rem;color:var(--color-accent)}.saved p{white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:700px){.templates{grid-template-columns:1fr}}
</style>

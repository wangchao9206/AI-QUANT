<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {api,type PaperFill,type PaperFillNote} from '../services/api'
import {tradeLabel} from '../utils/paperChartTrades'
import {formatTime,formatNumber} from '../utils/format'
const props=defineProps<{sessionId:string;fill:PaperFill}>()
const drafts=new Map<string,{content:string;saved:string;version:number;updatedAt?:string}>()
const draft=ref<{content:string;saved:string;version:number;updatedAt?:string}|null>(null)
const loading=ref(false),saving=ref(false),error=ref(''),message=ref('')
let generation=0
const key=computed(()=>`${props.sessionId}/${props.fill.id}`)
const dirty=computed(()=>draft.value?.content!==draft.value?.saved)
async function load(force=false){
 const ticket=++generation,k=key.value
 error.value='';message.value='';draft.value=null;loading.value=false
 if(!force&&drafts.has(k)){draft.value=drafts.get(k)!;return}
 loading.value=true
 try{const note=await api.paperFillNote(props.sessionId,props.fill.id);if(ticket!==generation)return
  draft.value={content:note.content,saved:note.content,version:note.version,updatedAt:note.updatedAt};drafts.set(k,draft.value)
 }catch(e){if(ticket===generation)error.value=e instanceof Error?e.message:'心得读取失败'}
 finally{if(ticket===generation)loading.value=false}
}
async function save(){
 if(!draft.value||saving.value)return
 const k=key.value,ticket=generation,text=draft.value.content,version=draft.value.version
 saving.value=true;error.value='';message.value=''
 try{const note:PaperFillNote=await api.savePaperFillNote(props.sessionId,props.fill.id,{content:text,version})
  const cached=drafts.get(k);if(cached){cached.saved=note.content;cached.version=note.version;cached.updatedAt=note.updatedAt}
  if(ticket===generation)message.value='心得已保存'
 }catch(e){if(ticket===generation)error.value=e instanceof Error?e.message:'保存失败，草稿仍保留'}
 finally{saving.value=false}
}
watch(key,()=>void load(),{immediate:true})
</script>
<template>
 <section class="fill-journal" aria-label="逐笔交易心得">
  <header><div><small>交易手记 · 仅本人可见</small><h3>{{tradeLabel(fill)}} · {{formatNumber(fill.fillPrice,2)}} · {{fill.quantity}}手</h3><p>{{formatTime(fill.marketTime)}} · {{fill.contract}}</p></div><span v-if="draft?.updatedAt">上次保存 {{formatTime(draft.updatedAt)}}</span></header>
  <p v-if="loading" role="status">正在读取心得…</p>
  <template v-if="draft"><label :for="`journal-${fill.id}`">我的心得与感悟</label><textarea :id="`journal-${fill.id}`" v-model="draft.content" maxlength="6000" rows="6" placeholder="当时为什么入场或离场？看到了什么信号？执行、情绪和下次想改进的地方…" /><footer><span>{{draft.content.length}} / 6000 · {{dirty?'有未保存的草稿':'已保存'}}</span><button type="button" :disabled="saving||!dirty" @click="save">{{saving?'保存中…':'保存本笔心得'}}</button></footer></template>
  <p v-if="message" role="status">{{message}}</p><p v-if="error" role="alert">{{error}} <button v-if="!draft" type="button" @click="load(true)">重试</button></p>
 </section>
</template>
<style scoped>
.fill-journal{margin:1rem 0;padding:1.25rem;border:1px solid var(--color-line,#d7e0de);border-left:3px solid #527c70;border-radius:.75rem;background:#f7faf8}.fill-journal header{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}.fill-journal h3{font-size:1rem;margin:.4rem 0}.fill-journal small,.fill-journal p,.fill-journal header>span,.fill-journal footer>span{font-size:.75rem;color:var(--color-ink-secondary,#53645e)}.fill-journal label{display:block;font-size:.8rem;margin:.8rem 0 .5rem}.fill-journal textarea{box-sizing:border-box;width:100%;resize:vertical;padding:.8rem;border:1px solid #c7d6ce;border-radius:.45rem;background:white;font:inherit;line-height:1.7}.fill-journal footer{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-top:.7rem}.fill-journal button{padding:.6rem .9rem;background:#315f51;color:white;border:0;border-radius:.4rem;cursor:pointer}.fill-journal button:disabled{opacity:.5;cursor:default}
</style>

<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {ArrowUpRight,BookOpen,RefreshCw} from 'lucide-vue-next'
import {booksApi,type ReadingBook,type BookPreview} from '../services/books'
import {formatTradingDate} from '../utils/format'

const props=defineProps<{book:ReadingBook}>()
const result=ref<BookPreview|null>(null),loading=ref(false),error=ref(''),selected=ref(0)
let generation=0,active=true
function safeUrl(value:string){
  try{const url=new URL(value);return url.protocol==='https:'&&url.hostname==='weread.qq.com'&&!url.username&&!url.password
    &&(!url.port||url.port==='443')&&!url.search&&!url.hash&&/^\/web\/reader\/[A-Za-z0-9]{12,80}$/.test(url.pathname)}catch{return false}
}
const resources=computed(()=>result.value?.resources.filter(r=>safeUrl(r.readerUrl))??[])
const resource=computed(()=>resources.value[selected.value])
async function load(refresh=false){
  const id=props.book.id,version=++generation;loading.value=true;error.value='';result.value=null;selected.value=0
  try{const response=await booksApi.preview(id,refresh);if(active&&version===generation)result.value=response}
  catch(e){if(active&&version===generation)error.value=e instanceof Error?e.message:'阅读资源暂时不可用'}
  finally{if(active&&version===generation)loading.value=false}
}
watch(()=>props.book.id,()=>void load(),{immediate:true})
onUnmounted(()=>{active=false;generation++})
</script>

<template>
  <section class="preview-panel" aria-label="书籍在线预览">
    <header class="preview-heading"><div><BookOpen :size="20"/><div><h3>打开原著，边读边想。</h3><p>按书名与作者查找文字阅读资源，平台保留原有的试读、登录与购买规则。</p></div></div><button type="button" :disabled="loading" @click="load(true)"><RefreshCw :size="14"/>重新查找</button></header>
    <p v-if="loading" class="preview-state" role="status">正在为《{{book.title}}》查找在线阅读入口…</p>
    <div v-else-if="error" class="preview-state preview-error" role="alert"><p>{{error}}</p><button type="button" @click="load(true)">重试查找</button></div>
    <template v-else-if="resource">
      <label v-if="resources.length>1" class="edition-select">选择阅读版本<select v-model.number="selected" aria-label="选择阅读版本"><option v-for="(item,index) in resources" :key="item.readerUrl" :value="index">{{item.title}} · {{item.publisher||item.provider}}</option></select></label>
      <div class="preview-source"><div><span>{{resource.provider}} · 在线阅读</span><h4>{{resource.title}}</h4><p>{{resource.author}}<template v-if="resource.publisher"> · {{resource.publisher}}</template></p><small>资源核对：{{formatTradingDate(resource.verifiedAt)}}</small></div><a :href="resource.readerUrl" target="_blank" rel="noopener noreferrer" class="open-reader" aria-label="在新窗口打开原著">打开在线预览 <ArrowUpRight :size="15"/></a></div>
      <p class="preview-access">{{resource.accessNote}} 点击后将在新窗口打开{{resource.provider}}的原著阅读器。</p>
      <div class="reader-instructions"><BookOpen :size="30" :stroke-width="1.3"/><div><h4>在原平台阅读，在这里留下感悟。</h4><p>阅读后切回“我的感悟”，记录触动你的内容、理解和问题。当前页面尚未保存的草稿会在切换页签时保留。</p></div></div>
      <p class="preview-footnote">正文由{{resource.provider}}提供，本站保留你的感悟记录，不缓存或改写平台正文。</p>
    </template>
    <div v-else class="preview-state preview-empty"><BookOpen :size="28"/><p>{{result?.message||'暂未找到与这本书相符的阅读入口。'}}</p><p>核对书名和作者后，可重新查找。</p><a href="https://weread.qq.com/" target="_blank" rel="noopener noreferrer">打开微信读书 <ArrowUpRight :size="14"/></a></div>
  </section>
</template>

<style scoped>
.reader-instructions{display:flex;align-items:start;gap:1rem;margin:1.4rem 0;padding:1.4rem 1rem;border-block:1px solid #e5daca;color:#aa8b6a}.reader-instructions>svg{flex-shrink:0}.reader-instructions h4{margin:0;font:500 1rem/1.8 var(--font-display);color:#786049}.reader-instructions p{font-size:.73rem;line-height:1.95;margin:.5rem 0 0;color:#98816a}
.preview-panel{padding:1.6rem 2rem;min-width:0}.preview-heading,.preview-heading>div{display:flex;align-items:start;gap:.65rem}.preview-heading{justify-content:space-between;gap:1rem}.preview-heading>div>svg{color:#8b3f35;flex-shrink:0}.preview-heading h3{margin:0;font:600 1rem var(--font-display);color:#654f3b}.preview-heading p{font-size:.7rem;line-height:1.9;color:#8b7c6b;margin:.5rem 0 0}.preview-heading button{display:flex;align-items:center;gap:.3rem;white-space:nowrap;border:1px solid #ddcfbd;border-radius:.4rem;background:transparent;color:#8b3f35;padding:.45rem .6rem;cursor:pointer;font-size:.65rem}.preview-heading button:disabled{opacity:.5;cursor:default}.preview-source{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:1rem 1.1rem;margin-top:1.2rem;background:#f5eee2;border:1px solid #e4d6c4;border-radius:.5rem}.preview-source span{font-size:.62rem;color:#a58464}.preview-source h4{font-size:.86rem;line-height:1.8;color:#654f3b;margin:.3rem 0;overflow-wrap:anywhere}.preview-source p{font-size:.7rem;color:#8b7c6b;margin:.2rem 0}.preview-source small{font-size:.59rem;color:#a18b73}.open-reader{display:inline-flex;align-items:center;gap:.3rem;flex-shrink:0;padding:.65rem .8rem;background:#8b3f35;border-radius:.4rem;text-decoration:none;color:white;font-size:.72rem}.preview-access,.preview-footnote{font-size:.67rem;color:#9a826a;line-height:1.9;margin:.8rem 0}.preview-footnote{margin-bottom:0}.book-reader{display:block;width:100%;min-width:0;height:72vh;min-height:560px;border:1px solid #dacebd;border-radius:.5rem;background:white}.preview-state{font-size:.74rem;color:#8b7c6b;line-height:1.9;padding:.8rem 0}.preview-error{color:#963c32}.preview-state button{border:1px solid #ddcfbd;background:transparent;border-radius:.4rem;padding:.5rem .7rem;cursor:pointer;color:#8b3f35}.preview-empty{text-align:center;padding:2rem 1rem}.preview-empty a{display:inline-flex;gap:.3rem;align-items:center;color:#8b3f35}.edition-select{display:grid;gap:.5rem;font-size:.7rem;color:#8b7c6b;margin-top:1.1rem}.edition-select select{max-width:100%;min-width:0;font-size:.72rem;padding:.6rem;border:1px solid #ddcfbd;border-radius:.4rem;background:white;color:inherit}
@media(max-width:760px){.preview-panel{padding:1.2rem 1.1rem}.preview-heading{flex-wrap:wrap}.preview-source{align-items:start;flex-direction:column;gap:.8rem}.book-reader{height:76vh;min-height:520px}.preview-access{font-size:.65rem}}
</style>

<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {BookOpen,ChevronLeft,ChevronRight,RefreshCw} from 'lucide-vue-next'
import catalog from '../content/chanlunChapters.json'

interface TextBlock {type:'text';text:string}
interface ImageBlock {type:'image';src:string;alt:string}
interface Chapter {number:number;title:string;author:string;publishedAt:string;sourceUrl:string;blocks:(TextBlock|ImageBlock)[]}
const storageKey='aiquant-chanlun-chapter'
const props=defineProps<{initialChapter?:number}>()
const emit=defineEmits<{chapterChange:[number:number]}>()
function savedChapter(){
  try{const number=Number(localStorage.getItem(storageKey));return Number.isInteger(number)&&number>=1&&number<=108?number:1}catch{return 1}
}
const validChapter=(number:unknown):number|undefined=>typeof number==='number'&&Number.isInteger(number)&&number>=1&&number<=108?number:undefined
const current=ref(validChapter(props.initialChapter)??savedChapter()),search=ref(''),loading=ref(false),error=ref(''),content=ref<Chapter|null>(null)
const font=ref(1),article=ref<HTMLElement|null>(null)
const fontClasses=['font-small','font-normal','font-large']
const chapter=computed(()=>catalog.chapters.find(item=>item.number===current.value)!)
const chapters=computed(()=>catalog.chapters.filter(item=>`${item.number} ${item.title}`.includes(search.value.trim())))
const imagePattern=new RegExp(`^/reading-assets/chanlun/${catalog.version}/images/[a-f0-9]{16}\\.(?:jpg|jpeg|png|gif|webp)$`)
let generation=0,controller:AbortController|undefined,active=true
async function load(){
  const version=++generation,number=current.value
  controller?.abort();controller=new AbortController();loading.value=true;error.value='';content.value=null
  try{
    const response=await fetch(chapter.value.contentPath,{signal:controller.signal})
    if(!response.ok||!response.headers.get('Content-Type')?.includes('application/json'))throw new Error('正文文件暂时不可用，请重新载入。')
    const data=await response.json() as Chapter
    if(data.number!==number||data.author!=='缠中说禅'||!Array.isArray(data.blocks)
      ||data.blocks.some(block=>block.type==='image'?!imagePattern.test(block.src):block.type!=='text'||typeof block.text!=='string'))throw new Error('正文文件校验失败，请重新载入。')
    if(active&&generation===version){content.value=data;if(article.value)article.value.scrollTop=0}
  }catch(failure){if(active&&generation===version)error.value=failure instanceof Error?failure.message:'正文读取失败，请重试。'}
  finally{if(active&&generation===version)loading.value=false}
}
watch(()=>props.initialChapter,number=>{const valid=validChapter(number);if(valid)current.value=valid})
watch(current,number=>{try{localStorage.setItem(storageKey,String(number))}catch{/* Reading remains available without storage. */}emit('chapterChange',number);void load()},{immediate:true})
onUnmounted(()=>{active=false;generation++;controller?.abort()})
</script>

<template>
  <section class="chanlun-reader" aria-label="缠论正文阅读">
    <header class="reader-title"><BookOpen :size="21"/><div><h3>教你炒股票 · 原始连载</h3><p>作者：缠中说禅 · 108课正文与配图，自动记住上次课号。</p></div></header>
    <div class="reader-layout">
      <aside class="chapter-sidebar" aria-label="缠论章节目录">
        <label>章节目录 · 108课<input v-model="search" type="search" aria-label="搜索缠论章节" placeholder="搜索课号或标题"/></label>
        <nav class="chapter-list" aria-label="选择缠论章节"><button v-for="item in chapters" :key="item.number" type="button" :aria-current="current===item.number?'page':undefined" @click="current=item.number"><span>{{String(item.number).padStart(3,'0')}}</span>{{item.title.replace(/^教你炒股票\d+[：:]?/,'')}}</button></nav>
        <p v-if="!chapters.length" class="reader-note">没有匹配的章节，请更换关键词。</p>
      </aside>
      <div class="chapter-reading">
        <h4>{{chapter.title}}</h4>
        <div class="chapter-controls"><button type="button" :disabled="current===1" @click="current--"><ChevronLeft :size="16"/>上一课</button><span>{{current}} / 108</span><button type="button" :disabled="current===108" @click="current++">下一课<ChevronRight :size="16"/></button><button type="button" :disabled="loading" @click="load"><RefreshCw :size="14"/>重新载入</button></div>
        <div class="reading-options"><span>阅读字号</span><button type="button" aria-label="缩小正文字号" :disabled="font===0" @click="font--">A−</button><button type="button" aria-label="放大正文字号" :disabled="font===2" @click="font++">A+</button><span v-if="content">{{content.publishedAt}}</span></div>
        <p v-if="loading" role="status" class="reader-note">正在读取第{{current}}课正文…</p>
        <p v-else-if="error" role="alert" class="reader-note">{{error}}</p>
        <article v-else-if="content" ref="article" class="chapter-body" :class="fontClasses[font]" :aria-label="`第${current}课正文`" tabindex="0">
          <template v-for="(block,index) in content.blocks" :key="index"><p v-if="block.type==='text'">{{block.text}}</p><figure v-else><img :src="block.src" :alt="block.alt" loading="lazy"/></figure></template>
          <p class="chapter-end">第{{current}}课 · 正文结束</p>
        </article>
        <details class="reading-provenance"><summary>版本与出处</summary><p>原文作者：缠中说禅。原始发表：缠中说禅新浪博客。</p><p class="source-address">{{chapter.sourceUrl}}</p><p>本系统提供公开整理档案中的108课正文及配图，未将网友评论或疑似作者小号的回复混入正文。保留原文表达；整理档案与原博可能存在排版、配图及文字差异。</p><p>转载依据：作者在第8、17课回复中允许转载，并要求注明出处、推广原博客。原文版权归原作者所有；档案整理来源为 stockServ/chzhshch-108-plus（MIT）。</p><a :href="catalog.provenancePath" download>下载来源与版本核对记录</a></details>
      </div>
    </div>
  </section>
</template>

<style scoped>
.chanlun-reader{padding:1.5rem 2rem;color:#654f3b}.reader-title{display:flex;align-items:flex-start;gap:.7rem;margin-bottom:1.2rem}.reader-title h3{margin:0;font-size:1rem}.reader-title p,.reader-note{font-size:.72rem;line-height:1.9;color:#8b7c6b}.reader-title p{margin:.4rem 0 0}.reader-layout{display:grid;grid-template-columns:13rem minmax(0,1fr);gap:1rem;min-width:0}.chapter-sidebar{border:1px solid #e2d9ca;border-radius:.5rem;padding:.8rem;min-width:0}.chapter-sidebar label{display:grid;gap:.7rem;font-size:.74rem}.chapter-sidebar input{box-sizing:border-box;width:100%;padding:.6rem;border:1px solid #ded7cb;border-radius:.3rem;background:#fff;font:inherit}.chapter-list{display:grid;gap:.25rem;max-height:76vh;overflow:auto;margin-top:.7rem}.chapter-list button{display:flex;align-items:baseline;gap:.4rem;text-align:left;border:0;background:transparent;padding:.65rem .4rem;font:inherit;font-size:.72rem;line-height:1.7;color:inherit;cursor:pointer;overflow-wrap:anywhere}.chapter-list span{font-size:.62rem;color:#a18b73;flex-shrink:0}.chapter-list button[aria-current=page]{background:#f4e9de;color:#8b3f35;border-radius:.3rem;font-weight:600}.chapter-reading{min-width:0}.chapter-reading h4{font-size:1rem;line-height:1.8;margin:0 0 .7rem;overflow-wrap:anywhere}.chapter-controls{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap}.chapter-controls button{display:inline-flex;align-items:center;gap:.25rem;padding:.45rem .6rem;border:1px solid #ddcfbd;border-radius:.3rem;background:#fffdf7;color:#8b3f35;font-size:.7rem;cursor:pointer}.chapter-controls span{font-size:.68rem;color:#a18b73}.chapter-controls button:disabled{opacity:.4;cursor:default}.chapter-body{box-sizing:border-box;max-height:76vh;overflow:auto;padding:1.2rem 1.6rem;border:1px solid #e2d9ca;border-radius:.4rem;background:#fffefa;color:#453c33;line-height:2;scrollbar-gutter:stable}.chapter-body p{white-space:pre-wrap;overflow-wrap:anywhere;margin:0 auto 1.2em;max-width:40em}.chapter-body figure{margin:1.4rem 0}.chapter-body img{display:block;max-width:100%;height:auto;margin:auto}.font-small{font-size:16px}.font-normal{font-size:18px}.font-large{font-size:21px}.reading-options{display:flex;align-items:center;gap:.6rem;margin:1rem 0;font-size:.7rem;color:#8b7c6b;flex-wrap:wrap}.reading-options button{padding:.25rem .55rem;background:transparent;border:1px solid #ded7cb;border-radius:.3rem;color:inherit;cursor:pointer}.reading-options button:disabled{opacity:.4}.chapter-end{text-align:center;color:#a18b73;font-size:.7rem;padding-top:1rem}.reading-provenance{font-size:.68rem;line-height:1.9;color:#8b7c6b;margin-top:1rem}.reading-provenance summary{cursor:pointer}.reading-provenance p{margin:.7rem 0}.reading-provenance a{color:#8b3f35}.source-address{overflow-wrap:anywhere}.chanlun-reader :is(button,input):focus-visible{outline:2px solid #b17b51;outline-offset:2px}
@media(max-width:1000px){.reader-layout{grid-template-columns:minmax(0,1fr)}.chapter-list{max-height:13rem}.chapter-body{max-height:80vh;padding:1rem}.chanlun-reader{padding:1.2rem}}
</style>

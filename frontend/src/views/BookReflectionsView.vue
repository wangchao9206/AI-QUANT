<script setup lang="ts">
import {computed,onMounted,onUnmounted,reactive,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {ArrowUpRight,BookOpen,Library,NotebookPen,Plus,RefreshCw} from 'lucide-vue-next'
import {booksApi,type ReadingBook,type BookReflection,type ReflectionCategory,type ReflectionDraft} from '../services/books'
import type {RecordPage} from '../services/api'
import {featuredBook,saviorReading} from '../content/bookReflections'
import {requestId} from '../utils/requestId'
import Pagination from '../components/Pagination.vue'
import BookPreviewPanel from '../components/BookPreviewPanel.vue'

const route=useRoute(),router=useRouter()
const books=ref<ReadingBook[]>([]),selectedId=ref(typeof route.query.book==='string'?route.query.book:featuredBook.id)
const loading=ref(true),catalogReady=ref(false),catalogError=ref(''),notesError=ref(''),saveError=ref(''),notice=ref('')
const search=ref(''),tab=ref<'preview'|'ideas'|'trading'|'notes'>('ideas'),showAdd=ref(false),adding=ref(false),saving=ref(false)
const newBook=reactive({title:'',author:''}),addError=ref('')
let bookCommand:{clientRequestId:string;title:string;author:string}|null=null
const drafts=reactive<Record<string,ReflectionDraft>>({}),page=ref(1),records=ref<RecordPage<BookReflection>|null>(null),notesLoading=ref(false)
const noteCommands:Record<string,ReflectionDraft>={}
let active=true,catalogGeneration=0,notesGeneration=0
const shelf=computed(()=>catalogReady.value?books.value:[featuredBook])
const selected=computed(()=>shelf.value.find(b=>b.id===selectedId.value)??null)
const filteredBooks=computed(()=>shelf.value.filter(b=>[b.title,b.author].some(v=>v.toLowerCase().includes(search.value.trim().toLowerCase()))))
const builtIn=computed(()=>selected.value?.slug==='distant-savior')
const draft=computed(()=>drafts[selectedId.value]??(drafts[selectedId.value]={clientRequestId:requestId(),category:'IDEA',content:''}))
const categories:Record<ReflectionCategory,string>={IDEA:'思想理解',TRADING:'交易应用',QUESTION:'疑问与反思'}
const tabs=[{id:'preview',label:'在线预览'},{id:'ideas',label:'思想解读'},{id:'trading',label:'交易应用'},{id:'notes',label:'我的感悟'}] as const
const readingDate=(stamp:string)=>new Date(stamp).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})
const message=(e:unknown)=>e instanceof Error?e.message:'暂时未完成，请重试'

async function loadBooks(){
  const generation=++catalogGeneration;loading.value=true;catalogError.value=''
  try{
    const result=await booksApi.books();if(!active||generation!==catalogGeneration)return
    books.value=result;catalogReady.value=true
    if(!result.some(b=>b.id===selectedId.value)){
      selectedId.value=result.find(b=>b.slug==='distant-savior')?.id??result[0]?.id??''
      if(route.query.book)notice.value='这本书暂未找到，已返回当前书架。'
    }
    await loadNotes()
  }catch(e){if(active&&generation===catalogGeneration)catalogError.value=message(e)}
  finally{if(active&&generation===catalogGeneration)loading.value=false}
}
async function loadNotes(){
  const id=selectedId.value,currentPage=page.value,generation=++notesGeneration
  records.value=null;notesError.value=''
  if(!catalogReady.value||!selected.value){notesLoading.value=false;return}
  notesLoading.value=true
  try{const result=await booksApi.reflections(id,currentPage);if(active&&generation===notesGeneration){records.value=result;const book=books.value.find(b=>b.id===id);if(book)book.reflectionCount=result.total}}
  catch(e){if(active&&generation===notesGeneration)notesError.value=message(e)}
  finally{if(active&&generation===notesGeneration)notesLoading.value=false}
}
function selectBook(book:ReadingBook){
  if(book.id===selectedId.value)return
  selectedId.value=book.id;page.value=1;notice.value='';saveError.value=''
  tab.value=book.slug==='distant-savior'?'ideas':'notes'
  void router.replace({path:'/books',query:{book:book.id}})
  void loadNotes()
}
async function createBook(){
  if(adding.value||!newBook.title.trim())return
  const payload={title:newBook.title.trim(),author:newBook.author.trim()}
  if(!bookCommand||bookCommand.title!==payload.title||bookCommand.author!==payload.author)bookCommand={...payload,clientRequestId:requestId()}
  adding.value=true;addError.value=''
  try{
    const result=await booksApi.create({...bookCommand});if(!active)return
    books.value=[result,...books.value.filter(b=>b.id!==result.id)];catalogReady.value=true
    showAdd.value=false;newBook.title='';newBook.author='';bookCommand=null;search.value=''
    selectBook(result);notice.value='书籍已加入书架，可以开始记录感悟。'
  }catch(e){if(active)addError.value=message(e)}finally{if(active)adding.value=false}
}
async function saveReflection(){
  if(saving.value||!catalogReady.value||!draft.value.content.trim())return
  const id=selectedId.value,previous=noteCommands[id],content=draft.value.content.trim()
  if(previous&&(previous.content!==content||previous.category!==draft.value.category))draft.value.clientRequestId=requestId()
  const body={...draft.value,content};noteCommands[id]=body
  saving.value=true;saveError.value='';notice.value=''
  try{
    const result=await booksApi.reflect(id,body);if(!active)return
    const original=drafts[id]
    // Do not erase edits made while the request was in flight.
    if(original?.clientRequestId===body.clientRequestId&&original.content.trim()===body.content&&original.category===body.category)
      drafts[id]={clientRequestId:requestId(),category:body.category,content:''}
    else if(original?.clientRequestId===body.clientRequestId)original.clientRequestId=requestId()
    if(selectedId.value===id){page.value=1;notice.value='感悟已保存到服务器。';await loadNotes()}
    return result
  }catch(e){if(active&&selectedId.value===id)saveError.value=message(e)}finally{if(active)saving.value=false}
}
watch(page,()=>void loadNotes())
watch(()=>route.query.book,value=>{
  const target=typeof value==='string'?value:featuredBook.id
  if(target===selectedId.value)return
  const book=shelf.value.find(b=>b.id===target);if(book)selectBook(book)
})
onMounted(()=>void loadBooks())
onUnmounted(()=>{active=false;catalogGeneration++;notesGeneration++})
</script>

<template>
  <div class="books-page">
    <header class="reading-hero">
      <div><p class="reading-eyebrow">THE READING ROOM / 从阅读到自己的判断</p><h2>读过的书，<br/>留下自己的理解。</h2><p class="hero-description">记录触动你的观念，也记录疑问。让一本书带来的思考，慢慢成为有依据、有边界的行动。</p></div>
      <div class="hero-seal" aria-hidden="true"><BookOpen :size="34" :stroke-width="1"/><span>阅读 · 思考 · 实践</span></div>
    </header>
    <p v-if="catalogError" class="reading-alert" role="alert">书架加载失败：{{catalogError}}。可继续阅读内置解读，保存感悟需连接服务器。<button type="button" :disabled="loading" @click="loadBooks">重新连接</button></p>
    <p v-if="notice" class="reading-notice" role="status">{{notice}}</p>
    <div class="reading-layout">
      <aside class="bookshelf" aria-label="我的书架">
        <header><div><Library :size="18"/><h3>我的书架</h3></div><span>{{shelf.length.toString().padStart(2,'0')}}</span></header>
        <label class="shelf-search"><span class="sr-only">搜索书架</span><input v-model="search" placeholder="书名或作者" aria-label="搜索书架" type="search"/></label>
        <p v-if="loading" class="quiet" role="status">正在读取书架…</p>
        <div class="book-list"><button v-for="book in filteredBooks" :key="book.id" class="book-choice" type="button" :aria-pressed="book.id===selectedId" @click="selectBook(book)"><span class="book-spine" aria-hidden="true"/><span><strong>{{book.title}}</strong><small>{{book.author||'作者未填写'}}</small><em>{{book.reflectionCount}} 条个人感悟</em></span><ArrowUpRight :size="14"/></button></div>
        <p v-if="!filteredBooks.length&&!loading" class="quiet">没有找到这本书，可以添加到书架。</p>
        <button class="add-book" type="button" :disabled="!catalogReady" :aria-expanded="showAdd" @click="showAdd=!showAdd"><Plus :size="16"/>添加书籍</button>
        <form v-if="showAdd" class="book-form" aria-label="添加书籍" @submit.prevent="createBook"><label>书名<input v-model="newBook.title" required maxlength="120" aria-label="书名"/></label><label>作者（选填）<input v-model="newBook.author" maxlength="80" aria-label="作者"/></label><p v-if="addError" role="alert">{{addError}}</p><button :disabled="adding||!newBook.title.trim()">{{adding?'正在添加…':'加入书架'}}</button></form>
        <p class="shelf-footnote">书籍与个人感悟保存在服务器，使用同一入口可继续阅读和记录。</p>
      </aside>
      <section v-if="selected" class="reading-main" aria-label="当前书籍">
        <section class="book-intro"><div class="book-cover" aria-hidden="true"><small>READING NOTES</small><strong>{{selected.title}}</strong><span>{{selected.author}}</span></div><div><span class="reading-eyebrow">{{builtIn?'首本共读 / 文学与自我认识':'我的阅读 / 持续记录'}}</span><h2>《{{selected.title}}》</h2><p class="book-author">{{selected.author||'作者未填写'}}</p><p class="intro-description">{{builtIn?saviorReading.introduction:'从一个触动你的观念开始，记下自己的理解、应用场景与仍然想追问的问题。'}}</p><p v-if="builtIn" class="interpretation-label">以下为本站阅读解读与应用思考，非原著逐字引文。</p></div></section>
        <button class="preview-entry" type="button" @click="tab='preview'"><BookOpen :size="16"/>在线预览原著 <ArrowUpRight :size="15"/></button>
        <nav class="reading-tabs" aria-label="书籍内容"><button v-for="item in tabs" :key="item.id" type="button" :aria-pressed="tab===item.id" @click="tab=item.id">{{item.label}}</button></nav>
        <BookPreviewPanel v-if="tab==='preview'" :key="selected.id" :book="selected"/>
        <template v-else>
        <section v-if="tab==='ideas'&&builtIn" class="reading-section" aria-label="思想解读"><p class="thesis">{{saviorReading.thesis}}</p><div class="idea-grid"><article v-for="(idea,index) in saviorReading.ideas" :key="idea.title" class="idea-card"><span class="chapter-index">{{String(index+1).padStart(2,'0')}}</span><h3>{{idea.title}}</h3><p>{{idea.body}}</p><div class="reading-question"><span>留给自己的问题</span><p>{{idea.question}}</p></div></article></div><button class="text-action" type="button" @click="tab='notes'">写下你的理解 <NotebookPen :size="16"/></button></section>
        <section v-else-if="tab==='trading'&&builtIn" class="reading-section" aria-label="交易应用"><p class="section-intro">把观念转成可检验的规则。文学启发帮助思考，交易优势仍需独立验证。</p><div class="application-list"><article v-for="(item,index) in saviorReading.applications" :key="item.idea"><span class="chapter-index">{{String(index+1).padStart(2,'0')}}</span><div><small>{{item.idea}}</small><h3>{{item.practice}}</h3><p>{{item.detail}}</p></div></article></div><h3 class="subheading">值得警惕的误读</h3><div class="pitfall-grid"><article v-for="item in saviorReading.pitfalls" :key="item.title"><h4>{{item.title}}</h4><p>{{item.body}}</p></article></div><aside class="reading-sources"><strong>继续核对：官方交易教育资料</strong><a v-for="source in saviorReading.sources" :key="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{source.title}} ↗<small>{{source.description}}</small></a><div class="practice-links"><RouterLink to="/paper">去模拟交易验证 <ArrowUpRight :size="14"/></RouterLink><RouterLink to="/personal">去个人总结复盘 <ArrowUpRight :size="14"/></RouterLink></div></aside></section>
        <section v-else-if="tab==='notes'" class="reading-section" aria-label="我的感悟"><div class="notes-heading"><NotebookPen :size="20"/><div><h3>把这次阅读，写成自己的话。</h3><p>可以是一条理解、一个应用假设，也可以是暂时没有答案的问题。</p></div></div><form class="reflection-form" @submit.prevent="saveReflection"><label>感悟主题<select v-model="draft.category" aria-label="感悟主题"><option v-for="(label,key) in categories" :key="key" :value="key">{{label}}</option></select></label><label>我的感悟<textarea v-model="draft.content" rows="7" required maxlength="6000" aria-label="我的感悟" placeholder="什么触动了你？你如何理解？准备怎样观察或验证？"/></label><div class="reflection-actions"><small>{{draft.content.length}} / 6000</small><button :disabled="saving||!catalogReady||!draft.content.trim()">{{saving?'正在保存…':'保存感悟'}}</button></div><p v-if="saveError" role="alert" class="form-error">{{saveError}}。内容已保留，可以重试。</p></form><header class="history-heading"><h3>阅读留下的记录 <span v-if="records">{{records.total}}</span></h3><button type="button" :disabled="notesLoading" @click="loadNotes"><RefreshCw :size="14"/>刷新</button></header><p v-if="notesLoading" class="quiet" role="status">正在读取感悟…</p><p v-if="notesError" class="form-error" role="alert">{{notesError}} <button type="button" @click="loadNotes">重新读取</button></p><div v-if="records?.items.length" class="reflection-history"><article v-for="note in records.items" :key="note.id"><header><span>{{categories[note.category]}}</span><time :datetime="note.createdAt">{{readingDate(note.createdAt)}}</time></header><p>{{note.content}}</p></article></div><div v-else-if="records&&!notesLoading" class="empty-reading"><BookOpen :size="24"/><p>还没有个人感悟。写下第一条，让这次阅读有迹可循。</p></div><Pagination v-if="records&&records.total>10" v-model:page="page" :total="records.total" :page-size="10" label="书籍感悟分页"/></section>
        <section v-else class="reading-section empty-reading"><BookOpen :size="28"/><h3>从你的第一条感悟开始。</h3><p>这本书暂未收录内置解读，你可以先记录自己的理解与问题。</p><button type="button" class="text-action" @click="tab='notes'">写下感悟 <NotebookPen :size="16"/></button></section>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.preview-entry{display:inline-flex;align-items:center;gap:.5rem;margin:0 2rem 1.2rem;padding:.7rem 1rem;border:0;border-radius:.4rem;background:#8b3f35;color:white;cursor:pointer;font-size:.74rem}.reading-tabs{flex-wrap:wrap}@media(max-width:760px){.preview-entry{margin-left:1.1rem;margin-right:1.1rem}.reading-tabs{column-gap:1rem;row-gap:0}.reading-tabs button{font-size:.7rem}}
.books-page{--reading-red:#8b3f35;--reading-paper:#fffdf7;--reading-muted:#81776b;display:grid;gap:1.25rem;min-width:0;color:var(--color-ink)}
.reading-hero{display:flex;align-items:center;justify-content:space-between;gap:2rem;padding:2rem 2.3rem;border:1px solid #e2d9ca;border-radius:1rem;background:linear-gradient(115deg,#f5eedf,#fdfbf5);position:relative;overflow:hidden}.reading-eyebrow{font-size:.63rem;letter-spacing:.12em;color:var(--reading-red);line-height:1.8}.reading-hero h2{font:500 clamp(1.8rem,3.1vw,2.65rem)/1.45 var(--font-display);margin:.7rem 0;color:#453c33}.hero-description{max-width:36rem;font-size:.78rem;line-height:1.9;color:#766b5e;margin:0}.hero-seal{display:grid;justify-items:center;gap:1rem;flex-shrink:0;border:1px solid #cdbda4;padding:2rem 1.3rem;color:#94765a;transform:rotate(4deg)}.hero-seal span{font-size:.65rem;letter-spacing:.12em}
.reading-layout{display:grid;grid-template-columns:14rem minmax(0,1fr);gap:1.25rem;align-items:start}.bookshelf{background:var(--reading-paper);border:1px solid #e2d9ca;border-radius:.85rem;padding:1.1rem;min-width:0;position:sticky;top:1rem}.bookshelf>header,.bookshelf>header>div{display:flex;align-items:center;gap:.5rem}.bookshelf>header{justify-content:space-between;color:var(--reading-red)}.bookshelf h3{font-size:.85rem;margin:0}.bookshelf>header>span{font:500 .78rem var(--font-numeric);color:#a89a87}.shelf-search{display:block;margin:1rem 0}.shelf-search input,.book-form input{width:100%;min-width:0;padding:.65rem .7rem;border:1px solid #ded7cb;border-radius:.4rem;background:white;font-size:.72rem;color:inherit;box-sizing:border-box}.book-list{display:grid;gap:.55rem;max-height:32rem;overflow:auto}.book-choice{display:flex;align-items:stretch;gap:.65rem;position:relative;width:100%;text-align:left;padding:.8rem .6rem;border:1px solid transparent;border-radius:.45rem;background:transparent;cursor:pointer;color:inherit}.book-choice[aria-pressed=true]{background:#f4ebe2;border-color:#e4cbbd}.book-spine{width:4px;min-width:4px;border-radius:2px;background:#d7cfc2}.book-choice[aria-pressed=true] .book-spine{background:var(--reading-red)}.book-choice>span:nth-child(2){display:grid;gap:.4rem;min-width:0}.book-choice strong{font-size:.78rem;overflow-wrap:anywhere}.book-choice small{font-size:.65rem;color:var(--reading-muted)}.book-choice em{font-size:.6rem;color:#a19280;font-style:normal}.book-choice>svg{flex-shrink:0;margin-left:auto;color:var(--reading-red)}.add-book{display:flex;justify-content:center;align-items:center;gap:.4rem;width:100%;margin-top:1rem;padding:.65rem;border:1px dashed #cfbeab;background:transparent;border-radius:.4rem;color:var(--reading-red);font-size:.72rem;cursor:pointer}.shelf-footnote{font-size:.6rem;line-height:1.8;color:#9b8d7c;margin:1rem 0 0}.book-form{display:grid;gap:.7rem;padding-top:1rem}.book-form label{display:grid;gap:.35rem;font-size:.68rem}.book-form p{font-size:.67rem;color:#9e382e;line-height:1.7}
.reading-main{min-width:0;border:1px solid #e2d9ca;border-radius:1rem;background:var(--reading-paper);overflow:hidden}.book-intro{display:grid;grid-template-columns:9rem minmax(0,1fr);align-items:center;gap:1.8rem;padding:1.8rem 2rem}.book-cover{background:#77382f;box-shadow:6px 6px 0 #d7ccba;min-height:12rem;border-left:7px solid #5e2c26;display:flex;flex-direction:column;align-items:center;justify-content:space-between;gap:1rem;color:#f9e8c5;padding:.9rem;box-sizing:border-box}.book-cover small{font:500 .45rem var(--font-numeric);letter-spacing:.12em}.book-cover strong{writing-mode:vertical-rl;font:500 1.25rem/1.7 var(--font-display);letter-spacing:.16em;max-height:13rem;overflow-wrap:anywhere}.book-cover span{font-size:.6rem;overflow-wrap:anywhere;max-width:100%}.book-intro h2{font:500 clamp(1.4rem,2.1vw,1.9rem)/1.6 var(--font-display);margin:.4rem 0;overflow-wrap:anywhere}.book-author{font-size:.72rem;color:var(--reading-muted);margin:0 0 .8rem}.intro-description{font-size:.76rem;color:#756b60;line-height:1.95;margin:0}.interpretation-label{font-size:.6rem;color:#a18b73;margin:.7rem 0 0;line-height:1.7}.reading-tabs{display:flex;gap:1.8rem;padding:0 2rem;border-block:1px solid #e5ded3}.reading-tabs button{border:0;border-bottom:2px solid transparent;padding:1rem 0;color:#8a7c6c;background:transparent;font-size:.75rem;cursor:pointer}.reading-tabs button[aria-pressed=true]{color:var(--reading-red);border-bottom-color:var(--reading-red);font-weight:700}.reading-section{padding:1.6rem 2rem}.thesis{font:500 1.1rem/1.9 var(--font-display);color:#654f3b;border-left:3px solid #a77753;padding:.2rem 0 .2rem 1rem;margin:0 0 1.7rem}.idea-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.4rem 1.7rem}.idea-card{min-width:0;padding-top:.8rem;border-top:1px solid #e4dacc}.chapter-index{font:500 .7rem var(--font-numeric);color:#ab8a6c;letter-spacing:.08em}.idea-card h3,.application-list h3{font:600 1rem var(--font-display);margin:.65rem 0}.idea-card>p,.application-list p,.pitfall-grid p{font-size:.74rem;color:#776c60;line-height:1.95;margin:.5rem 0}.reading-question{margin-top:1rem;background:#f5f0e6;padding:.7rem .8rem;border-radius:.3rem}.reading-question>span{font-size:.56rem;letter-spacing:.05em;color:#aa8d70}.reading-question p{font-size:.69rem;line-height:1.9;color:#716050;margin:.3rem 0 0}.text-action{display:inline-flex;align-items:center;gap:.5rem;color:var(--reading-red);padding:.5rem 0;border:0;background:transparent;cursor:pointer;font-size:.74rem;margin-top:1.2rem}.section-intro{font-size:.76rem;line-height:1.9;color:#756b60;margin:0 0 1rem}.application-list{display:grid}.application-list article{display:grid;grid-template-columns:1.8rem minmax(0,1fr);gap:.6rem;padding:1.1rem 0;border-bottom:1px solid #e5ded3}.application-list small{font-size:.6rem;color:#aa8d70}.application-list h3{margin:.3rem 0}.subheading{font:600 1rem var(--font-display);margin:1.8rem 0 1rem}.pitfall-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.9rem}.pitfall-grid article{background:#f5ede6;border-radius:.4rem;padding:.9rem}.pitfall-grid h4{font-size:.76rem;color:var(--reading-red);margin:0 0 .5rem}.reading-sources{display:grid;gap:.85rem;margin-top:1.5rem;padding-top:1.2rem;border-top:1px solid #e2d9ca}.reading-sources>strong{font-size:.68rem;color:#8d7d6a}.reading-sources>a{display:grid;gap:.3rem;font-size:.7rem;color:var(--reading-red);text-decoration:none}.reading-sources small{font-size:.64rem;color:#8f8272;line-height:1.8}.practice-links{display:flex;flex-wrap:wrap;gap:1rem}.practice-links a{display:inline-flex;align-items:center;gap:.2rem;color:var(--reading-red);font-size:.7rem;text-decoration:none}
.notes-heading{display:flex;gap:.65rem;color:var(--reading-red);align-items:start}.notes-heading h3{font:600 1rem var(--font-display);margin:0}.notes-heading p{font-size:.72rem;color:#8b7c6b;line-height:1.9;margin:.5rem 0 0}.reflection-form{display:grid;gap:1rem;margin:1.3rem 0 2rem}.reflection-form label{display:grid;gap:.5rem;font-size:.7rem;color:#7d6d5c}.reflection-form select{width:12rem;max-width:100%;padding:.55rem .7rem;border:1px solid #dbd0bf;border-radius:.4rem;background:white;color:inherit;font-size:.72rem}.reflection-form textarea{width:100%;min-width:0;box-sizing:border-box;resize:vertical;border:1px solid #dbd0bf;border-radius:.5rem;background:#fffefa;padding:.9rem;color:#574a3b;font:400 .78rem/1.9 var(--font-sans)}.reflection-actions{display:flex;align-items:center;justify-content:space-between}.reflection-actions small{font:400 .63rem var(--font-numeric);color:#a18d75}.reflection-actions button,.book-form>button{padding:.65rem 1rem;border:0;border-radius:.4rem;background:var(--reading-red);color:white;font-size:.72rem;cursor:pointer}.history-heading{display:flex;align-items:center;justify-content:space-between;gap:.5rem;padding-bottom:.8rem;border-bottom:1px solid #e3d9ca}.history-heading h3{font:500 .95rem var(--font-display);margin:0}.history-heading h3 span{font:400 .65rem var(--font-numeric);margin-left:.4rem;color:#a18d75}.history-heading button{display:flex;gap:.3rem;align-items:center;border:0;background:none;color:#977e64;font-size:.65rem;cursor:pointer}.reflection-history article{padding:1.2rem 0;border-bottom:1px solid #e8dfd1}.reflection-history header{display:flex;justify-content:space-between;gap:.6rem;flex-wrap:wrap;font-size:.62rem}.reflection-history header span{color:var(--reading-red);background:#f4e9de;padding:.15rem .4rem;border-radius:.2rem}.reflection-history time{color:#aa9680}.reflection-history article>p{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.95;font-size:.77rem;color:#6a5b4b;margin:.8rem 0 0}.empty-reading{text-align:center;padding:2rem 1rem;color:#aa967b}.empty-reading h3{font-size:.9rem}.empty-reading p{font-size:.73rem;line-height:1.9}.quiet{font-size:.68rem;line-height:1.8;color:#9a8a77}.form-error,.reading-alert{font-size:.72rem;color:#963c32;line-height:1.8}.reading-alert{padding:.8rem 1rem;border:1px solid #e8cabc;border-radius:.5rem;background:#fff4ed}.reading-alert button,.form-error button{color:inherit;background:none;border:0;text-decoration:underline;cursor:pointer}.reading-notice{padding:.7rem 1rem;margin:0;border:1px solid #ccdbce;background:#f0f6ed;color:#4b7151;border-radius:.4rem;font-size:.72rem}.books-page button:disabled{opacity:.5;cursor:default}.books-page :is(button,input,textarea,select):focus-visible{outline:2px solid #b17b51;outline-offset:3px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
@media(max-width:1050px){.reading-layout{grid-template-columns:12rem minmax(0,1fr)}.book-intro{grid-template-columns:6rem minmax(0,1fr);gap:1.2rem;padding:1.5rem}.book-cover{min-height:10rem;padding:.6rem}.book-cover strong{font-size:1rem}.reading-section{padding:1.4rem}.reading-tabs{padding:0 1.4rem}.idea-grid,.pitfall-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:760px){.reading-layout{grid-template-columns:minmax(0,1fr)}.bookshelf{position:static}.book-list{display:flex;overflow:auto;max-height:none}.book-choice{min-width:12rem;max-width:18rem;width:auto;flex-shrink:0}.bookshelf>header{margin-bottom:.5rem}.shelf-search{margin:.7rem 0}.shelf-footnote{margin:.6rem 0 0}.reading-hero{padding:1.5rem;gap:.8rem}.hero-seal{padding:1rem .6rem}.hero-seal span{display:none}.hero-description{font-size:.72rem}.book-intro{grid-template-columns:5rem minmax(0,1fr);padding:1.1rem;gap:1rem}.book-cover{min-height:9rem;border-left-width:4px}.book-cover strong{font-size:.9rem}.book-cover small{font-size:.35rem}.book-intro h2{font-size:1.3rem}.intro-description{font-size:.7rem}.book-intro .reading-eyebrow{font-size:.54rem}.reading-tabs{padding:0 1.1rem;gap:1.3rem}.reading-section{padding:1.2rem 1.1rem}.thesis{font-size:.98rem}.reading-hero h2{font-size:1.7rem}}
</style>

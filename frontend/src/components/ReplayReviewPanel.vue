<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { authState, hasPermission } from '../services/auth'
import { observedReviewAction, replayReviewsApi, reviewActions, type ReplayReview, type ReplayReviewAction, type ReplayReviewContext, type ReplayReviewTarget } from '../services/replayReviews'
import { formatTradingDateTime } from '../utils/format'
import { requestUuid } from '../utils/requestId'

const props=defineProps<{context:ReplayReviewContext; at:string; fills?:ReplayReviewTarget[]; busy?:boolean; workflowId?:string|null; preset?:string}>()
const emit=defineEmits<{pause:[]; editing:[boolean]}>()
const canWrite=computed(()=>hasPermission('paper.write'))
const canEditWorkflow=computed(()=>hasPermission('workflows.read'))
const editablePresets=new Set(['HOLISTIC_14D','MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','DUAL_THRUST','ADAPTIVE_CTA','BUY_AND_HOLD'])
const notes=ref<ReplayReview[]>([])
const loading=ref(false)
const writing=ref(false)
const listError=ref('')
const saveError=ref('')
const notice=ref('')
const form=ref<{context:ReplayReviewContext; at:string; fills:ReplayReviewTarget[]}|null>(null)
const targetId=ref('')
const suggestedAction=ref<ReplayReviewAction>('WAIT')
const reason=ref('')
const identity=computed(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId,props.context]))
const visible=computed(()=>notes.value.filter(note=>Date.parse(note.at)<=Date.parse(props.at)))
const editTarget=computed(()=>{
  const source=props.context.kind==='session'?{reviewSession:props.context.id}
    :{reviewVersion:props.context.id,reviewRun:props.context.reviewRunId}
  if(props.workflowId) return {path:'/strategy/workflows',query:{draft:props.workflowId,...source}}
  const id=visible.value.find(note=>note.workflowId)?.workflowId
  if(id) return {path:'/strategy/workflows',query:{draft:id,...source}}
  if(props.preset&&editablePresets.has(props.preset)) return {path:'/strategy/workflows',query:{preset:props.preset,...source}}
  return null
})
let generation=0
let attempt:{key:string; id:string}|null=null
let disposed=false
watch(()=>!!form.value,value=>emit('editing',value))
onUnmounted(()=>{disposed=true;++generation;emit('editing',false)})

async function load() {
  const poll=++generation
  listError.value=''
  loading.value=true
  try {
    const records=await replayReviewsApi.list(props.context)
    if(poll===generation) notes.value=records
  } catch(failure) {
    if(poll===generation) listError.value=failure instanceof Error?failure.message:'复盘标注暂不可用'
  } finally { if(poll===generation) loading.value=false }
}

watch(identity,()=>{
  notes.value=[]
  form.value=null
  attempt=null
  writing.value=false
  notice.value=''
  void load()
},{immediate:true})

function open() {
  if(props.busy||!props.at||!canWrite.value||writing.value)return
  emit('pause')
  form.value={context:{...props.context},at:props.at,fills:(props.fills??[]).slice()}
  reason.value=''
  targetId.value=''
  suggestedAction.value='WAIT'
  saveError.value=''
  notice.value=''
  attempt=null
}

async function save() {
  const editor=form.value
  if(!editor||writing.value||!reason.value.trim())return
  const target=editor.fills.find(item=>item.id===targetId.value)
  const payload={at:target?.at??editor.at,stage:target?'FILL' as const:'BAR' as const,
    ...(target?{targetId:target.id}:{}),suggestedAction:suggestedAction.value,reason:reason.value.trim()}
  const key=JSON.stringify(payload)
  if(attempt?.key!==key)attempt={key,id:requestUuid()}
  const scope=identity.value
  writing.value=true
  saveError.value=''
  try {
    const saved=await replayReviewsApi.save(editor.context,{...payload,clientRequestId:attempt.id})
    if(disposed||scope!==identity.value)return
    ++generation
    loading.value=false
    notes.value=[saved,...notes.value.filter(note=>note.id!==saved.id)]
    form.value=null
    notice.value='复盘标注已保存。'
    void load()
  } catch(failure) {
    if(scope===identity.value)saveError.value=failure instanceof Error?failure.message:'保存标注失败'
  } finally {if(scope===identity.value)writing.value=false}
}
</script>

<template>
  <section class="replay-review" aria-label="策略复盘标注">
    <header>
      <div><h3>策略复盘</h3><p>标注当前时点或一笔已发生的成交，写下你会怎么处理。</p></div>
      <button v-if="canWrite&&!form" type="button" :disabled="busy||!at" @click="open">暂停并标注</button>
    </header>
    <form v-if="form" class="review-editor" @submit.prevent="save">
      <div class="review-fields">
        <label>标注对象
          <select v-model="targetId" :disabled="writing">
            <option value="">当前时点 · {{ formatTradingDateTime(form.at) }}</option>
            <option v-for="item in form.fills" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select>
        </label>
        <label>我会怎么做
          <select v-model="suggestedAction" :disabled="writing"><option v-for="(label,action) in reviewActions" :key="action" :value="action">{{ label }}</option></select>
        </label>
      </div>
      <label>为什么这样做 <textarea v-model="reason" rows="2" maxlength="1000" placeholder="例如：收盘刚越过均线，想等第二根确认再进场" :disabled="writing" required /></label>
      <p v-if="saveError" role="alert" class="review-error">{{ saveError }}</p>
      <div class="review-controls">
        <button type="submit" :disabled="writing||!reason.trim()">{{ writing?'保存中…':'保存标注' }}</button>
        <button type="button" :disabled="writing" @click="form=null">取消</button>
      </div>
    </form>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="listError" role="alert" class="review-error">{{ listError }} <button type="button" @click="load">重试</button></p>
    <p v-else-if="loading" role="status">正在读取复盘标注…</p>
    <details v-if="visible.length" open>
      <summary>已保存 {{ visible.length }} 条标注</summary>
      <ol class="review-history">
        <li v-for="item in visible" :key="item.id">
          <time :datetime="item.at">{{ formatTradingDateTime(item.at) }}</time>
          <strong>{{ reviewActions[item.suggestedAction] }}</strong>
          <small>{{ item.stage==='FILL'?'模拟成交':'当时信号' }} · {{ observedReviewAction(item.observedAction) }}</small>
          <p>{{ item.reason }}</p>
        </li>
      </ol>
    </details>
    <RouterLink v-if="editTarget&&canEditWorkflow" :to="editTarget">打开策略草稿，准备下一版</RouterLink>
  </section>
</template>

<style scoped>
.replay-review { min-width: 0; padding: .9rem 1rem; border: 1px solid var(--color-line); border-radius: .65rem; background: var(--color-surface); }
.replay-review header,.review-fields,.review-controls { display: flex; gap: .65rem; align-items: start; flex-wrap: wrap; }
.replay-review header { justify-content: space-between; }
.replay-review h3 { font-size: .95rem; margin: 0; }
.replay-review p { font-size: .78rem; margin: .36rem 0 .6rem; line-height: 1.55; }
.replay-review button { border: 1px solid var(--color-line); border-radius: .45rem; padding: .45rem .65rem; background: var(--color-surface-raised); color: var(--color-ink); cursor: pointer; }
.replay-review button:disabled { opacity: .5; cursor: default; }
.review-editor { display: grid; gap: .65rem; padding: .75rem 0; border-top: 1px solid var(--color-line); }
.review-editor label { display: grid; min-width: 0; gap: .3rem; font-size: .77rem; }
.review-editor select,.review-editor textarea { min-width: 0; max-width: 100%; box-sizing: border-box; color: var(--color-ink); background: var(--color-surface-raised); border: 1px solid var(--color-line); border-radius: .35rem; padding: .4rem; font: inherit; }
.review-fields label:first-child { flex: 1 1 12rem; }
.replay-review summary,.replay-review a { cursor: pointer; font-size: .78rem; }
.replay-review a { display: inline-block; color: var(--color-accent); margin-top: .5rem; }
.review-history { display: grid; gap: .5rem; max-height: 18rem; overflow: auto; padding-left: 0; list-style: none; }
.review-history li { padding: .48rem 0; border-bottom: 1px solid var(--color-line); overflow-wrap: anywhere; }
.review-history strong,.review-history time,.review-history small { margin-right: .5rem; font-size: .75rem; }
.review-history time,.review-history small { color: var(--color-ink-secondary); }
.review-error { color: var(--color-warning); }
</style>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { observedReviewAction, replayReviewsApi, reviewActions, type ReplayReview, type ReplayReviewContext } from '../services/replayReviews'
import { formatTradingDateTime } from '../utils/format'

const props=defineProps<{context:ReplayReviewContext}>()
const entries=ref<ReplayReview[]>([]), error=ref(''), loading=ref(false)
let generation=0
async function load(){
  const ticket=++generation
  loading.value=true
  error.value=''
  try {
    const value=await replayReviewsApi.list(props.context)
    if(ticket===generation)entries.value=value
  } catch(failure){
    if(ticket===generation)error.value=failure instanceof Error?failure.message:'复盘建议暂不可用'
  } finally {if(ticket===generation)loading.value=false}
}
watch(()=>props.context,()=>{entries.value=[];void load()},{immediate:true})
onUnmounted(()=>{++generation})
</script>

<template>
  <details class="workflow-feedback" open>
    <summary>本次复盘建议<span v-if="entries.length"> · {{ entries.length }} 条</span></summary>
    <p v-if="error" role="alert">{{ error }} <button type="button" @click="load">重试</button></p>
    <p v-else-if="loading" role="status">正在读取建议…</p>
    <p v-else-if="!entries.length">这次模拟还没有保存标注。</p>
    <template v-else>
      <p>修改规则后发布新版本，再用相同合约、区间、资金和成本验证。</p>
      <ul>
        <li v-for="entry in entries" :key="entry.id">
          <time :datetime="entry.at">{{ formatTradingDateTime(entry.at) }}</time>
          <strong>{{ reviewActions[entry.suggestedAction] }}</strong>
          <small>原处理：{{ observedReviewAction(entry.observedAction) }}</small>
          <p>{{ entry.reason }}</p>
        </li>
      </ul>
    </template>
  </details>
</template>

<style scoped>
.workflow-feedback { border: 1px solid var(--color-line); border-radius: .55rem; padding: .7rem .9rem; margin: .8rem 0; font-size: .78rem; }
.workflow-feedback summary { cursor: pointer; font-weight: 650; }
.workflow-feedback ul { padding: 0; max-height: 16rem; overflow: auto; list-style: none; }
.workflow-feedback li { padding: .45rem 0; border-top: 1px solid var(--color-line); overflow-wrap: anywhere; }
.workflow-feedback li strong,.workflow-feedback time { margin-right: .5rem; }
.workflow-feedback small { color: var(--color-ink-secondary); }
.workflow-feedback p { margin: .4rem 0; line-height: 1.65; }
</style>

<script setup lang="ts">
import {computed} from 'vue'
const props=withDefaults(defineProps<{page:number;pageSize:number;total:number;label?:string}>(),{label:'列表分页'})
const emit=defineEmits<{'update:page':[number]}>()
const pages=computed(()=>Math.max(1,Math.ceil(props.total/props.pageSize)))
</script>
<template>
  <nav class="pagination" :aria-label="label">
    <span>共 {{total}} 条 · 第 {{page}} / {{pages}} 页</span>
    <div><button type="button" :disabled="page<=1" @click="emit('update:page',1)">首页</button><button type="button" :disabled="page<=1" @click="emit('update:page',page-1)">上一页</button><label><span class="sr-only">{{label}}页码</span><input :value="page" type="number" min="1" :max="pages" :aria-label="`${label}页码`" @change="emit('update:page',Math.min(pages,Math.max(1,Math.floor(Number(($event.target as HTMLInputElement).value)||1))))" /></label><button type="button" :disabled="page>=pages" @click="emit('update:page',page+1)">下一页</button><button type="button" :disabled="page>=pages" @click="emit('update:page',pages)">末页</button></div>
  </nav>
</template>
<style scoped>
.pagination{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.65rem;padding:.9rem 0;font-size:.7rem;color:var(--color-ink-secondary)}.pagination div{display:flex;gap:.35rem;align-items:center}.pagination button,.pagination input{border:1px solid var(--color-line);border-radius:.35rem;background:var(--color-surface,#fff);padding:.35rem .5rem;color:inherit;min-height:2rem}.pagination input{width:3.6rem;text-align:center}.pagination button:disabled{opacity:.4;cursor:default}.pagination button:not(:disabled){cursor:pointer}.pagination button:focus-visible,.pagination input:focus-visible{outline:2px solid var(--color-accent);outline-offset:2px}
</style>

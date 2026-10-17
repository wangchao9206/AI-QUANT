<script setup lang="ts">
import {useExperience} from '../composables/useExperience'
const {mode,setMode,persistenceError}=useExperience()
</script>
<template>
  <div class="experience-control"><div class="experience-switch" role="group" aria-label="页面信息模式"><button type="button" :aria-pressed="mode==='SIMPLE'" @click="setMode('SIMPLE')">简明模式</button><button type="button" :aria-pressed="mode==='PRO'" @click="setMode('PRO')">专业模式</button></div><span v-if="persistenceError" role="status">{{persistenceError}}</span></div>
</template>
<style scoped>
.experience-control{position:relative;flex-shrink:0}.experience-switch{display:flex;padding:3px;border:1px solid var(--color-line);border-radius:.65rem;background:var(--color-surface)}button{border:0;background:transparent;color:var(--color-ink-secondary);font-size:.67rem;white-space:nowrap;border-radius:.4rem;padding:.5rem .65rem;cursor:pointer}button[aria-pressed=true]{background:var(--color-accent);color:white}.experience-control>span{display:block;position:absolute;font-size:.6rem;line-height:1.5;color:var(--color-warning);width:12rem;margin-top:.2rem;z-index:2;background:var(--color-surface)}
</style>

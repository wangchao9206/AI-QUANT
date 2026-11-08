<script setup lang="ts">
import {useExperience} from '../composables/useExperience'
import {computed,watch} from 'vue'
import {usePrivateDocument} from '../composables/usePrivateDocument'
import {preferencesTarget} from '../services/workspace'
import {validatePreferences,type PersonalPreferences} from '../utils/workspaceContent'
import {authState} from '../services/auth'
import PrivateDocumentControls from './PrivateDocumentControls.vue'
const {mode,setMode,persistenceError}=useExperience()
const sync=usePrivateDocument(computed(()=>preferencesTarget),():PersonalPreferences=>({schemaVersion:1,experience:mode.value}),validatePreferences,computed(()=>!!authState.user))
let applying=false
watch(sync.draft,value=>{applying=true;setMode(value.experience);applying=false},{deep:true,immediate:true,flush:'sync'})
watch(mode,value=>{if(!applying)sync.replaceDraft({schemaVersion:1,experience:value})},{flush:'sync'})
</script>
<template>
  <div class="experience-control"><div class="experience-switch" role="group" aria-label="页面信息模式"><button type="button" :aria-pressed="mode==='SIMPLE'" @click="setMode('SIMPLE')">简明模式</button><button type="button" :aria-pressed="mode==='PRO'" @click="setMode('PRO')">专业模式</button></div><span v-if="persistenceError" role="status">{{persistenceError}}</span><PrivateDocumentControls :sync="sync" label="页面模式"/></div>
</template>
<style scoped>
.experience-control{position:relative;flex-shrink:0}.experience-switch{display:flex;padding:3px;border:1px solid var(--color-line);border-radius:.65rem;background:var(--color-surface)}button{border:0;background:transparent;color:var(--color-ink-secondary);font-size:.67rem;white-space:nowrap;border-radius:.4rem;padding:.5rem .65rem;cursor:pointer}button[aria-pressed=true]{background:var(--color-accent);color:white}.experience-control>span{display:block;position:absolute;font-size:.6rem;line-height:1.5;color:var(--color-warning);width:12rem;margin-top:.2rem;z-index:2;background:var(--color-surface)}
.experience-control :deep(.private-sync>div){position:absolute;right:0;z-index:30;width:min(22rem,calc(100vw - 2rem));max-height:70vh;overflow:auto;box-sizing:border-box;white-space:normal}
@media(max-width:650px){.experience-control :deep(.private-sync>div){width:min(18rem,calc(100vw - 6rem))}}
</style>

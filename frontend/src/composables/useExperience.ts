import {computed,ref,watch} from 'vue'
import {authState} from '../services/auth'

export type ExperienceMode='SIMPLE'|'PRO'
const key=()=>authState.user?`aiquant.experience.v2:${authState.user.id}:${authState.user.tenantId}`:''
function readMode():ExperienceMode {
  try{return key()&&localStorage.getItem(key())==='PRO'?'PRO':'SIMPLE'}catch{return 'SIMPLE'}
}
const mode=ref<ExperienceMode>(readMode())
const isSimple=computed(()=>mode.value==='SIMPLE')
const persistenceError=ref('')
function setMode(value:ExperienceMode){
  mode.value=value
  try{if(key())localStorage.setItem(key(),value);persistenceError.value=''}
  catch{persistenceError.value='本次切换已生效，浏览器无法保存偏好'}
}
watch(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId]),()=>{mode.value=readMode();persistenceError.value=''},{flush:'sync'})
export function useExperience(){return {mode,isSimple,setMode,persistenceError}}

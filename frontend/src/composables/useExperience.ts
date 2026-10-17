import {computed,ref} from 'vue'

export type ExperienceMode='SIMPLE'|'PRO'
const key='aiquant.experience.v1'
function readMode():ExperienceMode {
  try{return localStorage.getItem(key)==='PRO'?'PRO':'SIMPLE'}catch{return 'SIMPLE'}
}
const mode=ref<ExperienceMode>(readMode())
const isSimple=computed(()=>mode.value==='SIMPLE')
const persistenceError=ref('')
function setMode(value:ExperienceMode){
  mode.value=value
  try{localStorage.setItem(key,value);persistenceError.value=''}
  catch{persistenceError.value='本次切换已生效，浏览器无法保存偏好'}
}
export function useExperience(){return {mode,isSimple,setMode,persistenceError}}

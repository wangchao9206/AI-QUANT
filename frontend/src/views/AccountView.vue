<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {RouterLink} from 'vue-router'
import {authCall,authState,loadIdentity} from '../services/auth'
const user=computed(()=>authState.user),tab=ref('workspace'),busy=ref(false),error=ref(''),message=ref('')
const tabs=computed(()=>[{id:'workspace',name:'工作空间'},{id:'security',name:'安全与会话'},{id:'keys',name:'平台接入'}])
type Row=Record<string,any>
const sessions=ref<Row[]>([]),keys=ref<Row[]>([])
const tenantName=ref(''),keyName=ref(''),keyScope=ref('READ'),keyDays=ref(30),newKey=ref('')
const canManage=computed(()=>['OWNER','ADMIN'].includes(user.value?.role??''))
const bindingEmail=ref(''),bindingPassword=ref('')
const date=(v:unknown)=>v?new Date(String(v)).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—'
async function load(){
  error.value=''
  const tasks=[authCall<Row[]>('/sessions').then(r=>sessions.value=r),authCall<Row[]>('/keys').then(r=>keys.value=r)]
  const results=await Promise.allSettled(tasks);const failed=results.find(r=>r.status==='rejected');if(failed?.status==='rejected')error.value=failed.reason instanceof Error?failed.reason.message:'部分数据读取失败，请重试。'
}
async function run(action:()=>Promise<unknown>,success='已保存。'){
  if(busy.value)return;busy.value=true;error.value='';message.value=''
  try{await action();message.value=success;await load()}catch(e){error.value=e instanceof Error?e.message:'操作失败，请重试。'}finally{busy.value=false}
}
async function switchTenant(id:string){await run(async()=>{await authCall('/tenants/switch',{tenantId:id});window.location.assign('/account')})}
async function createTenant(){await run(async()=>{await authCall('/tenants',{name:tenantName.value});tenantName.value='';await loadIdentity()})}
async function createKey(){newKey.value='';await run(async()=>{const result=await authCall<{token:string}>('/keys',{name:keyName.value,scope:keyScope.value,days:keyDays.value});newKey.value=result.token;keyName.value=''},'密钥已创建，仅显示一次。')}
onMounted(()=>void load())
</script>
<template>
  <div class="account-page" v-if="user"><header class="account-heading"><div><p class="kicker">IDENTITY / WORKSPACES</p><h2>{{user.username}} 的账号</h2><p>{{user.email??'管理员尚未绑定邮箱'}} · {{user.platformAdmin?'平台管理员':user.role}}</p></div><button :disabled="busy" @click="load">刷新</button></header>
    <nav class="tabs" aria-label="账号设置分类"><button v-for="item in tabs" :key="item.id" :aria-selected="tab===item.id" @click="tab=item.id;newKey=''">{{item.name}}</button></nav>
    <p v-if="error" role="alert" class="notice">{{error}}</p><p v-if="message" role="status" class="message">{{message}}</p>
    <template v-if="tab==='workspace'"><section><h3>我的工作空间</h3><p class="intro">每个工作空间拥有独立的模拟账户、策略、笔记和结构研究记录。同一工作空间内的成员按角色协作。</p><div class="tenant-grid"><article v-for="tenant in user.tenants" :key="tenant.id"><small>{{tenant.role}} {{tenant.id===user.tenantId?'· 当前空间':''}}</small><h4>{{tenant.name}}</h4><button :disabled="tenant.id===user.tenantId||busy" @click="switchTenant(tenant.id)">切换到此空间</button></article></div><form @submit.prevent="createTenant"><label>新建工作空间<input v-model="tenantName" required maxlength="80" aria-label="新工作空间名称"/></label><button :disabled="busy">创建</button></form></section>
      <section v-if="canManage||user.platformAdmin"><h3>成员与访问管理</h3><p class="intro">租户、用户、角色、菜单和操作记录已移至独立后台。</p><RouterLink to="/admin">打开后台管理 ↗</RouterLink></section>
    </template>
    <template v-if="tab==='security'"><section><h3>密码与邮箱</h3><p class="intro">修改或找回密码后，全部会话和接口密钥会失效。</p><RouterLink to="/auth/change-password">修改密码</RouterLink> · <RouterLink to="/auth/forgot">通过邮箱找回密码</RouterLink>
      <form @submit.prevent="run(async()=>{await authCall('/email',{email:bindingEmail,password:bindingPassword});bindingPassword=''},'请到新邮箱完成验证；成功后需重新登录。')"><label>绑定 / 更换邮箱<input v-model="bindingEmail" aria-label="新邮箱" type="email" required maxlength="254"/></label><label>当前密码<input v-model="bindingPassword" aria-label="绑定邮箱时的当前密码" type="password" autocomplete="current-password" required maxlength="128"/></label><button :disabled="busy">发送邮箱验证</button></form>
      </section><section><h3>登录会话</h3><p class="intro">撤销当前会话后，需要重新登录。</p><div class="table-wrap"><table><thead><tr><th>创建时间</th><th>有效期至</th><th>操作</th></tr></thead><tbody><tr v-for="item in sessions" :key="item.id"><td>{{date(item.createdAt)}}</td><td>{{date(item.expiresAt)}}</td><td><button :disabled="busy" @click="run(()=>authCall(`/sessions/${item.id}/revoke`,{}),'会话已撤销。')">撤销</button></td></tr></tbody></table></div></section></template>
    <template v-if="tab==='keys'"><section><h3>为其他平台生成接口密钥</h3><p class="intro">密钥固定绑定当前用户与工作空间，支持 Authorization: Bearer 接入已授权的业务 API。角色降权、移除成员、改密或停用账号后，相关访问会立即受限。</p><form @submit.prevent="createKey"><label>用途名称<input v-model="keyName" required maxlength="80" aria-label="密钥名称"/></label><label>权限<select v-model="keyScope"><option value="READ">只读</option><option v-if="user.role!=='VIEWER'" value="READ_WRITE">读写</option></select></label><label>有效天数<input v-model.number="keyDays" type="number" min="1" max="365" required/></label><button :disabled="busy">创建密钥</button></form><div v-if="newKey" class="secret" role="status"><strong>仅显示一次，请复制保存。</strong><code>{{newKey}}</code><button @click="newKey=''">已保存，隐藏</button></div><div class="table-wrap"><table><thead><tr><th>名称</th><th>权限</th><th>有效期</th><th>操作</th></tr></thead><tbody><tr v-for="item in keys" :key="item.id"><td>{{item.name}}</td><td>{{item.scope}}</td><td>{{date(item.expiresAt)}}</td><td><button :disabled="busy" @click="run(()=>authCall(`/keys/${item.id}/revoke`,{}),'密钥已撤销。')">撤销</button></td></tr></tbody></table></div></section></template>
  </div>
</template>
<style scoped>
.account-page{display:grid;gap:1.2rem;min-width:0}.account-heading{display:flex;justify-content:space-between;align-items:center;gap:1rem}.account-heading h2{font:500 1.8rem var(--font-display);margin:.7rem 0}.account-heading p,.intro{font-size:.76rem;color:var(--color-ink-secondary);line-height:1.9}.kicker{font:.65rem var(--font-numeric)!important;letter-spacing:.1em;color:var(--color-accent)!important}.tabs{display:flex;flex-wrap:wrap;gap:.5rem;border-bottom:1px solid var(--color-line);padding-bottom:.9rem}button{font:inherit;font-size:.73rem;border:1px solid var(--color-line-strong);border-radius:.4rem;background:var(--color-surface);color:var(--color-ink);padding:.6rem .8rem;cursor:pointer}button[aria-selected=true]{background:var(--color-accent);color:white;border-color:var(--color-accent)}button:disabled{opacity:.5;cursor:default}section{border:1px solid var(--color-line);border-radius:.7rem;background:var(--color-surface);padding:1.3rem;min-width:0}h3{font:500 1.2rem var(--font-display);margin:0 0 1rem}h4{font-size:1rem;margin:.7rem 0}small{font:.65rem var(--font-numeric);color:var(--color-accent)}.tenant-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(14rem,1fr));gap:.8rem;margin:1rem 0}article{border:1px solid var(--color-line);border-radius:.4rem;padding:1rem}form{display:flex;align-items:end;gap:.8rem;flex-wrap:wrap;margin:1rem 0}label{display:grid;gap:.4rem;font-size:.7rem;min-width:0;flex:1}input,select{font:inherit;border:1px solid var(--color-line-strong);background:var(--color-surface-raised);border-radius:.4rem;padding:.65rem;min-width:0}.table-wrap{overflow:auto;max-width:100%}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:.73rem}th{text-align:left;color:var(--color-ink-secondary);font-weight:500}td,th{padding:.8rem .6rem;border-bottom:1px solid var(--color-line)}td{font-family:var(--font-numeric)}.actions{display:flex;gap:.4rem}a{font-size:.76rem;color:var(--color-accent)}.notice,.message,.secret{padding:.9rem;border-radius:.4rem;font-size:.75rem;line-height:1.9;background:var(--color-warning-soft);color:var(--color-warning);overflow-wrap:anywhere}.message{background:var(--color-success-soft);color:var(--color-success)}.secret{display:grid;gap:.7rem}.secret code{white-space:normal;word-break:break-all;font: .8rem var(--font-numeric);user-select:all}.notice button{margin-right:.5rem}@media(max-width:650px){section{padding:1rem}form label{flex-basis:100%}.account-heading{align-items:start}.tabs button{padding:.55rem}.tenant-grid{grid-template-columns:1fr}}
</style>

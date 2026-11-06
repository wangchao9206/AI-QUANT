<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {RouterLink,useRoute,useRouter} from 'vue-router'
import AppMark from '../components/AppMark.vue'
import {authCall,loadIdentity,forgetIdentity,safeNext} from '../services/auth'
const route=useRoute(),router=useRouter()
const mode=computed(()=>route.path.split('/').at(-1)??'login')
const titles:Record<string,string>={login:'登录工作空间',register:'用真实邮箱创建账号',verify:'验证你的邮箱','verify-email':'确认绑定新邮箱',forgot:'找回密码',reset:'设置新密码',resend:'重新发送验证邮件','change-password':'设置新密码'}
const identifier=ref(''),username=ref(''),email=ref(''),password=ref(''),oldPassword=ref(''),confirm=ref(''),busy=ref(false),error=ref(''),message=ref(''),token=ref('')
function readToken(){const candidate=new URLSearchParams(route.hash.slice(1)).get('token');if(candidate)token.value=candidate;else token.value='';error.value='';message.value='';password.value='';oldPassword.value='';confirm.value=''}
watch(()=>route.fullPath,readToken,{immediate:true})
const changing=computed(()=>['reset','change-password'].includes(mode.value))
async function submit(){
  if(busy.value)return;error.value='';message.value=''
  if(changing.value&&(password.value!==confirm.value||new TextEncoder().encode(password.value).length>72)){error.value='两次输入的密码需一致，且不超过 72 字节。';return}
  busy.value=true
  try{
    if(mode.value==='login'){
      await authCall('/login',{identifier:identifier.value,password:password.value});const user=await loadIdentity()
      await router.replace(user?.mustChangePassword?'/auth/change-password':safeNext(route.query.next));return
    }
    const bodies:Record<string,unknown>={register:{username:username.value,email:email.value},verify:{token:token.value},'verify-email':{token:token.value},forgot:{email:email.value},resend:{email:email.value},reset:{token:token.value,password:password.value},'change-password':{oldPassword:oldPassword.value,password:password.value}}
    const result=await authCall<{message:string}>('/'+mode.value,bodies[mode.value]);message.value=result.message
    if(changing.value){forgetIdentity();password.value='';oldPassword.value='';confirm.value=''}
    if(['verify','verify-email','reset'].includes(mode.value)){token.value='';history.replaceState(history.state,'',route.path)}
  }catch(e){error.value=e instanceof Error?e.message:'操作失败，请稍后重试。'}finally{busy.value=false}
}
</script>
<template>
  <main class="auth-page"><section class="auth-story"><div class="brand"><AppMark/><strong>AI-QUANT</strong></div><div><p>ONE IDENTITY / YOUR WORKSPACE</p><h1>让每一份研究，<br/>有自己的归属。</h1><span>邮箱验证 · 独立工作空间 · 可管理的访问权限</span></div><small>真实行情、研究记录和模拟账户，从你的工作空间开始。</small></section>
    <section class="auth-panel"><div class="auth-card"><p class="eyebrow">ACCOUNT / 账号</p><h2>{{titles[mode]}}</h2>
      <p v-if="mode==='register'" class="intro">验证邮件会发往你的邮箱。初始密码为「账号 + 123456」，首次登录后必须修改。</p>
      <p v-if="mode==='change-password'" class="intro">使用初始密码的账号需先完成此步骤。保存成功后，全部旧会话和接口密钥都会失效。</p>
      <p v-if="route.query.error" role="status" class="notice">{{route.query.error}}</p>
      <form @submit.prevent="submit">
        <label v-if="mode==='login'">账号或邮箱<input v-model="identifier" autocomplete="username" required maxlength="254" aria-label="账号或邮箱"/></label>
        <label v-if="mode==='register'">账号<input v-model="username" autocomplete="username" required pattern="[a-z][a-z0-9_]{2,31}" maxlength="32" placeholder="3～32 位小写字母、数字或下划线" aria-label="注册账号"/></label>
        <label v-if="['register','forgot','resend'].includes(mode)">邮箱<input v-model="email" type="email" autocomplete="email" required maxlength="254" aria-label="邮箱"/></label>
        <label v-if="mode==='login'">密码<input v-model="password" type="password" autocomplete="current-password" required maxlength="128" aria-label="密码"/></label>
        <template v-if="changing"><label v-if="mode==='change-password'">原密码<input v-model="oldPassword" type="password" autocomplete="current-password" required maxlength="128" aria-label="原密码"/></label><label>新密码<input v-model="password" type="password" autocomplete="new-password" minlength="12" maxlength="72" required aria-label="新密码"/></label><label>确认新密码<input v-model="confirm" type="password" autocomplete="new-password" minlength="12" maxlength="72" required aria-label="确认新密码"/></label><small>至少 12 个字符，最多 72 字节；不能继续使用初始密码。</small></template>
        <p v-if="['verify','verify-email','reset'].includes(mode)&&!token" class="notice">未找到有效验证链接，请从邮件中的链接打开本页。</p>
        <p v-if="error" role="alert" class="notice">{{error}}</p><p v-if="message" role="status" class="success">{{message}}</p>
        <button v-if="!message" class="submit" :disabled="busy||(['verify','verify-email','reset'].includes(mode)&&!token)">{{busy?'正在处理…':mode==='login'?'登录':['verify','verify-email'].includes(mode)?'确认验证邮箱':changing?'保存新密码':'发送验证邮件'}}</button>
      </form>
      <nav><RouterLink v-if="mode!=='login'" to="/auth/login">返回登录</RouterLink><template v-else><RouterLink to="/auth/register">邮箱注册</RouterLink><RouterLink to="/auth/forgot">忘记密码</RouterLink><RouterLink to="/auth/resend">重发验证邮件</RouterLink></template></nav>
      <p class="footer">请使用自己的账号登录，验证链接仅在有效期内可使用一次。</p>
    </div></section>
  </main>
</template>
<style scoped>
.auth-page{min-height:100vh;display:grid;grid-template-columns:1fr 1fr;background:var(--color-canvas)}.auth-story{background:#171c20;color:#fff;padding:3rem 4rem;display:flex;flex-direction:column;justify-content:space-between;gap:3rem}.brand{display:flex;gap:1rem;align-items:center;letter-spacing:.1em}.auth-story p{font:.7rem var(--font-numeric);letter-spacing:.12em;color:#a3c3d3}.auth-story h1{font:400 clamp(2rem,4vw,4.5rem) var(--font-display);line-height:1.5;margin:1.5rem 0}.auth-story span,.auth-story small{color:#acb4b9;font-size:.8rem;line-height:1.9}.auth-panel{display:flex;align-items:center;justify-content:center;padding:3rem 2rem}.auth-card{max-width:25rem;width:100%}.eyebrow{font:.7rem var(--font-numeric);color:var(--color-accent);letter-spacing:.1em}h2{font:500 1.9rem var(--font-display);margin:1rem 0 1.5rem}.intro,.footer{font-size:.75rem;line-height:1.9;color:var(--color-ink-secondary)}form{display:grid;gap:1.1rem}label{display:grid;gap:.5rem;font-size:.8rem}input{font:inherit;border:1px solid var(--color-line-strong);border-radius:.4rem;padding:.8rem;background:var(--color-surface);width:100%;min-width:0}.submit{padding:.9rem;background:var(--color-accent);color:#fff;border:0;border-radius:.4rem;font:inherit;cursor:pointer}button:disabled{opacity:.5;cursor:default}nav{display:flex;flex-wrap:wrap;gap:1.1rem;margin:1.5rem 0}nav a{color:var(--color-accent);font-size:.75rem}.notice,.success{font-size:.76rem;padding:.8rem;line-height:1.8;border-radius:.4rem;background:var(--color-warning-soft);color:var(--color-warning);overflow-wrap:anywhere}.success{color:var(--color-success);background:var(--color-success-soft)}form small{color:var(--color-ink-secondary);line-height:1.8}.footer{border-top:1px solid var(--color-line);padding-top:1rem;margin-top:2rem}@media(max-width:800px){.auth-page{grid-template-columns:1fr}.auth-story{padding:1.5rem;gap:1rem}.auth-story h1{font-size:1.8rem;margin:.7rem 0}.auth-story>small{display:none}.auth-panel{padding:2rem 1.3rem}}
</style>

<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {api} from '../services/api'
import type {LedgerAnalysis} from '../types/mentors'
import Pagination from './Pagination.vue'
import {usePagination} from '../composables/usePagination'
import {formatNumber,formatTime} from '../utils/format'
const csvText=ref(''),sourceLabel=ref(''),sourceUrl=ref(''),rights=ref(false),busy=ref(false),error=ref('')
const result=ref<LedgerAnalysis|null>(null),revision=ref(0),analyzedRevision=ref(-1)
watch([csvText,sourceLabel,sourceUrl,rights],()=>revision.value++,{flush:'sync'})
const stale=computed(()=>result.value&&revision.value!==analyzedRevision.value)
const pairs=computed(()=>result.value?.pairs??[]),contracts=computed(()=>result.value?.byContract??[]),positions=computed(()=>result.value?.openPositions??[])
const {items:paired,page:pairPage,total:pairTotal}=usePagination(pairs,10,[result])
const {items:contractRows,page:contractPage,total:contractTotal}=usePagination(contracts,10,[result])
const {items:openRows,page:openPage,total:openTotal}=usePagination(positions,10,[result])
const number=(v?:number|null)=>v==null?'资料不足，不能计算':formatNumber(v,2)
function download(text:string,name:string,type:string){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function template(){download('\ufefftrade_id,time,trading_day,contract,side,offset,price,quantity,multiplier,fee\r\n','成交分析空白模板.csv','text/csv;charset=utf-8')}
async function readFile(event:Event){
  const file=(event.target as HTMLInputElement).files?.[0];if(!file)return
  error.value=''
  if(file.size>1_000_000){error.value='文件超过1MB，请拆分并保留期初开仓衔接';return}
  const bytes=await file.arrayBuffer()
  try{csvText.value=new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch{csvText.value=new TextDecoder('gb18030').decode(bytes)}
  if(!sourceLabel.value)sourceLabel.value=file.name
}
async function analyze(){
  error.value=''
  if(!rights.value||!sourceLabel.value.trim()||!csvText.value.trim()){error.value='请填写资料名称、成交CSV，并确认使用权限';return}
  if(new TextEncoder().encode(csvText.value).length>1_000_000){error.value='输入超过1MB';return}
  const current=revision.value;busy.value=true
  try{result.value=await api.analyzeMentorLedger({csvText:csvText.value,sourceLabel:sourceLabel.value.trim(),sourceUrl:sourceUrl.value.trim(),rightsConfirmed:rights.value});analyzedRevision.value=current}
  catch(e){error.value=e instanceof Error?e.message:'分析未完成'}finally{busy.value=false}
}
</script>
<template>
  <section class="ledger-lab">
    <header><div><span class="eyebrow">有真实资料，再做逐笔检验</span><h3>成交记录分析台</h3></div><button type="button" @click="template">下载空白CSV模板</button></header>
    <p class="hint">接受公开或获授权的期货成交记录。只有点击分析时才发送到本系统后台处理，后台不保存原始CSV。来源和账户归属仍须人工核验；导入不会自动认证为某位前辈的交割单。</p>
    <form @submit.prevent="analyze">
      <div class="fields"><label>资料名称<input v-model="sourceLabel" maxlength="150" required placeholder="原始资料名称、期间及版本"/></label><label>原始公开链接（可选）<input v-model="sourceUrl" type="url" placeholder="https://…"/></label></div>
      <label class="file">读取CSV文件（UTF-8 / GB18030，≤1MB）<input type="file" accept=".csv,text/csv" @change="readFile"/></label>
      <label>成交CSV<textarea v-model="csvText" rows="7" required spellcheck="false" placeholder="使用上方空白模板，保留实际开平仓、乘数和手续费"/></label>
      <details><summary>列格式与配对口径</summary><p>time 为真实自然时间，推荐 ISO 格式并附时区；不带时区按北京时间。trading_day 为交易所交易日，平今/平昨必须填写；夜盘不能用自然日期代替。side：BUY/SELL；offset：OPEN/CLOSE/CLOSETODAY/CLOSEYESTERDAY。fee 是本条成交的总手续费。仅支持实际交割合约，乘数由你按原始记录填写。</p><p>按合约、方向和开平标签做 FIFO 配对；缺少期初持仓时会拒绝分析。平仓分摊开平手续费，未平仓不计浮盈亏。没有逐日权益和出入金，不能计算账户收益率、最大回撤或杠杆。</p></details>
      <label class="consent"><input v-model="rights" type="checkbox"/>我确认资料已公开或有权用于本次分析，并已移除姓名、账号等非必要信息</label>
      <button class="primary" type="submit" :disabled="busy">{{busy?'核对与配对中…':'分析成交记录'}}</button>
      <p v-if="error" role="alert" class="error">{{error}}</p>
    </form>
    <section v-if="result" class="result" aria-label="成交分析结果">
      <p v-if="stale" role="status" class="error">输入已变更：下面仍是上一次资料的结果，请重新分析。</p>
      <div class="report-title"><h4>{{result.sourceLabel}}</h4><span class="badge">用户提供 · 未独立认证 · 仅描述性分析</span><button type="button" :disabled="!!stale" @click="download(JSON.stringify(result,null,2),'成交分析报告.json','application/json')">导出分析报告</button></div>
      <div class="metrics"><article><span>配对平仓净损益（元）</span><strong>{{number(result.metrics.netClosedPnl)}}</strong></article><article><span>分摊的开平手续费（元）</span><strong>{{number(result.metrics.allocatedClosedFees)}}</strong></article><article><span>去掉最好配对片段（元）</span><strong>{{number(result.metrics.netWithoutBest1)}}</strong></article><article><span>手续费翻倍后的净损益（元）</span><strong>{{number(result.metrics.netAtDoubleClosedFees)}}</strong></article></div>
      <p class="hint">{{result.metrics.fillCount}} 条成交 / {{result.metrics.pairedFragments}} 个FIFO配对片段；片段不是独立交易。账户收益率与最大回撤：资料不足，不能计算。</p>
      <details open><summary>解释边界</summary><ul><li v-for="warning in result.warnings" :key="warning">{{warning}}</li></ul></details>
      <div class="table-wrap"><table><caption>分合约已平仓统计</caption><thead><tr><th>合约</th><th>平仓手数</th><th>毛损益</th><th>分摊手续费</th><th>净损益</th></tr></thead><tbody><tr v-for="c in contractRows" :key="c.contract"><td>{{c.contract}}</td><td>{{c.closedLots}}</td><td>{{number(c.grossPnl)}}</td><td>{{number(c.fees)}}</td><td>{{number(c.netPnl)}}</td></tr></tbody></table></div><Pagination v-model:page="contractPage" :page-size="10" :total="contractTotal" label="合约分析分页"/>
      <details><summary>查看FIFO配对与剩余持仓</summary><div class="table-wrap"><table><thead><tr><th>合约 / 方向</th><th>开仓时刻</th><th>平仓时刻</th><th>手数</th><th>开 / 平价格</th><th>净损益</th></tr></thead><tbody><tr v-for="(p,i) in paired" :key="i"><td>{{p.contract}} / {{p.direction==='LONG'?'多':'空'}}</td><td>{{formatTime(p.openedAt)}}</td><td>{{formatTime(p.closedAt)}}</td><td>{{p.quantity}}</td><td>{{p.entryPrice}} / {{p.exitPrice}}</td><td>{{number(p.netPnl)}}</td></tr></tbody></table></div><Pagination v-model:page="pairPage" :page-size="10" :total="pairTotal" label="成交配对分页"/><p v-if="!openTotal">无剩余未平仓持仓。</p><p v-for="p in openRows" :key="p.contract+p.direction">{{p.contract}} / {{p.direction}}：{{p.lots}} 手，未计浮盈亏。</p><Pagination v-model:page="openPage" :page-size="10" :total="openTotal" label="未平仓分页"/></details>
      <p class="hash">输入 SHA-256：{{result.inputSha256}}</p>
    </section>
  </section>
</template>
<style scoped>
.ledger-lab{padding:1.3rem;background:white;border:1px solid var(--color-line);border-radius:.7rem}header,.report-title{display:flex;align-items:center;justify-content:space-between;gap:.7rem;flex-wrap:wrap}.eyebrow{font-size:.66rem;color:var(--color-accent)}h3{font-size:1.1rem;margin:.5rem 0}button{padding:.6rem .85rem;border:1px solid var(--color-line);border-radius:.4rem;background:white;font-size:.72rem;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.primary{background:var(--color-accent);color:white}.hint,details{font-size:.73rem;line-height:1.9;color:var(--color-ink-secondary)}.fields{display:grid;grid-template-columns:1fr 1fr;gap:1rem}label{display:grid;gap:.5rem;font-size:.75rem;margin:.85rem 0}input,textarea{width:100%;box-sizing:border-box;padding:.65rem;border:1px solid var(--color-line);border-radius:.4rem;background:#fdfdfb;color:inherit;min-width:0}textarea{font: .75rem/1.7 monospace;resize:vertical}.consent{display:flex;align-items:flex-start;gap:.6rem;line-height:1.8}.consent input{width:auto;margin-top:.4rem}.file input{font-size:.7rem}.error{color:#a44d2e;font-size:.75rem;line-height:1.8}.result{margin-top:1.5rem;border-top:1px solid var(--color-line);padding-top:1rem}.badge{font-size:.65rem;background:#f5f0e3;color:#806338;padding:.4rem;border-radius:.3rem}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem}.metrics article{background:#f6f7f4;padding:.8rem;border-radius:.4rem}.metrics span{display:block;font-size:.66rem;line-height:1.8}.metrics strong{display:block;font:600 1.2rem var(--font-numeric);margin-top:.5rem;overflow-wrap:anywhere}summary{cursor:pointer;color:var(--color-accent)}.table-wrap{overflow:auto}table{font-size:.7rem;width:100%;text-align:left;border-collapse:collapse}th,td{padding:.6rem;border-bottom:1px solid var(--color-line);white-space:nowrap}caption{text-align:left;padding:.8rem 0}.hash{overflow-wrap:anywhere;font-size:.6rem;color:var(--color-ink-tertiary)}@media(max-width:800px){.metrics{grid-template-columns:1fr 1fr}.fields{grid-template-columns:1fr}}
</style>

<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import type {SettlementSnapshot} from '../types/mentors'
import Pagination from './Pagination.vue'
import {usePagination} from '../composables/usePagination'
import {formatNumber,formatTime} from '../utils/format'
const props=defineProps<{snapshot:SettlementSnapshot}>()
const selected=ref('')
watch(()=>props.snapshot.accounts,rows=>{if(!rows.some(a=>a.id===selected.value))selected.value=rows[0]?.id??''},{immediate:true})
const account=computed(()=>props.snapshot.accounts.find(a=>a.id===selected.value))
const rows=computed(()=>[...(account.value?.rows??[])].reverse())
const {items,page,total}=usePagination(rows,20,[selected])
const money=(value:unknown)=>value==null?'未披露':formatNumber(Number(value),2)
function exportData(){if(!account.value)return;const url=URL.createObjectURL(new Blob([JSON.stringify(account.value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`公开资金表-${account.value.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
</script>
<template>
  <section v-if="snapshot.accounts.length" class="settlement-evidence">
    <header><div><span class="eyebrow">公开日结算数据 / 独立对照样本</span><h3>权益、资金流与实际手续费</h3></div><label>账户<select v-model="selected" aria-label="选择资金表账户"><option v-for="a in snapshot.accounts" :key="a.id" :value="a.id">{{a.alias}}</option></select></label></header>
    <p>{{snapshot.publisher}} · 采集 {{formatTime(snapshot.fetchedAt)}}。{{snapshot.sampling}}</p>
    <template v-if="account">
      <div class="caption"><strong>{{account.alias}} · {{total}} 个日结算记录</strong><span>{{rows.at(-1)?.dateline}} — {{rows[0]?.dateline}}</span><button type="button" @click="exportData">导出公开资金表JSON</button><a :href="account.sourceUrl" target="_blank" rel="noopener noreferrer">核对主办方原页 ↗</a></div>
      <p class="boundary">{{account.rawTradesPublic?'原始明细权限状态已返回，具体明细尚未采集。':'主办方未开放此账户的逐笔成交明细，仅资金表公开。'}} 这些账户与上述前辈档案没有身份对应，不能据此替代某位前辈的交易记录。</p>
      <p v-if="account.checks">已披露手续费加总 {{money(account.checks.feeSum)}} 元，入金 {{money(account.checks.inSum)}} 元，出金 {{money(account.checks.outSum)}} 元。按下列现金校验式，{{account.checks.cashResidualRows}} 行差额超过0.01元；最大绝对差额 {{money(account.checks.maxAbsCashResidual)}} 元。</p>
      <p>校验差额＝当日结存－上日结存－入金＋出金－逐日盈亏＋手续费－权利金收支。差额保留原值，不自动归为费用；期权市值、质押及完整账单口径仍需另外核对。账户权益也不等同当日结存。</p>
      <div class="table-wrap"><table><thead><tr><th>日期</th><th>账户权益（元）</th><th>上日结存</th><th>当日结存</th><th>入金</th><th>出金</th><th>逐日盈亏</th><th>手续费</th><th>权利金收支</th><th>现金校验差额</th></tr></thead><tbody><tr v-for="r in items" :key="String(r.dateline)"><td>{{r.dateline}}</td><td>{{money(r.equity)}}</td><td>{{money(r.balance)}}</td><td>{{money(r.cbalance)}}</td><td>{{money(r.today_in)}}</td><td>{{money(r.today_out)}}</td><td>{{money(r.profit)}}</td><td>{{money(r.fee)}}</td><td>{{money(r.royalty)}}</td><td>{{money(r.cashResidual)}}</td></tr></tbody></table></div>
      <Pagination v-model:page="page" :page-size="20" :total="total" label="公开资金表分页"/>
      <details><summary>逐页来源与数据校验码</summary><a v-for="(url,i) in account.sourceUrls" :key="url" :href="url" target="_blank" rel="noopener noreferrer">公开原始资金表第{{i+1}}页 ↗</a><p class="hash">公开资金行规范JSON SHA-256：{{account.sourceSha256}}</p></details>
    </template>
  </section>
</template>
<style scoped>
.settlement-evidence{padding:1.2rem;background:white;border:1px solid var(--color-line);border-radius:.7rem;min-width:0}header,.caption{display:flex;justify-content:space-between;align-items:center;gap:.8rem;flex-wrap:wrap}.eyebrow{font-size:.66rem;color:var(--color-accent)}h3{font-size:1.1rem;margin:.5rem 0}p{font-size:.72rem;line-height:1.9;color:var(--color-ink-secondary)}label,.caption{font-size:.73rem}select,button{border:1px solid var(--color-line);border-radius:.4rem;background:white;padding:.5rem;font:inherit}.boundary{padding:.75rem;background:#f5f0e3;border-radius:.4rem}a{font-size:.7rem;color:var(--color-accent);margin-right:.8rem}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:.72rem}th,td{padding:.65rem;border-bottom:1px solid var(--color-line);white-space:nowrap}details{font-size:.72rem}summary{cursor:pointer;margin:.75rem 0}.hash{overflow-wrap:anywhere;font-size:.65rem}
</style>

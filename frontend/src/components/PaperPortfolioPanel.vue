<script setup lang="ts">
import {ref} from 'vue'
import type {BacktestPresets,PaperSession,PaperPortfolioPosition} from '../services/api'
import {formatNumber,formatTime} from '../utils/format'
const props=defineProps<{session:PaperSession;presets:BacktestPresets|null;busy:boolean}>()
const emit=defineEmits<{select:[symbol:string];close:[position:PaperPortfolioPosition]}>()
const symbol=ref('')
function select(){
  const value=symbol.value.trim().toUpperCase()
  const knownRoot=props.presets?.symbols.find(item=>item.symbol===value+'0'||item.symbol===value+'M')
  if(value)emit('select',knownRoot?.symbol??(/^[A-Z]{1,4}$/.test(value)&&!value.endsWith('M')?value+'0':value))
}
function quoteState(p:PaperPortfolioPosition){return p.marketState==='LIVE'?'最近实时估值':p.marketState==='CLOSED_CACHE'?'休市行情':p.marketState==='UNAVAILABLE'?'行情不可用 · 保留上次估值':'行情延迟 · 保留观测'}
</script>

<template>
  <section class="portfolio-panel" aria-label="多品种共用资金账户">
    <div class="portfolio-heading"><div><small>ONE ACCOUNT · MULTIPLE INSTRUMENTS</small><h3>一个账户，多个品种</h3></div><span>共用资金 · {{session.positions?.length??(session.position.lots?1:0)}} 个持仓合约</span></div>
    <form class="instrument-picker" @submit.prevent="select">
      <label>品种或实际合约<input v-model="symbol" list="paper-instrument-catalog" aria-label="添加或切换品种" placeholder="如 FG0、RB0，或 FG701" :disabled="busy" required pattern="[A-Za-z]{1,4}(0|M|[0-9]{3,4})?" /></label>
      <datalist id="paper-instrument-catalog"><option v-for="item in presets?.symbols??[]" :key="item.symbol" :value="item.symbol">{{item.name}} · {{item.exchange}}</option></datalist>
      <button type="submit" :disabled="busy||!symbol.trim()">添加 / 切换品种</button>
      <p>切换只更换图表和下单合约，已有持仓继续保留。主力代码会解析为当前实际合约。</p>
    </form>
    <nav class="instrument-tabs" aria-label="账户内合约"><button v-for="p in session.instruments??[]" :key="p.contract" type="button" :aria-pressed="session.currentContract===p.contract" :disabled="busy" @click="emit('select',p.contract)">{{p.contract}}<span v-if="p.lots"> · {{p.direction>0?'多':'空'}} {{p.lots}}手</span></button></nav>
    <div v-if="session.multiInstrument" class="portfolio-table"><table aria-label="全部品种持仓"><thead><tr><th>实际合约</th><th>方向 / 手数</th><th>持仓均价</th><th>估值价格</th><th>浮动盈亏</th><th>保证金</th><th>行情与时间</th><th>操作</th></tr></thead><tbody>
      <tr v-for="p in session.positions??[]" :key="p.contract"><td><button type="button" :disabled="busy" @click="emit('select',p.contract)">{{p.contract}}</button></td><td>{{p.direction>0?'多':'空'}} / {{p.lots}}</td><td>{{formatNumber(p.averagePrice,2)}}</td><td>{{formatNumber(p.currentPrice,2)}}</td><td :class="p.unrealizedPnl>=0?'up':'down'">{{formatNumber(p.unrealizedPnl,2)}}</td><td>¥{{formatNumber(p.marginOccupied,2)}}</td><td><span>{{quoteState(p)}}</span><small>{{formatTime(p.marketTime)}}</small></td><td><button type="button" :disabled="busy" @click="emit('close',p)">选择平仓</button></td></tr>
      <tr v-if="!session.positions?.length"><td colspan="8" class="empty">账户暂无持仓，可在同一资金账户内切换品种开仓。</td></tr>
    </tbody></table></div>
    <p class="valuation">{{session.multiInstrument?'账户总权益包含全部持仓；开仓挂单预留 ¥'+formatNumber(session.reservedCash??0,2)+'。':'首次添加或切换将保留原资金、持仓及交易记录。'}}<span v-if="session.portfolioValuedAt"> 最近汇总 {{formatTime(session.portfolioValuedAt)}}。</span>使用“刷新账户估值”更新全部持仓并检查挂单。</p>
  </section>
</template>

<style scoped>
.portfolio-panel{min-width:0;padding:1.1rem 1.25rem;border:1px solid var(--color-line);border-radius:.75rem;background:#fbfcf9}.portfolio-heading{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}.portfolio-heading small{font-size:.6rem;letter-spacing:.12em;color:#55746a}.portfolio-heading h3{font-size:1rem;margin:.3rem 0 .8rem}.portfolio-heading>span{font-size:.72rem;color:#45675b}.instrument-picker{display:flex;align-items:flex-end;gap:.7rem;flex-wrap:wrap}.instrument-picker label{display:grid;gap:.35rem;font-size:.7rem}.instrument-picker input{padding:.65rem;border:1px solid #b9cfc4;border-radius:.4rem;width:16rem;max-width:100%;background:white}.portfolio-panel button{padding:.55rem .75rem;border:1px solid #b9cfc4;border-radius:.4rem;background:white;color:#235747;cursor:pointer;font-size:.7rem}.portfolio-panel button:disabled{opacity:.5;cursor:wait}.instrument-picker>button{background:#235747;color:white}.instrument-picker p,.valuation{font-size:.69rem;color:var(--color-ink-secondary);line-height:1.7;margin:.4rem 0}.instrument-tabs{display:flex;gap:.4rem;flex-wrap:wrap;margin:.8rem 0}.instrument-tabs button[aria-pressed=true]{background:#e2eee7;border-color:#618c79}.portfolio-table{overflow-x:auto;width:100%;margin:.6rem 0}table{border-collapse:collapse;width:100%;font-size:.7rem;white-space:nowrap}th,td{text-align:left;padding:.7rem .6rem;border-bottom:1px solid var(--color-line)}th{color:var(--color-ink-secondary);font-weight:500}td small{display:block;margin-top:.3rem;font-size:.6rem;color:var(--color-ink-secondary)}.empty{text-align:center;padding:1.5rem;color:var(--color-ink-secondary)}.up{color:var(--color-positive)}.down{color:var(--color-negative)}@media(max-width:600px){.portfolio-panel{padding:.85rem}.instrument-picker label{width:100%}.instrument-picker input{width:100%;box-sizing:border-box}.instrument-picker>button{width:100%}}
</style>

<script setup lang="ts">
import {onMounted,onUnmounted,ref,watch} from 'vue'
import {monitoringApi,type MonitorAsset,type MonitorHistory} from '../services/monitoring'
import {instrumentLabel} from '../utils/instrumentNames'
import {formatTime} from '../utils/format'
const props=withDefaults(defineProps<{assetType?:MonitorAsset;paused?:boolean}>(),{assetType:'FUTURE',paused:false})
defineEmits<{configure:[]}>()
const items=ref<MonitorHistory[]>([]),query=ref(''),page=ref(1),total=ref(0),loading=ref(false),error=ref(''),detail=ref<MonitorHistory|null>(null)
let alive=true,ticket=0,timer:number|undefined
const statuses:Record<string,string>={READY:'正常',WARMING:'预热中',STALE:'休市 / 数据过时',ERROR:'检查失败',FORBIDDEN:'权限不可用',EXPIRED:'已到期'}
function metric(row:MonitorHistory,key:string){const value=row.metrics[key];return typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('zh-CN',{maximumFractionDigits:4}):'—'}
async function load(){
 if(loading.value)return
 const current=++ticket;loading.value=true;error.value=''
 try{const result=await monitoringApi.history(props.assetType,query.value,page.value);if(alive&&current===ticket){items.value=result.items;total.value=result.total}}
 catch(e){if(alive&&current===ticket)error.value=e instanceof Error?e.message:'历史记录读取失败'}
 finally{if(alive&&current===ticket)loading.value=false}
}
function search(){page.value=1;void load()}
function turn(delta:number){page.value+=delta;void load()}
watch(()=>props.assetType,()=>{++ticket;loading.value=false;items.value=[];detail.value=null;page.value=1;void load()})
watch(()=>props.paused,value=>{if(!value)void load()})
onMounted(()=>{void load();timer=window.setInterval(()=>{if(!document.hidden&&!props.paused)void load()},15000)})
onUnmounted(()=>{alive=false;++ticket;window.clearInterval(timer)})
</script>
<template>
 <section class="history-panel" aria-label="历史盘口监控">
  <h3>历史盘口监控 · 每分钟留档</h3>
  <button @click="$emit('configure')">配置监控合约</button>
  <p>在“期货后台监控”启用需要跟踪的合约，服务器每 60 秒保存一次检查结果，关闭页面仍持续运行。首次检查开始记录，不补造过去数据；暂停或归档任务后停止采样。</p>
  <p>量价、MA5/10/20/60/180、MACD、布林、ATR、挂单量及价差按任务周期计算；技术指标使用已确认收盘的 K 线。休市、断线、权限异常也会留档，缺失值显示 —。</p>
  <form @submit.prevent="search"><input v-model="query" aria-label="搜索历史盘口" placeholder="合约或任务名称" maxlength="100"/><button :disabled="loading">查询历史</button><button type="button" :disabled="loading" @click="load">刷新记录</button><span>{{total}} 条</span></form>
  <p v-if="error" role="alert">{{error}}</p>
  <div class="history-scroll"><table><thead><tr><th>检查时间 / 源时间</th><th>合约 / 任务</th><th>状态</th><th>最新价 / 完整柱量</th><th>量比 / 60 秒涨跌%</th><th>MA5 / MA20</th><th>DIF / DEA</th><th>盘口失衡 / 价差</th><th>依据</th></tr></thead><tbody>
   <tr v-for="row in items" :key="row.id"><td>{{formatTime(row.checkedAt)}}<small>{{formatTime(row.sourceTimestamp)}}</small></td><td>{{instrumentLabel(row.symbol)}}<small>{{row.name}} · {{row.seconds/60}} 分钟</small></td><td>{{statuses[row.status]??row.status}}<small>{{row.message}}</small></td><td>{{metric(row,'lastPrice')}} / {{metric(row,'volume')}}</td><td>{{metric(row,'volumeRatio')}} / {{metric(row,'change60sPct')}}</td><td>{{metric(row,'ma5')}} / {{metric(row,'ma20')}}</td><td>{{metric(row,'dif')}} / {{metric(row,'dea')}}</td><td>{{metric(row,'depthImbalance')}} / {{metric(row,'spread')}}</td><td><button @click="detail=row">检查详情</button></td></tr>
  </tbody></table></div>
  <p v-if="!items.length">{{loading?'正在读取…':'还没有历史快照。启用合约监控后等待首次检查；无触发也会记录。'}}</p>
  <footer><span>第 {{page}} 页</span><button :disabled="page<=1||loading" @click="turn(-1)">上一页</button><button :disabled="page*20>=total||loading" @click="turn(1)">下一页</button></footer>
  <section v-if="detail" aria-label="历史检查详情"><h4>{{instrumentLabel(detail.symbol)}} · {{formatTime(detail.checkedAt)}}</h4><button @click="detail=null">关闭详情</button><p>任务版本 {{detail.monitorVersion}} · {{detail.algorithmVersion}} · 信号仅为该次检查结果，完整告警见后台监控触发记录。</p><pre>{{JSON.stringify({metrics:detail.metrics,parameters:detail.parameters,signals:detail.signals},null,2)}}</pre></section>
 </section>
</template>
<style scoped>
.history-panel{padding:1rem;background:#182430;border:1px solid #354b5d;border-radius:7px;min-width:0}.history-panel h3{font-size:.95rem}.history-panel p{font-size:.68rem;line-height:1.9;color:#a7bac8}.history-panel form,.history-panel footer{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:1rem 0;font-size:.7rem}.history-panel input{background:#101d28;color:#dce6ed;border:1px solid #354b5d;padding:.6rem;border-radius:4px;min-width:0}.history-panel button{background:#203140;border:1px solid #3a5061;color:#dce6ed;padding:.45rem;border-radius:4px;cursor:pointer}.history-panel button:disabled{opacity:.45}.history-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.65rem}th,td{text-align:left;padding:.8rem;border-bottom:1px solid #354b5d;min-width:7rem}th{color:#a7bac8;font-weight:400}small{display:block;margin-top:.4rem;color:#94a5b6;line-height:1.7}.history-panel pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:30rem;overflow:auto;font-size:.65rem;background:#101d28;padding:1rem}.history-panel footer{justify-content:flex-end}
</style>

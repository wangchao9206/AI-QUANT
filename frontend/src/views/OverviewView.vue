<script setup lang="ts">
import {computed,onMounted,onUnmounted,reactive,ref} from 'vue'
import {ArrowUpRight,Flame,Globe2,Newspaper,Radar,RefreshCw,ScanLine} from 'lucide-vue-next'
import Pagination from '../components/Pagination.vue'
import {usePagination} from '../composables/usePagination'
import DataPanel from '../components/DataPanel.vue'
import {api,type LeadsResponse} from '../services/api'
import type {MarketRadar,NewsRadar,SignalRadar,OverseasRadar,RadarBase} from '../types/radar'
import {formatNumber,formatPct,formatTime,formatTradingDate} from '../utils/format'
import {useExperience} from '../composables/useExperience'
import {instrumentPath,researchPath} from '../utils/marketNavigation'
import {useMarketStore} from '../stores/market'

const {isSimple}=useExperience()
const market=ref<MarketRadar|null>(null),news=ref<NewsRadar|null>(null),signals=ref<SignalRadar|null>(null),overseas=ref<OverseasRadar|null>(null),leads=ref<LeadsResponse|null>(null)
type Module='market'|'news'|'signals'|'overseas'|'leads'
const modules:Module[]=['market','news','signals','overseas','leads']
const loading=reactive<Record<Module,boolean>>({market:false,news:false,signals:false,overseas:false,leads:false})
const errors=reactive<Record<Module,string>>({market:'',news:'',signals:'',overseas:'',leads:''})
const busy=computed(()=>modules.some(k=>loading[k]))
const store=useMarketStore()
const ranking=ref('volume'),sector=ref('全部板块'),newsTopic=ref('全部'),strategyFilter=ref('ALL')
const sectors=computed(()=>['全部板块',...(market.value?.sectors?.map(i=>i.name)??[])])
const allRanked=computed(()=>{
  const rows=(market.value?.items??[]).filter(i=>sector.value==='全部板块'||i.sector===sector.value)
  return [...rows].sort((a,b)=>ranking.value==='gainers'?b.changePct-a.changePct:ranking.value==='losers'?a.changePct-b.changePct:(b.volume??0)-(a.volume??0))
})
const allHeadlines=computed(()=>(news.value?.items??[]).filter(i=>newsTopic.value==='全部'||i.topic===newsTopic.value).sort((a,b)=>Number(b.sourceTier==='PRIMARY')-Number(a.sourceTier==='PRIMARY')))
const filteredSignals=computed(()=>(signals.value?.items??[]).filter(i=>strategyFilter.value==='ALL'||i.strategy===strategyFilter.value))
const {items:signalRows,page:signalPage,total:signalTotal}=usePagination(filteredSignals,8,[strategyFilter])
const allLeads=computed(()=>(leads.value?.leads??[]).filter(i=>i.algorithmType!=='CYCLE_PIVOT'))
const {items:activeLeads,page:leadPage,total:leadTotal}=usePagination(allLeads,6)
const {items:headlines,page:newsPage,total:newsTotal}=usePagination(allHeadlines,7,[newsTopic])
const {items:ranked,page:marketPage,total:marketTotal}=usePagination(allRanked,8,[ranking,sector])
const {items:foreignItems,page:foreignPage,total:foreignTotal}=usePagination(computed(()=>overseas.value?.items??[]),6)
const pctClass=(v:number)=>v>0?'positive':v<0?'negative':'neutral'
const compact=(v:number)=>v>=1e8?`${formatNumber(v/1e8,2)}亿`:v>=1e4?`${formatNumber(v/1e4,1)}万`:formatNumber(v,0)
const marketTo=(symbol:string)=>({path:instrumentPath(symbol)})
const strategyTo=(symbol:string)=>({path:researchPath(symbol),hash:'#trade-plan'})
const sourceTime=(v:RadarBase|null)=>v?.dataTimestamp?formatTime(v.dataTimestamp):'等待观测'
const status=(v:RadarBase|null)=>!v?'待加载':({READY:'已接入',PARTIAL:'部分覆盖',DEGRADED:'保留旧快照',UNAVAILABLE:'暂不可用'}[v.status])
let alive=true;let timer:number|undefined
async function load(module:Module){
  if(loading[module])return
  loading[module]=true;errors[module]=''
  try{
    if(module==='market'){const v=await api.radarMarket();if(alive)market.value=v}
    if(module==='news'){const v=await api.radarNews();if(alive)news.value=v}
    if(module==='signals'){const v=await api.radarSignals();if(alive)signals.value=v}
    if(module==='overseas'){const v=await api.radarOverseas();if(alive)overseas.value=v}
    if(module==='leads'){const v=await api.leads();if(alive)leads.value=v}
  }catch(e){if(alive)errors[module]=e instanceof Error?e.message:'暂不可用'}
  finally{if(alive)loading[module]=false}
}
async function refresh(){await Promise.allSettled(modules.map(load))}
onMounted(()=>{if(!store.catalog)void store.loadCatalog();void refresh();timer=window.setInterval(()=>{if(!document.hidden&&!busy.value)void refresh()},60000)})
onUnmounted(()=>{alive=false;window.clearInterval(timer)})
</script>

<template>
  <div class="page-stack market-overview">
    <section class="desk-intro">
      <div><p class="eyebrow">MARKET INTELLIGENCE / 全市场工作台</p><h2>{{isSimple?'了解今天的市场。':'先看市场，再找交易。'}}</h2><p class="intro-copy">{{isSimple?'从价格和新闻了解变化，想深入时再查看线索与研究，不必一开始就使用专业参数。':'跨品种观察热度、事件与策略条件，将值得跟踪的变化带入研究计划。'}}</p></div>
      <div class="desk-actions"><span>每 60 秒更新 · 各模块独立核验</span><button type="button" class="refresh" :disabled="busy" @click="refresh"><RefreshCw :size="15" :class="{spinning:busy}"/>{{busy?'更新中':'刷新雷达'}}</button></div>
    </section>
    <nav v-if="isSimple" class="starter-links" aria-label="第一次使用"><RouterLink to="/market">浏览多个品种 ↗</RouterLink><RouterLink to="/learn">先读懂常见术语 ↗</RouterLink><RouterLink to="/paper">用虚拟资金练习 ↗</RouterLink></nav>
    <nav class="radar-jumps" aria-label="总览雷达导航"><a href="#hot"><Flame :size="15"/>热门品种</a><a href="#news"><Newspaper :size="15"/>新闻雷达</a><a href="#leads"><Radar :size="15"/>线索雷达</a><a href="#strategies"><ScanLine :size="15"/>策略雷达</a><a href="#overseas"><Globe2 :size="15"/>外盘雷达</a></nav>
    <section class="market-pulse" aria-label="市场广度">
      <div class="pulse-title"><span>境内市场快照</span><strong>{{market?.observedCount??'—'}}<small> / {{market?.catalogCount??'—'}} 品种</small></strong><span>{{sourceTime(market)}} · {{status(market)}}</span></div>
      <div><span>上涨品种</span><strong class="positive">{{market?.breadth?.up??'—'}}</strong><small>相对各自昨结算</small></div>
      <div><span>下跌品种</span><strong class="negative">{{market?.breadth?.down??'—'}}</strong><small>按品种去重</small></div>
      <div><span>平盘 / 未覆盖</span><strong>{{market?.breadth?.flat??'—'}}<em> / {{market?.missingCount??'—'}}</em></strong><small>未覆盖不计入涨跌家数</small></div>
      <div><span>策略条件触发</span><strong>{{signals?.items.length??'—'}}<small> 条</small></strong><small>{{signals?.scannedCount??'—'}} 个品种 · 日线条件</small></div>
    </section>

    <DataPanel id="hot" title="热门品种" eyebrow="01 / MARKET HEAT · 活跃度与涨跌榜">
      <template #actions><button class="quiet" type="button" :disabled="loading.market" @click="load('market')">{{loading.market?'核验中':'更新行情'}}</button></template>
      <div class="module-tools"><div class="segmented" role="group" aria-label="品种榜排序"><button type="button" :aria-pressed="ranking==='volume'" @click="ranking='volume'">成交活跃</button><button type="button" :aria-pressed="ranking==='gainers'" @click="ranking='gainers'">涨幅榜</button><button type="button" :aria-pressed="ranking==='losers'" @click="ranking='losers'">跌幅榜</button></div><select v-model="sector" aria-label="品种榜板块"><option v-for="name in sectors" :key="name">{{name}}</option></select></div>
      <p v-if="errors.market||market?.status==='UNAVAILABLE'" class="module-error" role="alert">{{errors.market||market?.message}} <button type="button" @click="load('market')">重试行情</button></p>
      <p v-else-if="loading.market&&!market" class="empty" role="status">正在读取全市场主连快照…</p>
      <div v-if="ranked.length" class="heat-grid"><RouterLink v-for="(item,index) in ranked" :key="item.symbol" :to="marketTo(item.symbol)" class="heat-card"><div class="card-top"><small>{{String(index+1).padStart(2,'0')}} / {{item.sector}}</small><ArrowUpRight :size="14"/></div><div class="heat-name"><strong>{{item.name}}</strong><span>{{item.symbol}}</span></div><div class="price-row"><b>{{formatNumber(item.price)}}</b><strong :class="pctClass(item.changePct)">{{formatPct(item.changePct)}}</strong></div><div class="card-bottom"><span>成交 {{compact(item.volume??0)}} 手</span><span>{{item.exchange}}</span></div><div class="quote-time"><span>{{item.dataStatus==='FRESH'?'近时快照':item.dataStatus==='DEGRADED'?'降级快照':'缓存快照'}}</span><time>{{formatTime(item.dataTimestamp)}}</time></div></RouterLink></div>
      <p v-else-if="market&&market.status!=='UNAVAILABLE'" class="empty">当前板块暂无有效品种快照。</p>
      <div class="module-footer"><p>{{market?.message??'每个品种仅取一个主连，按成交手数排序；热度不等于资金流入或交易建议。'}} <span v-if="market?.source">来源：{{market.source}}</span></p></div>
      <Pagination v-model:page="marketPage" :page-size="8" :total="marketTotal" label="热门品种分页" /><div v-if="market?.sectors?.length" class="sector-strip" aria-label="板块等权观察"><button v-for="item in market.sectors" :key="item.name" type="button" :aria-pressed="sector===item.name" @click="sector=sector===item.name?'全部板块':item.name"><span>{{item.name}} <small>{{item.count}} 品种</small></span><b :class="pctClass(item.averageChange)">{{formatPct(item.averageChange)}}</b></button></div>
    </DataPanel>

    <div class="radar-columns">
      <DataPanel id="news" title="新闻雷达" eyebrow="02 / EVENT WATCH · 跨品种事件">
        <template #actions><span class="source-state">{{status(news)}}</span></template>
        <div class="segmented topic-tabs" role="group" aria-label="新闻分类"><button v-for="topic in ['全部','宏观政策','交易规则','产业资讯','海外事件']" :key="topic" type="button" :aria-pressed="newsTopic===topic" @click="newsTopic=topic">{{topic}}</button></div>
        <p v-if="errors.news||news?.status==='UNAVAILABLE'" class="module-error" role="alert">{{errors.news||news?.message}} <button type="button" @click="load('news')">重试新闻</button></p>
        <p v-else-if="loading.news&&!news" class="empty" role="status">正在拉取跨品种期货资讯…</p>
        <p v-if="news?.status==='DEGRADED'" class="module-error">{{news.message}}</p>
        <div class="news-list"><article v-for="item in headlines" :key="item.id"><div class="news-meta"><span>{{item.topic}}</span><time>{{item.timePrecision==='DAY'?item.publishedAt.slice(0,10)+'（日期）':formatTradingDate(item.publishedAt)+' '+formatTime(item.publishedAt).slice(-8,-3)}}</time></div><a :href="item.url" target="_blank" rel="noopener noreferrer" class="headline">{{item.title}} <ArrowUpRight :size="13"/></a><p v-if="item.summary">{{item.summary}}</p><div class="news-source"><span>{{item.sourceTier==='PRIMARY'?'一手发布 · ':'媒体汇编 · '}}{{item.publisher}}</span><RouterLink v-for="symbol in item.relatedSymbols.slice(0,3)" :key="symbol" :to="marketTo(symbol)">{{symbol}} ↗</RouterLink></div></article></div>
        <p v-if="news&&!headlines.length&&news.status!=='UNAVAILABLE'" class="empty">此分类暂无新闻，切换“全部”查看其他事件。</p>
        <Pagination v-model:page="newsPage" :page-size="7" :total="newsTotal" label="总览新闻分页" /><RouterLink to="/news" class="text-link">消息解读、来源状态与历史案例 ↗</RouterLink>
      <p class="module-note">{{news?.source}} · 官方来源优先 · 原文时间 {{news?.dataTimestamp?sourceTime(news).slice(0,-3):'待观测'}}。品种关联为规则提示，进入消息中心核对传导条件与反证。</p>
      </DataPanel>
      <DataPanel id="leads" title="线索雷达" eyebrow="03 / OPPORTUNITY WATCH · 待核验变化">
        <template #actions><RouterLink to="/leads" class="text-link">完整线索池 ↗</RouterLink></template>
        <div class="lead-scope"><Radar :size="16"/><span>{{leads?.scannedCount??'—'}} 个候选品种扫描 · {{leads?.leadsCount??'—'}} 条原始线索</span></div>
        <p v-if="errors.leads" class="module-error" role="alert">{{errors.leads}} <button type="button" @click="load('leads')">重试线索</button></p>
        <p v-else-if="loading.leads&&!leads" class="empty" role="status">正在独立扫描量价、供需与期限结构线索…</p>
        <div class="lead-list"><RouterLink v-for="item in activeLeads" :key="item.id" :to="strategyTo(item.symbol)" class="lead-card"><div><span class="lead-badge">{{item.algorithmBadge}}<em v-if="(item.direction==='BULLISH'&&item.compositeScore<0)||(item.direction==='BEARISH'&&item.compositeScore>0)" class="disagreement">方向分歧</em></span><small>{{item.exchange}} · {{item.symbol}}</small></div><h3>{{item.displayName}}<span :class="item.direction==='BULLISH'?'positive':item.direction==='BEARISH'?'negative':'neutral'">{{item.direction==='BULLISH'?'偏多观察':item.direction==='BEARISH'?'偏空观察':'中性观察'}}</span></h3><p>{{item.analysis.coreAnomaly}}</p><footer><time>{{formatTime(item.dataTimestamp??item.discoveredAt)}}</time><span>核验研究与风险 <ArrowUpRight :size="12"/></span></footer></RouterLink></div>
        <p v-if="leads&&!activeLeads.length" class="empty">本轮未发现可展示的实证线索。保留观察，不强行生成机会。</p>
        <Pagination v-model:page="leadPage" :page-size="6" :total="leadTotal" label="总览线索分页" /><p class="module-note">文化周期类线索保留在完整线索池。此处原始线索评分可能含文化参考，触发方向也可能与综合方向相反；进入实证研究后重新核算，不解释为胜率。扫描时间 {{leads?formatTime(leads.dataTimestamp):'待扫描'}}。</p>
      </DataPanel>
    </div>

    <DataPanel id="strategies" title="策略雷达" eyebrow="04 / STRATEGY SCAN · 哪些条件正在触发">
      <template #actions><RouterLink to="/backtest" class="text-link">策略回测与成本验证 ↗</RouterLink></template>
      <p class="strategy-scope">扫描 {{signals?.scannedCount??'—'}} / {{signals?.universeCount??'—'}} 个品种 · {{signals?.missingCount??'—'}} 个缺数或日期过旧 · 日线日期 {{signals?.dataTimestamp?.slice(0,10)??'待观测'}} · {{status(signals)}}</p>
      <p v-if="errors.signals||signals?.status==='UNAVAILABLE'" class="module-error" role="alert">{{errors.signals||signals?.message}} <button type="button" @click="load('signals')">重试策略</button></p>
      <p v-else-if="loading.signals&&!signals" class="empty" role="status">正在读取已完成日线并核验策略条件…</p>
      <div class="strategy-groups"><button v-for="item in signals?.groups??[]" :key="item.id" type="button" :aria-pressed="strategyFilter===item.id" @click="strategyFilter=strategyFilter===item.id?'ALL':item.id"><span>{{item.name}} <b>{{item.matched}}<small> 条触发</small></b></span><p>{{item.rule}}</p><footer><em class="positive">偏多 {{item.long}}</em><em class="negative">偏空 {{item.short}}</em><span>{{strategyFilter===item.id?'再次点击看全部':'筛选条件'}}</span></footer></button></div>
      <details class="signal-disclosure" :open="!isSimple"><summary>查看具体品种、触发阈值与日线日期</summary>
      <div v-if="signalRows.length" class="signal-table-wrap"><table class="signal-table"><caption>已完成主连日线的空仓入场条件 · {{strategyFilter==='ALL'?'全部策略':'已筛选策略'}}</caption><thead><tr><th>品种 / 策略</th><th>条件方向</th><th>观测收盘</th><th>下轨 / 上轨</th><th>日线日期</th><th>下一步</th></tr></thead><tbody><tr v-for="item in signalRows" :key="item.id"><td><strong>{{item.name}} <small>{{item.symbol}}</small></strong><span>{{signals?.groups?.find(g=>g.id===item.strategy)?.name}}</span></td><td :class="item.signal==='BUY'?'positive':'negative'">{{item.signal==='BUY'?'偏多条件':'偏空条件'}}</td><td>{{formatNumber(item.close,3)}}</td><td>{{formatNumber(item.lower,3)}} / {{formatNumber(item.upper,3)}}</td><td>{{item.dataTimestamp.slice(0,10)}}</td><td><RouterLink :to="strategyTo(item.symbol)">核验计划 ↗</RouterLink></td></tr></tbody></table></div>
      <p v-else-if="signals&&signals.status!=='UNAVAILABLE'" class="empty">所选策略当前没有入场条件触发。</p>
      <div v-if="filteredSignals.length" class="module-footer"><p>当前展示 {{signalRows.length}} / {{filteredSignals.length}} 条触发；点击策略卡片筛选。</p><Pagination v-model:page="signalPage" :page-size="8" :total="signalTotal" label="总览策略分页" /></div>
      </details>
      <p class="module-note">{{signals?.message??'仅扫描日线入场条件；账户、持仓、实际交割合约与成交约束在研究计划中另行核验。'}} {{signals?.status==='DEGRADED'?'当前为上次成功扫描快照。':''}}</p>
    </DataPanel>

    <DataPanel id="overseas" title="外盘雷达" eyebrow="05 / GLOBAL CONTEXT · 产业链关联观察">
      <template #actions><button class="quiet" type="button" :disabled="loading.overseas" @click="load('overseas')">{{loading.overseas?'拉取中':'更新外盘'}}</button></template>
      <p v-if="errors.overseas||overseas?.status==='UNAVAILABLE'" class="module-error" role="alert">{{errors.overseas||overseas?.message}} <button type="button" @click="load('overseas')">重试外盘</button></p>
      <p v-else-if="loading.overseas&&!overseas" class="empty" role="status">正在拉取黄金、原油、铜与农产品外盘参考…</p>
      <div class="overseas-grid"><article v-for="item in foreignItems" :key="item.symbol"><div class="card-top"><span>{{item.sector}} / {{item.symbol}}</span><small>{{item.dataStatus==='FRESH'?'近时参考':'缓存参考'}}</small></div><a :href="item.sourceUrl" target="_blank" rel="noopener noreferrer">{{item.name}} <ArrowUpRight :size="13"/></a><div class="price-row"><b>{{formatNumber(item.price,3)}}</b><strong :class="pctClass(item.changePct)">{{formatPct(item.changePct)}}</strong></div><small>{{item.unit}} · 相对源昨结算</small><time>北京时间 {{formatTime(item.dataTimestamp)}}</time><div class="related"><span>境内关联</span><RouterLink v-for="symbol in item.relatedSymbols.slice(0,3)" :key="symbol" :to="marketTo(symbol)">{{symbol}} ↗</RouterLink></div></article></div>
      <Pagination v-model:page="foreignPage" :page-size="6" :total="foreignTotal" label="总览外盘分页" /><p class="module-note">{{overseas?.source??'新浪财经外盘参考行情'}} · {{status(overseas)}}。{{overseas?.message??'含 CFD / 参考报价，非交易所授权实时盘口；关联为产业链提示，不代表相关系数或套利信号。'}}<span v-if="overseas?.missing?.length"> 未取得：{{overseas.missing.join('、')}}。</span></p>
    </DataPanel>
  </div>
</template>

<style scoped>
.starter-links{display:flex;gap:1.2rem;flex-wrap:wrap;font-size:.72rem}.starter-links a{color:var(--color-accent);text-decoration:none}.signal-disclosure{margin-top:1rem;min-width:0}.signal-disclosure>summary{cursor:pointer;font-size:.75rem;color:var(--color-accent);padding:.6rem 0}

.disagreement{display:inline-block;font-style:normal;color:var(--color-warning);background:var(--color-warning-soft);border-radius:.25rem;padding:.15rem .3rem;margin-left:.4rem;font-size:.56rem}
.market-overview{gap:1.3rem}.market-overview :deep(section[id]){scroll-margin-top:1rem}.desk-intro{display:flex;justify-content:space-between;align-items:end;gap:1.5rem;padding:.4rem 0}.eyebrow{color:var(--color-accent);font-size:.65rem;letter-spacing:.12em;font-weight:700}.desk-intro h2{font:500 clamp(1.7rem,3vw,2.5rem) var(--font-display);letter-spacing:-.035em;margin:.6rem 0}.intro-copy{margin:.7rem 0 0;color:var(--color-ink-secondary);font-size:.8rem;line-height:1.8}.desk-actions{display:grid;justify-items:end;gap:.7rem;flex-shrink:0}.desk-actions>span{color:var(--color-ink-tertiary);font-size:.63rem}.refresh,.quiet{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;border:1px solid var(--color-line-strong);background:var(--color-surface);color:var(--color-accent);border-radius:.6rem;padding:.6rem .8rem;font-size:.72rem;cursor:pointer}.refresh{color:white;background:var(--color-accent);border-color:var(--color-accent)}button:disabled{opacity:.5;cursor:wait}.radar-jumps{display:flex;flex-wrap:wrap;gap:.6rem}.radar-jumps a{display:flex;align-items:center;gap:.45rem;padding:.55rem .8rem;border:1px solid var(--color-line);border-radius:2rem;text-decoration:none;font-size:.7rem;color:var(--color-ink-secondary);background:var(--color-surface)}
.market-pulse{display:grid;grid-template-columns:1.4fr repeat(4,minmax(0,1fr));border:1px solid #313a40;border-radius:1rem;background:#1b242b;color:white;padding:1.3rem 0}.market-pulse>div{display:grid;gap:.55rem;padding:.15rem 1.4rem;border-right:1px solid #394148;min-width:0}.market-pulse>div:last-child{border:0}.market-pulse span,.market-pulse small{font-size:.64rem;color:#bac4ca;line-height:1.6}.market-pulse strong{font:500 1.8rem var(--font-numeric)}.market-pulse strong small,.market-pulse em{font:400 .67rem var(--font-sans);color:#bac4ca}.market-pulse .positive{color:#ff8c83}.market-pulse .negative{color:#7ac89a}
.module-tools{display:flex;justify-content:space-between;gap:1rem;margin-bottom:1rem}.segmented{display:flex;gap:.3rem;flex-wrap:wrap}.segmented button{border:0;border-radius:.45rem;background:transparent;color:var(--color-ink-secondary);padding:.55rem .8rem;font-size:.72rem;cursor:pointer}.segmented button[aria-pressed=true]{background:var(--color-accent-soft);color:var(--color-accent);font-weight:700}.module-tools select{max-width:10rem;border:1px solid var(--color-line);border-radius:.5rem;background:var(--color-surface);padding:.4rem .6rem;font-size:.7rem;color:var(--color-ink-secondary)}
.heat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem}.heat-card{min-width:0;display:grid;gap:.85rem;padding:1rem;border:1px solid var(--color-line);border-radius:.75rem;background:var(--color-surface);text-decoration:none;color:var(--color-ink);transition:border-color .15s,transform .15s}.heat-card:hover{border-color:var(--color-accent);transform:translateY(-2px)}.card-top,.heat-name,.price-row,.card-bottom,.quote-time{display:flex;justify-content:space-between;gap:.5rem;align-items:center}.card-top{color:var(--color-ink-tertiary);font-size:.6rem}.card-top small{font-size:.6rem}.heat-name strong{font-size:.85rem}.heat-name span{font:.61rem var(--font-numeric);color:var(--color-ink-tertiary)}.price-row b{font:600 1.15rem var(--font-numeric)}.price-row strong{font:.75rem var(--font-numeric)}.card-bottom,.quote-time{font-size:.6rem;color:var(--color-ink-tertiary)}.quote-time{border-top:1px solid var(--color-line);padding-top:.6rem}.module-footer{display:flex;gap:1rem;justify-content:space-between;align-items:center;margin-top:1rem}.module-footer p,.module-note{font-size:.65rem;color:var(--color-ink-tertiary);line-height:1.8;margin:.8rem 0 0}.module-footer p{margin:0;flex:1}.module-footer .quiet{flex-shrink:0}.sector-strip{display:flex;gap:.65rem;overflow-x:auto;margin-top:1rem;padding-bottom:.3rem}.sector-strip button{min-width:7.8rem;flex-shrink:0;display:grid;gap:.5rem;text-align:left;padding:.7rem .85rem;border:1px solid var(--color-line);border-radius:.6rem;background:transparent;cursor:pointer}.sector-strip button[aria-pressed=true]{border-color:var(--color-accent)}.sector-strip span{font-size:.68rem}.sector-strip small{display:block;font-size:.6rem;color:var(--color-ink-tertiary);margin-top:.2rem}.sector-strip b{font:.8rem var(--font-numeric)}
.radar-columns{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:1.3rem}.source-state,.text-link{font-size:.67rem;color:var(--color-accent);text-decoration:none;line-height:1.7}.topic-tabs{margin:-.4rem 0 .6rem}.topic-tabs button{padding:.4rem .6rem}.news-list article{padding:1rem 0;border-bottom:1px solid var(--color-line)}.news-meta{display:flex;justify-content:space-between;gap:1rem;color:var(--color-ink-tertiary);font-size:.62rem}.news-meta span{color:var(--color-accent)}.headline{display:block;color:var(--color-ink);text-decoration:none;font-size:.84rem;line-height:1.7;font-weight:650;margin:.5rem 0}.headline svg{display:inline;vertical-align:middle;color:var(--color-accent)}.headline:hover{text-decoration:underline}.news-list p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:.7rem;color:var(--color-ink-secondary);line-height:1.8;margin:.4rem 0 .6rem}.news-source{display:flex;gap:.7rem;flex-wrap:wrap;font-size:.61rem;color:var(--color-ink-tertiary)}.news-source a{color:var(--color-accent);text-decoration:none}.lead-scope{display:flex;align-items:center;gap:.6rem;font-size:.68rem;color:var(--color-ink-secondary);margin-bottom:1rem}.lead-card{display:block;text-decoration:none;color:var(--color-ink);padding:1rem;border:1px solid var(--color-line);border-radius:.7rem;margin-bottom:.7rem}.lead-card:hover{border-color:var(--color-accent)}.lead-card>div,.lead-card h3,.lead-card footer{display:flex;justify-content:space-between;gap:.8rem;align-items:center}.lead-badge{background:var(--color-accent-soft);color:var(--color-accent);font-size:.6rem;padding:.25rem .45rem;border-radius:.3rem}.lead-card small{font:.6rem var(--font-numeric);color:var(--color-ink-tertiary)}.lead-card h3{font-size:.83rem;margin:.8rem 0 .5rem}.lead-card h3 span{font-size:.69rem;font-weight:500}.lead-card p{font-size:.71rem;line-height:1.75;color:var(--color-ink-secondary);margin:.4rem 0 .8rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.lead-card footer{font-size:.61rem;color:var(--color-ink-tertiary)}.lead-card footer span{display:flex;align-items:center;gap:.25rem;color:var(--color-accent)}
.strategy-scope{font-size:.7rem;color:var(--color-ink-secondary);line-height:1.8;margin:-.3rem 0 1rem}.strategy-groups{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem}.strategy-groups button{display:block;text-align:left;padding:1rem;border:1px solid var(--color-line);border-radius:.75rem;background:var(--color-surface);cursor:pointer;min-width:0}.strategy-groups button[aria-pressed=true]{background:var(--color-accent-soft);border-color:var(--color-accent)}.strategy-groups button>span{display:flex;align-items:center;justify-content:space-between;gap:.6rem;font-size:.8rem;font-weight:650}.strategy-groups b{font:600 1.3rem var(--font-numeric)}.strategy-groups b small{font:.6rem var(--font-sans);color:var(--color-ink-tertiary)}.strategy-groups p{font-size:.68rem;color:var(--color-ink-secondary);line-height:1.8;min-height:2.4rem}.strategy-groups footer{display:flex;flex-wrap:wrap;gap:.7rem;font-size:.63rem}.strategy-groups em{font-style:normal}.strategy-groups footer span{margin-left:auto;color:var(--color-accent)}.signal-table-wrap{overflow:auto;margin-top:1rem}.signal-table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:.72rem}.signal-table caption{text-align:left;padding:.6rem 0 1rem;font-size:.64rem;color:var(--color-ink-tertiary)}.signal-table th{text-align:left;font-size:.62rem;font-weight:500;color:var(--color-ink-tertiary);border-bottom:1px solid var(--color-line);padding:.6rem .8rem}.signal-table td{padding:.8rem;border-bottom:1px solid var(--color-line);font-family:var(--font-numeric)}.signal-table td:first-child{font-family:var(--font-sans)}.signal-table td strong{font-size:.73rem}.signal-table td small{font-size:.6rem;color:var(--color-ink-tertiary)}.signal-table td>span{display:block;font-size:.62rem;color:var(--color-ink-tertiary);margin-top:.3rem}.signal-table a{color:var(--color-accent);text-decoration:none}
.overseas-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.8rem}.overseas-grid article{padding:1rem;border:1px solid var(--color-line);border-radius:.75rem;min-width:0;background:var(--color-surface)}.overseas-grid .card-top{margin-bottom:.8rem;flex-wrap:wrap}.overseas-grid article>a{display:flex;align-items:center;gap:.3rem;font-size:.8rem;font-weight:650;text-decoration:none;color:var(--color-ink)}.overseas-grid .price-row{margin:.9rem 0 .5rem}.overseas-grid article>small,.overseas-grid time{display:block;font-size:.6rem;line-height:1.9;color:var(--color-ink-tertiary)}.related{display:flex;gap:.45rem;flex-wrap:wrap;padding-top:.65rem;margin-top:.65rem;border-top:1px solid var(--color-line);font-size:.6rem}.related span{color:var(--color-ink-tertiary)}.related a{color:var(--color-accent);text-decoration:none}.module-error{font-size:.74rem;line-height:1.8;background:var(--color-warning-soft);color:var(--color-warning);padding:.8rem;border-radius:.5rem}.module-error button{border:0;background:none;color:var(--color-accent);text-decoration:underline;cursor:pointer}.empty{padding:1.5rem .3rem;font-size:.75rem;color:var(--color-ink-tertiary);line-height:1.8}.neutral{color:var(--color-ink-secondary)}.spinning{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(min-width:1600px){.heat-grid{grid-template-columns:repeat(6,minmax(0,1fr))}}
@media(max-width:1150px){.heat-grid,.overseas-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.market-pulse{grid-template-columns:repeat(4,minmax(0,1fr))}.pulse-title{grid-column:1/-1;border-right:0!important;border-bottom:1px solid #394148;padding-bottom:1rem!important;margin-bottom:1rem}.pulse-title strong{font-size:1.4rem}.radar-columns{grid-template-columns:minmax(0,1fr)}.desk-intro{align-items:start}.desk-actions{max-width:10rem;text-align:right}}
@media(max-width:650px){.desk-intro{flex-direction:column;gap:1rem}.desk-actions{max-width:none;justify-items:start;display:flex;align-items:center;flex-wrap:wrap;text-align:left}.heat-grid,.overseas-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.market-pulse{grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem 0}.market-pulse>div{padding:0 1rem}.market-pulse>div:nth-child(3){border:0}.market-pulse .pulse-title{margin-bottom:0}.market-pulse strong{font-size:1.5rem}.strategy-groups{grid-template-columns:minmax(0,1fr)}.strategy-groups p{min-height:0}.heat-card,.overseas-grid article{padding:.8rem}.heat-name{align-items:start;flex-direction:column;gap:.3rem}.price-row{flex-wrap:wrap;gap:.4rem}.price-row b{font-size:1rem}.card-bottom,.quote-time{flex-wrap:wrap}.module-footer{align-items:start;flex-direction:column}.radar-jumps a{font-size:.65rem;padding:.5rem .65rem}.module-tools{flex-wrap:wrap}.lead-card>div{flex-wrap:wrap}}
</style>

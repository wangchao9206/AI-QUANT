<script setup lang="ts">
import {computed} from 'vue'
import {useRoute} from 'vue-router'
import {BookOpen} from 'lucide-vue-next'
import {useExperience} from '../composables/useExperience'
const route=useRoute();const {isSimple}=useExperience()
const guides:Record<string,{title:string;body:string}>={
  overview:{title:'先了解市场，不急着做决定',body:'总览把价格、新闻和研究线索放在一起。红色表示上涨，绿色表示下跌；新闻热度和模型分数都不等于盈利机会。'},
  market:{title:'先按行业找品种，再点开了解',body:'这里展示多个品种。可以搜索名称、按行业筛选，或点星标加入关注。主力连续用于观察走势，并不是可以直接下单的交割合约。'},
  instrument:{title:'先看时间，再看变化',body:'价格旁会标注观测时间。“缓存”表示历史快照，不代表当前可成交价格。价格走势用于了解变化，更多指标可按需展开。'},
  strategy:{title:'研究工具用来提出问题和核验假设',body:'先看一种方法在什么条件下工作，再查看具体品种；模型分数不是胜率。首次使用可以先在历史回测或模拟练习中理解结果。'},
  research:{title:'先理解研究依据，再考虑风险情景',body:'方向只是模型的观察结果。风险试算需要手动填写账户情景，默认金额只是示例，既不读取实盘账户，也不会自动下单。'},
  leads:{title:'线索是待核验的变化，不是买卖指令',body:'不同方法可能给出相反方向。先读依据、来源和时间，再进入品种详情或研究计划核验；不要把“高分”理解成“高胜率”。'},
  backtest:{title:'回测是在过去的数据上做仿真',body:'先选品种、方法和时间，再比较收益、回撤与费用。历史表现不能保证未来；专业参数和逐笔账本可以在需要时展开。'},
  paper:{title:'先在模拟环境练习',body:'模拟账户使用虚拟资金；模拟成交、手续费与滑点也有假设，练习结果不等于真实市场表现。这里不会替你操作实盘账户。'},
}
const guide=computed(()=>guides[String(route.meta.guide??route.name??'')])
</script>
<template><aside v-if="isSimple&&guide" class="beginner-guide" aria-label="本页使用指引"><BookOpen :size="18"/><div><strong>{{guide.title}}</strong><p>{{guide.body}}</p></div><RouterLink to="/learn">看不懂？从这里学起 ↗</RouterLink></aside></template>
<style scoped>
.beginner-guide{display:flex;align-items:flex-start;gap:.8rem;background:var(--color-accent-soft);border:1px solid #c8dbe5;border-radius:.8rem;padding:1rem 1.1rem;margin-bottom:1.3rem;color:var(--color-accent);min-width:0}.beginner-guide>svg{flex-shrink:0;margin-top:.1rem}.beginner-guide>div{flex:1;min-width:0}.beginner-guide strong{font-size:.78rem}.beginner-guide p{font-size:.7rem;line-height:1.8;margin:.4rem 0 0;color:#426071}.beginner-guide a{font-size:.68rem;white-space:nowrap;color:var(--color-accent);margin-top:.1rem}@media(max-width:650px){.beginner-guide{flex-wrap:wrap}.beginner-guide a{margin-left:1.9rem}.beginner-guide>div{flex-basis:75%}}
</style>

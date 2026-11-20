import {TRINITY_NAME,TRINITY_STRATEGY_ID} from './personalTrinity'

export const MA20_MACD_BACKTEST_PATH='/backtest/ma20-macd'

export const PAPER_STRATEGIES = [
  {id:'MA20_MACD',name:'1分钟MA20＋日线MACD'},
  {id:'HOLISTIC_14D',name:'融合趋势'},
  {id:'MOMENTUM_BREAKOUT',name:'唐奇安通道放量突破'},
  {id:'BOLLINGER_REVERSAL',name:'布林带均值回归'},
  {id:'DUAL_THRUST',name:'Dual Thrust'},
  {id:'ADAPTIVE_CTA',name:'自适应CTA'},
  {id:'BUY_AND_HOLD',name:'买入持有'},
  {id:'WORKFLOW',name:'已发布策略工作流'},
  {id:TRINITY_STRATEGY_ID,name:TRINITY_NAME},
] as const

export type PaperStrategyId=typeof PAPER_STRATEGIES[number]['id']

export function paperStrategyId(value:unknown):PaperStrategyId|undefined {
  return PAPER_STRATEGIES.find(strategy=>strategy.id===value)?.id
}

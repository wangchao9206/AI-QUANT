import type { FlowGraph, FlowNode, NodeType } from '../services/workflows'

export const MA_TREND_NAME = 'MA5／10／20 趋势与 15 分钟确认'
export const MA_TREND_DRAFT_KIND = 'MA_TREND_15M'
export const MA_TREND_DESCRIPTION = '日线以收盘价相对 MA20 定方向、相对 MA5 看强弱。MA5 与 MA20 交叉产生反手候选；多头中 MA5 与 MA20 收敛后，MA5 上穿 MA10 可买多或加多。下一个交易日看已收盘的 15 分钟 K 线相对 MA20 确认方向，参考 MACD 金叉／死叉及 DKX。首次半仓，加仓按可用资金的一半，止盈时平当时持仓的一半。'

export function maTrendTemplate(): FlowGraph {
  const graph: FlowGraph = { schemaVersion: 1, draftKind: MA_TREND_DRAFT_KIND, nodes: [], edges: [] }
  const rows = new Map<number, number>()
  function node(id: string, type: NodeType, label: string, params: FlowNode['params'], column: number) {
    const row = rows.get(column) ?? 0
    rows.set(column, row + 1)
    graph.nodes.push({ id, type, label, params, x: 25 + 255 * column, y: 25 + 120 * row })
    return id
  }
  function connect(source: string, sourcePort: string, target: string, targetPort: string) {
    graph.edges.push({ id: `edge_${graph.edges.length}`, source, sourcePort, target, targetPort })
  }
  function pair(id: string, type: 'MATH'|'COMPARE', label: string, op: string, a: string, b: string, column: number) {
    node(id, type, label, { op }, column)
    connect(a, 'value', id, 'left')
    connect(b, 'value', id, 'right')
    return id
  }
  function and(id: string, label: string, a: string, b: string, column: number) {
    node(id, 'LOGIC', label, { op: 'AND' }, column)
    connect(a, 'result', id, 'a')
    connect(b, 'result', id, 'b')
    return id
  }

  const market = node('market', 'MARKET', '已完成日线', {}, 0)
  const zero = node('zero', 'CONSTANT', '零轴', { value: 0 }, 1)
  const close = node('close', 'PRICE', '收盘价', { field: 'close', shift: 0 }, 1)
  connect(market, 'bars', close, 'market')
  for (const [period, shifts] of [[5, 4], [10, 2], [20, 4]] as const) {
    for (let shift = 0; shift < shifts; shift++) {
      const id = node(`ma${period}_${shift}`, 'INDICATOR', `MA${period}${shift ? ` · 前 ${shift} 日` : ''}`,
        { kind: 'SMA', field: 'close', period, shift }, 1)
      connect(market, 'bars', id, 'market')
    }
  }
  for (let shift = 0; shift < 4; shift++) {
    pair(`spread${shift}`, 'MATH', `MA5－MA20 · ${shift ? `前 ${shift} 日` : '信号日'}`, 'SUB', `ma5_${shift}`, `ma20_${shift}`, 2)
  }
  const compare = (id: string, label: string, op: string, a: string, b: string) => pair(id, 'COMPARE', label, op, a, b, 3)
  const bull = compare('bull_regime', '收盘在 MA20 上方', 'GT', close, 'ma20_0')
  const bear = compare('bear_regime', '收盘在 MA20 下方', 'LT', close, 'ma20_0')
  and('bull_strength', '强势多头', bull, compare('close_above5', '收盘在 MA5 上方', 'GT', close, 'ma5_0'), 4)
  and('bear_strength', '强势空头', bear, compare('close_below5', '收盘在 MA5 下方', 'LT', close, 'ma5_0'), 4)
  const above = compare('above20', '当前 MA5 高于 MA20', 'GT', 'spread0', zero)
  const below = compare('below20', '当前 MA5 低于 MA20', 'LT', 'spread0', zero)
  and('ma20_cross_up', 'MA5 上穿 MA20 · 买多／平空候选', above,
    compare('prior_not_above', '昨日 MA5 未高于 MA20', 'LTE', 'spread1', zero), 4)
  and('ma20_cross_down', 'MA5 下穿 MA20 · 买空／平多候选', below,
    compare('prior_not_below', '昨日 MA5 未低于 MA20', 'GTE', 'spread1', zero), 4)
  const priorNarrowing = and('prior_narrowing', '前 3 日间距连续缩小',
    compare('narrow_a', '前 3 日间距大于前 2 日', 'GT', 'spread3', 'spread2'),
    compare('narrow_b', '前 2 日间距大于昨日', 'GT', 'spread2', 'spread1'), 4)
  const staysAbove = and('stays_above', '昨日及今日 MA5 高于 MA20',
    compare('prior_positive', '昨日 MA5 高于 MA20', 'GT', 'spread1', zero), above, 4)
  const convergence = and('bull_convergence', '多头均线收敛', priorNarrowing, staysAbove, 5)
  const cross10 = and('ma10_cross_up', 'MA5 上穿 MA10',
    compare('above10', '当前 MA5 高于 MA10', 'GT', 'ma5_0', 'ma10_0'),
    compare('prior_not_above10', '昨日 MA5 未高于 MA10', 'LTE', 'ma5_1', 'ma10_1'), 4)
  const reentry = and('long_reentry_condition', '收敛后上穿 MA10', convergence, cross10, 6)
  and('long_reentry', '多头再入场 · 买多／加多候选', bull, reentry, 7)
  return graph
}

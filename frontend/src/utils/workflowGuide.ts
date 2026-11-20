import type { FlowGraph, FlowNode } from '../services/workflows'
import { portLabels, ports, presetNames, specs } from './workflowGraph'

const comparisons: Record<string, string> = { GT: '>', GTE: '≥', LT: '<', LTE: '≤', EQ: '=' }
const operators: Record<string, string> = { ADD: '+', SUB: '−', MUL: '×', DIV: '÷' }
const actionLabels: Record<string, string> = {
  BUY: '开多', SELL: '开空', CLOSE_LONG: '平多', CLOSE_SHORT: '平空', FLATTEN: '平当前持仓',
}
const positionConditions: Record<string, string> = {
  BUY: '空仓时', SELL: '空仓时', CLOSE_LONG: '持有多头时', CLOSE_SHORT: '持有空头时', FLATTEN: '有持仓时',
}
const signals: Record<string, string> = {
  BUY: '出现开多信号', SELL: '出现开空信号', FLATTEN: '出现平仓信号',
  HOLD: '本次没有交易动作', WARMING: '等待足够的已完成日线',
}
const statuses: Record<string, string> = {
  READY: '已计算', PASS: '成立', BLOCKED: '未触发', SKIPPED: '持仓不适用',
  CANDIDATE: '产生信号', WARMING: '等待数据', ERROR: '计算失败',
}

export function workflowSignalLabel(signal?: string | null) {
  return signal ? signals[signal] ?? '未知信号' : '暂无信号'
}

export function workflowNodeStatusLabel(status: string) {
  return statuses[status] ?? status
}

function param(node: FlowNode, key: string) {
  return node.params[key] ?? specs[node.type].defaults[key]
}

function option(node: FlowNode, key: string) {
  const value = String(param(node, key))
  return specs[node.type].params.find(item => item.key === key)?.options?.[value] ?? value
}

function nodeTitle(node: FlowNode) {
  return node.label.trim() || specs[node.type].name
}

function priceSummary(node: FlowNode) {
  const field = option(node, 'field')
  const offset = Number(param(node, 'shift'))
  const label = node.type === 'PRICE'
    ? field
    : param(node, 'kind') === 'ATR'
      ? `${param(node, 'period')} 日 ${option(node, 'kind')}`
      : `${field}的 ${param(node, 'period')} 日${option(node, 'kind')}`
  return offset ? `${label}（向前 ${offset} 根）` : label
}

function riskSummary(node: FlowNode) {
  return `每次开仓 ${param(node, 'lots')} 手，止损 ${param(node, 'stopLossAtr')} ATR，止盈 ${param(node, 'takeProfitAtr')} ATR`
}

function operand(node: FlowNode, output: string) {
  if (node.type === 'PRICE' || node.type === 'INDICATOR') return priceSummary(node)
  if (node.type === 'CONSTANT') return String(param(node, 'value'))
  if (node.type === 'PRESET' || node.type === 'CHAN_SIGNAL') {
    const name = node.type === 'PRESET'
      ? presetNames[String(param(node, 'strategy'))] ?? nodeTitle(node)
      : nodeTitle(node)
    return `${name}的${portLabels[output] ?? output}信号`
  }
  return nodeTitle(node)
}

function describe(node: FlowNode, input: (port: string) => string): string {
  switch (node.type) {
    case 'MARKET': return '读取所选品种已经收盘的日线'
    case 'PRICE':
    case 'INDICATOR': return priceSummary(node)
    case 'CONSTANT': return `固定数值 ${param(node, 'value')}`
    case 'POSITION': return '多头为 1，空仓为 0，空头为 −1'
    case 'MATH': return `${input('left')} ${operators[String(param(node, 'op'))] ?? '?'} ${input('right')}`
    case 'COMPARE': return `${input('left')} ${comparisons[String(param(node, 'op'))] ?? '?'} ${input('right')}`
    case 'LOGIC': {
      const operation = param(node, 'op')
      if (operation === 'NOT') return `「${input('a')}」不成立时触发`
      const interval = operation === 'OR' ? '任一条件成立' : '两个条件都成立'
      return `「${input('a')}」与「${input('b')}」${interval}时触发`
    }
    case 'PRESET': return `复用${presetNames[String(param(node, 'strategy'))] ?? '预设'}规则的开多、开空和平仓信号`
    case 'CHAN_SIGNAL': return `观察${option(node, 'group')}，用于历史回测和历史模拟`
    case 'RISK': return riskSummary(node)
    case 'ACTION': {
      const action = String(param(node, 'action'))
      return `${positionConditions[action] ?? ''}，若「${input('condition')}」成立，产生${actionLabels[action] ?? '交易'}信号`
    }
  }
}

export function summarizeWorkflow(graph: FlowGraph) {
  const byId = new Map(graph.nodes.map(node => [node.id, node]))
  type LinkSource = { node: FlowNode; output: string }
  const incoming = new Map<string, Map<string, LinkSource>>()
  for (const edge of graph.edges) {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target || source.id === target.id) continue
    const outputType = ports(source).outputs[edge.sourcePort]
    if (!outputType || outputType !== ports(target).inputs[edge.targetPort]) continue
    const inputs = incoming.get(target.id) ?? new Map<string, LinkSource>()
    if (!inputs.has(edge.targetPort)) inputs.set(edge.targetPort, { node: source, output: edge.sourcePort })
    incoming.set(target.id, inputs)
  }

  const nodes = graph.nodes.map(node => {
    const inputs = incoming.get(node.id)
    const missingInputs = Object.keys(ports(node).inputs)
      .filter(port => !inputs?.has(port))
      .map(port => portLabels[port] ?? port)
    const input = (port: string) => {
      const source = inputs?.get(port)
      return source ? operand(source.node, source.output) : `待连接${portLabels[port] ?? port}`
    }
    return { id: node.id, title: nodeTitle(node), detail: describe(node, input), missingInputs }
  })
  const risks = graph.nodes.filter(node => node.type === 'RISK')
  return {
    nodes,
    missingLinks: nodes.reduce((total, node) => total + node.missingInputs.length, 0),
    risk: risks.length === 1 && risks[0] ? riskSummary(risks[0]) : risks.length ? '需要保留一个风控节点' : '尚未设置风控',
  }
}

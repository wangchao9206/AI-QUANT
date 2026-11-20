import { describe, expect, it } from 'vitest'
import { customTemplate } from './workflowGraph'
import { summarizeWorkflow, workflowNodeStatusLabel, workflowSignalLabel } from './workflowGuide'

describe('workflow guide summary', () => {
  it('describes the configured comparison and risk from the draft graph', () => {
    const graph = customTemplate()
    graph.nodes.find(node => node.id === 'sma')!.params = { kind: 'EMA', field: 'close', period: 12, shift: 1 }
    graph.nodes.find(node => node.id === 'risk')!.params = { lots: 3, stopLossAtr: 1.5, takeProfitAtr: 4 }
    const summary = summarizeWorkflow(graph)
    expect(summary.nodes.find(node => node.id === 'compare')?.detail).toBe('收盘价 > 收盘价的 12 日指数均线 EMA（向前 1 根）')
    expect(summary.risk).toBe('每次开仓 3 手，止损 1.5 ATR，止盈 4 ATR')
    expect(summary.missingLinks).toBe(0)
  })

  it('counts a missing condition when a wire comes from an invalid port', () => {
    const graph = customTemplate()
    graph.edges.find(edge => edge.id === 'e5')!.sourcePort = 'value'
    const summary = summarizeWorkflow(graph)
    expect(summary.missingLinks).toBe(1)
    expect(summary.nodes.find(node => node.id === 'action0')?.missingInputs).toEqual(['触发条件'])
  })

  it('labels a proposed action distinctly from a hold and a warming node', () => {
    expect(workflowSignalLabel('SELL')).toBe('出现开空信号')
    expect(workflowSignalLabel('HOLD')).toBe('本次没有交易动作')
    expect(workflowNodeStatusLabel('WARMING')).toBe('等待数据')
  })
})

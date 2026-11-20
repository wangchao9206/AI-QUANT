import { defineComponent, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MaTrendReplay, MaTrendReviewFrame, WorkflowVersion } from '../services/workflows'
import MaTrendWorkflowReplay from './MaTrendWorkflowReplay.vue'

const mocks = vi.hoisted(() => ({ replay:vi.fn() }))
vi.mock('../services/workflows', () => ({ workflowsApi:{ maTrendReplay:mocks.replay } }))

const ChartStub = defineComponent({
  name:'TongdaxinChart', props:['points'], template:'<div aria-label="图表已知行情">{{ points.length }}</div>',
})
const NotesStub = defineComponent({
  name:'ReplayReviewPanel', props:['at','context','fills'], emits:['pause','editing'],
  template:`<button type="button" data-test="annotate" @click="$emit('pause'); $emit('editing',true)">标注</button>`,
})

const baselineVersion: WorkflowVersion = {
  id:'v1', workflowId:'draft', sourceRevision:1, version:1, name:'均线', engineVersion:'ma-trend',
  definition:{schemaVersion:1,nodes:[],edges:[],maTrendExecution:{takeProfitPct:1}},
  requiredBars:21, lots:0, stopLossAtr:0, takeProfitAtr:0,
}
const nextVersion: WorkflowVersion = { ...baselineVersion, id:'v2', sourceRevision:2, version:2 }

function frame(time: string, openAt: string, signalReason: string, executionIndexes: number[] = []): MaTrendReviewFrame {
  return { at:`2026-11-03T${time}:00+08:00`, openAt:`2026-11-03T${openAt}:00+08:00`, tradingDate:'2026-11-03',
    open:100, high:105, low:101, close:103, volume:90, equity:100000, direction:0, lots:0, averagePrice:0,
    dailyTrigger:null,dailySignalDate:null,minuteTrend:1,minuteMa20:101,signal:'HOLD',signalReason,executionIndexes }
}

function sample(): MaTrendReplay {
  return { scope:{first:'2026-11-03',last:'2026-11-03',scoreDays:1},
    metrics:{initialCash:100000,endingEquity:99342,netPnl:-658,returnPct:-.658,maxDrawdownPct:1,entryCount:1,addCount:0,takeProfitCount:0,reversalCount:0,fees:6,slippageCost:10},
    assumptions:[], reviewRunId:'run-id', reviewDatasetId:'verified-archive', executions:[{
      at:'2026-11-03T09:15:00+08:00', signalAt:'2026-11-03T09:15:00+08:00', action:'OPEN', direction:1, lots:1, price:102, fee:6,
    }], reviewTimeline:[frame('09:15','09:00','首次等待确认'), frame('09:30','09:15','当根委托已成交',[0]), frame('09:45','09:30','下一根仍持仓')] }
}

function setup() {
  return mount(MaTrendWorkflowReplay, { props:{version:baselineVersion,versions:[baselineVersion,nextVersion]},
    global:{stubs:{TongdaxinChart:ChartStub, ReplayReviewPanel:NotesStub}} })
}

describe('MA workflow replay and review', () => {
  beforeEach(() => mocks.replay.mockReset())
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('keeps future bars and results hidden, pauses on annotation, and pins a fill to the completed bar', async () => {
    mocks.replay.mockResolvedValue(sample())
    const wrapper = setup()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.replay).toHaveBeenCalledWith('v1', { symbol:'FG701', initialCash:100000, costMultiplier:1, includeTimeline:true })
    expect(wrapper.get('[aria-label="图表已知行情"]').text()).toBe('1')
    expect(wrapper.text()).not.toContain('当根委托已成交')
    expect(wrapper.find('[aria-label="历史模拟结果"]').exists()).toBe(false)

    vi.useFakeTimers()
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
    const controls = wrapper.get('[aria-label="回放控制"]')
    await controls.get('button').trigger('click')
    await vi.advanceTimersByTimeAsync(450)
    expect(wrapper.get('[aria-label="图表已知行情"]').text()).toBe('2')
    expect(wrapper.get('[aria-label="本根模拟成交"]').text()).toContain('开仓')
    const notes = wrapper.getComponent(NotesStub)
    expect(notes.props('at')).toBe('2026-11-03T09:30:00+08:00')
    expect(notes.props('fills')).toEqual([{ id:'0', at:'2026-11-03T09:30:00+08:00', label:'开仓 · 多头 1 手 @ 102' }])
    expect(notes.props('context')).toEqual({ kind:'workflow', id:'v1', reviewRunId:'run-id' })

    await wrapper.get('[data-test="annotate"]').trigger('click')
    await vi.advanceTimersByTimeAsync(900)
    expect(wrapper.get('[data-test="replay-cursor"]').text()).toContain('09:30')
    expect(controls.get('button').attributes('disabled')).toBeDefined()
    notes.vm.$emit('editing',false)
    await nextTick()
    const next = controls.findAll('button').find(button => button.text() === '后一根')!
    await next.trigger('click')
    expect(wrapper.get('[aria-label="历史模拟结果"]').text()).toContain('-658')
    wrapper.unmount()
  })

  it('compares another frozen version using the same replay conditions and refuses a different archive', async () => {
    const base = sample()
    mocks.replay.mockResolvedValueOnce(base).mockResolvedValueOnce({ ...base, reviewDatasetId:'another-archive' })
      .mockResolvedValueOnce({...base,metrics:{...base.metrics,netPnl:345}})
    const wrapper = setup()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const step = wrapper.get('[aria-label="回放控制"]').findAll('button').find(button => button.text() === '后一根')!
    await step.trigger('click'); await step.trigger('click')
    const comparisons = wrapper.get('[aria-label="版本对照"]')
    await comparisons.get('select').setValue('v2')
    await comparisons.get('form').trigger('submit'); await flushPromises()
    expect(mocks.replay).toHaveBeenLastCalledWith('v2', { symbol:'FG701', initialCash:100000, costMultiplier:1, includeTimeline:false })
    expect(comparisons.get('[role="alert"]').text()).toContain('历史行情档案不同')
    await comparisons.get('form').trigger('submit'); await flushPromises()
    expect(comparisons.get('table').text()).toContain('345')
    wrapper.unmount()
  })
})

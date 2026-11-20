import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ReplayReviewPanel from './ReplayReviewPanel.vue'

const mocks=vi.hoisted(()=>({list:vi.fn(),save:vi.fn()}))
vi.mock('../services/replayReviews',async load=>({...await load<typeof import('../services/replayReviews')>(),replayReviewsApi:mocks}))

describe('historical replay annotation',()=>{
  it('pauses and keeps the chosen bar and fill when the incoming cursor changes',async()=>{
    const at='2026-11-02T21:15:00+08:00'
    const future='2026-11-02T21:45:00+08:00'
    const context={kind:'workflow' as const,id:'version-1',reviewRunId:'run-1'}
    mocks.list.mockResolvedValue([{id:'future',at:future,stage:'BAR',observedAction:'WAIT',suggestedAction:'ADD',reason:'未来标注'}])
    mocks.save.mockRejectedValueOnce(new Error('连接中断')).mockImplementation(async(_,data)=>({id:'saved',...data,observedAction:'OPEN'}))
    const wrapper=mount(ReplayReviewPanel,{props:{at,context,fills:[{id:'0',at,label:'开多 3 手'}]},global:{stubs:{RouterLink:true}}})
    await flushPromises()
    expect(wrapper.text()).not.toContain('未来标注')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('pause')).toHaveLength(1)
    await wrapper.setProps({at:'2026-11-02T21:30:00+08:00',fills:[{id:'1',at:future,label:'新成交'}]})
    await wrapper.get('select').setValue('0')
    await wrapper.get('textarea').setValue('再观察一根确认')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledTimes(2)
    expect(mocks.save.mock.calls[0]).toEqual(mocks.save.mock.calls[1])
    expect(mocks.save.mock.calls[1]?.[1]).toMatchObject({at,targetId:'0',stage:'FILL',suggestedAction:'WAIT',reason:'再观察一根确认'})
    wrapper.unmount()
  })
})

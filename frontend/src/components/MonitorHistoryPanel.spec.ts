import {mount,flushPromises} from '@vue/test-utils'
import {it,expect,vi,afterEach} from 'vitest'
import MonitorHistoryPanel from './MonitorHistoryPanel.vue'
const mocks=vi.hoisted(()=>({history:vi.fn()}))
vi.mock('../services/monitoring',()=>({monitoringApi:mocks}))
afterEach(()=>{vi.useRealTimers();vi.clearAllMocks()})
it('shows durable minute snapshots, missing values, details and server pagination',async()=>{
 mocks.history.mockResolvedValue({total:21,items:[{id:1,name:'螺纹监控',symbol:'RB2701',status:'STALE',checkedAt:'2026-11-07T02:00:00Z',sourceTimestamp:null,seconds:60,metrics:{lastPrice:100,ma20:null},parameters:{rules:[]},signals:[],monitorVersion:2,algorithmVersion:'test'}]})
 const w=mount(MonitorHistoryPanel);await flushPromises()
 await w.findAll('button').find(b=>b.text()==='配置监控合约')!.trigger('click');expect(w.emitted('configure')).toHaveLength(1)
 expect(w.text()).toContain('休市 / 数据过时');expect(w.text()).toContain('—')
 await w.get('[aria-label="搜索历史盘口"]').setValue('RB');await w.get('form').trigger('submit');await flushPromises()
 expect(mocks.history).toHaveBeenLastCalledWith('FUTURE','RB',1)
 await w.findAll('button').find(b=>b.text()==='下一页')!.trigger('click');await flushPromises()
 expect(mocks.history).toHaveBeenLastCalledWith('FUTURE','RB',2)
 await w.findAll('button').find(b=>b.text()==='检查详情')!.trigger('click')
 expect(w.get('[aria-label="历史检查详情"]').text()).toContain('任务版本 2');w.unmount()
})
it('surfaces errors without inventing observations',async()=>{
 mocks.history.mockRejectedValueOnce(new Error('服务暂不可用'))
 const w=mount(MonitorHistoryPanel);await flushPromises();expect(w.get('[role="alert"]').text()).toContain('服务暂不可用');expect(w.findAll('tbody tr')).toHaveLength(0);w.unmount()
})

import {mount,flushPromises} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import {it,expect,vi} from 'vitest'
import MonitorReviewsView from './MonitorReviewsView.vue'
import {monitorApi} from './monitor'
vi.mock('./monitor',()=>({monitorApi:{reviews:vi.fn()}}))
it('reads the archived review and links back to its precise monitor event',async()=>{
  vi.mocked(monitorApi.reviews).mockResolvedValue([{id:'r',monitorId:'m',eventSeq:21,outlook:'WAIT',content:'不追涨，等待证据',lessonNumber:20,createdAt:'now',evidence:{event:{signalType:'B3'},analysis:{symbol:'FU2701',frequency:'MIN5',profileHash:'frozen'},detectedAt:'then'}} as never])
  const router=createRouter({history:createMemoryHistory(),routes:['workbench','radar','compare','replay','lab','academy','judgments','reviews','settings'].map(tab=>({path:`/chanlun/${tab}`,component:MonitorReviewsView}))});await router.push('/chanlun/reviews');await router.isReady();const wrapper=mount(MonitorReviewsView,{global:{plugins:[router]}});await flushPromises();expect(wrapper.text()).toContain('不追涨，等待证据');expect(wrapper.findAll('a').some(a=>a.attributes('href')==='/chanlun/radar?monitor=m&event=21')).toBe(true);wrapper.unmount()
})

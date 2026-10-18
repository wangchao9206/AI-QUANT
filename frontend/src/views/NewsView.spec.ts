import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,describe,it,expect,vi} from 'vitest'
import NewsView from './NewsView.vue'
import {api} from '../services/api'
vi.mock('../services/api',()=>({api:{radarNews:vi.fn(),eventStudy:vi.fn()}}))
beforeEach(()=>{
  vi.mocked(api.radarNews).mockResolvedValue({status:'PARTIAL',dataTimestamp:'2025-01-01',items:Array.from({length:15},(_,i)=>({id:String(i),title:`原始发布${i}`,summary:'',url:'https://www.ndrc.gov.cn/',publisher:'发改委',publishedAt:'2025-01-01T00:00:00+08:00',timePrecision:'DAY',sourceTier:'PRIMARY',sourceId:'ndrc',topic:'产业资讯',relatedSymbols:['RBM'],analysis:[{eventType:'政策',chain:'政策→产量',conditions:'需求可能抵消',checks:['核对执行']}]})),sources:[{id:'nbs',name:'统计局',tier:'PRIMARY',url:'https://www.stats.gov.cn',scope:'统计',status:'UNAVAILABLE',fetchedAt:null,itemCount:0,message:'本次未取得有效条目'}]})
  vi.mocked(api.eventStudy).mockResolvedValue({scope:'八个代表案例',methodology:'未证明绝对最早',items:[],watchSources:[],generatedAt:'2025-01-01'})
})
describe('news desk',()=>{
  it('paginates the fetched snapshot and resets when source filters change',async()=>{
    const w=mount(NewsView,{global:{stubs:{RouterLink:true}}});await flushPromises()
    expect(w.findAll('.news-item')).toHaveLength(12)
    await w.findAll('.pagination button')[2].trigger('click')
    expect(w.findAll('.news-item')).toHaveLength(3)
    expect(w.text()).toContain('原始发布12')
    await w.get('input[type="search"]').setValue('原始发布1')
    expect(w.get('.pagination').text()).toContain('第 1 / 1 页')
    expect(w.text()).toContain('（仅日期）')
    await w.get('.interpretation summary').trigger('click')
    expect(w.text()).toContain('需求可能抵消')
    w.unmount()
  })
  it('keeps failed source visible and separates first-release uncertainty',async()=>{
    const w=mount(NewsView,{global:{stubs:{RouterLink:true}}});await flushPromises()
    await w.findAll('[role="tab"]')[2].trigger('click')
    expect(w.text()).toContain('读取失败')
    await w.findAll('[role="tab"]')[1].trigger('click')
    expect(w.text()).toContain('未证明绝对最早')
    w.unmount()
  })
})

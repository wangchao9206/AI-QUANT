import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,describe,it,expect,vi} from 'vitest'
import MentorsView from './MentorsView.vue'
import {api} from '../services/api'
import type {MentorCatalog} from '../types/mentors'
vi.mock('../services/api',()=>({api:{mentors:vi.fn(),analyzeMentorLedger:vi.fn()}}))
beforeEach(()=>{
  // Presentation fixture only: evidence accuracy is checked against the backend catalogue tests.
  const profiles=['傅海棠','葛卫东','李永强','丁洪波','吴伟淼','周承基'].map((name,i)=>({
    id:['fu-haitang','ge-weidong','li','ding','wu','zhou'][i]!,name,initials:name[0]!,style:'测试研究方向',admission:'原始资料待核验',identityStatus:'具名人物',liveEvidence:i===1?'CFTC原文':'访谈',successEvidence:'未独立核验',intro:'研究档案',timeline:[],achievements:i===0?[{text:'原专访记载5万元到1.2亿元；未核对完整出入金。',sourceIds:['interview']}]:[],
    quotes:i===0?[{text:'测试原话甲',sourceId:'interview',context:'原始语境'}]:i===2?[{text:'测试原话乙',sourceId:'interview',context:'原始语境'}]:[],methods:i===1?[{title:'研究归纳',body:'条件与约束',sourceIds:['interview'],status:'研究者归纳，非本人语录'}]:[],factors:[],ledger:{status:'MISSING',message:'完整交割单尚缺',missing:['成交与资金流']},learningIds:[],sourceIds:['interview']}))
  vi.mocked(api.mentors).mockResolvedValue({version:'test',definition:'证据分层',evidencePolicy:[],profiles,sources:[{id:'interview',publisher:'测试来源',title:'原始资料',url:'https://example.com',kind:'FIRST_PERSON_INTERVIEW',publishedAt:null,checkedAt:'2026-10-18',limitation:'未认证'}],learningTemplates:[],generatedAt:'2026-10-18',summary:{profiles:6,completePersonLedgers:0,aggregateAccounts:0,quoteCount:2},contestSnapshot:{status:'UNAVAILABLE',accounts:[]},editions:Array.from({length:20},(_,i)=>({edition:i+1,year:null,profileId:null,status:'ARCHIVE_PENDING',url:'https://ds.qhrb.com.cn/',note:'待核验'}))} as MentorCatalog)
})
describe('mentor research desk',()=>{
  it('paginates real profiles and exposes missing evidence instead of invented ledgers',async()=>{
    const w=mount(MentorsView);await flushPromises();await w.get('#tab-profiles').trigger('click')
    expect(w.findAll('.person-card')).toHaveLength(4)
    expect(w.text()).toContain('5万元到1.2亿元')
    expect(w.text()).toContain('未核对完整出入金')
    await w.findAll('.pagination button')[2].trigger('click')
    expect(w.findAll('.person-card')).toHaveLength(2)
    expect(w.findAll('.person-card')[0]?.text()).toContain('吴伟淼')
    await w.get('input[type="search"]').setValue('葛卫东')
    expect(w.findAll('.person-card')).toHaveLength(1)
    await w.get('.person-card').trigger('click')
    expect(w.get('.profile-detail').text()).toContain('CFTC原文')
    await w.get('#tab-evidence').trigger('click')
    expect(w.text()).toContain('葛卫东 · 账户资料与操作记录分开研究')
    expect(w.text()).toContain('尚未与此档案建立公开记录对应')
    expect(w.text()).not.toContain('已验证可复制')
    w.unmount()
  })
  it('keeps exact quotes separate from paraphrases and editions separate from full archives',async()=>{
    const w=mount(MentorsView);await flushPromises();await w.get('#tab-profiles').trigger('click')
    await w.get('#tab-wisdom').trigger('click')
    expect(w.findAll('blockquote')).toHaveLength(2)
    await w.get('select[aria-label="选择心法人物"]').setValue('ge-weidong')
    expect(w.text()).toContain('不收录流传金句')
    expect(w.get('.method').text()).toContain('非本人语录')
    await w.get('#tab-editions').trigger('click')
    expect(w.findAll('tbody tr')).toHaveLength(10)
    expect(w.text()).toContain('尚非完整获奖名录')
    await w.findAll('.pagination button')[2].trigger('click')
    expect(w.findAll('tbody tr')[0]?.text()).toContain('第11届')
    w.unmount()
  })
  it('admits official aliases without real names and keeps unknown matches out of performance records',async()=>{
    const data=await api.mentors()
    data.profiles.push({...data.profiles[0]!,id:'alias-test',name:'参赛昵称',identityKind:'CONTEST_ALIAS',researchStatus:'DOCUMENTED',identityStatus:'无需公开实名',intro:'官方赛期记录',admission:'官方昵称足以建档',quotes:[],contestRecords:[{recordKey:'observation1',event:'全国赛',edition:18,year:2024,group:'轻量组',scope:'INTERIM',asOf:'2024-09-25',rank:2,accountRef:null,netProfit:100,cumulativeNetWorth:2,reportedDrawdownPct:20,sourceIds:['interview'],note:''}]},
      {...data.profiles[0]!,id:'alias-pending',name:'相近昵称待核',identityKind:'CONTEST_ALIAS',researchStatus:'PENDING_MATCH',admission:'昵称匹配待核',contestRecords:[]})
    const w=mount(MentorsView);await flushPromises();await w.get('#tab-profiles').trigger('click')
    await w.get('select[aria-label="筛选档案类型"]').setValue('CONTEST_ALIAS')
    expect(w.findAll('.person-card')).toHaveLength(2)
    expect(w.get('.profile-detail').text()).toContain('无需公开实名')
    await w.get('#tab-evidence').trigger('click')
    expect(w.get('.record-panel').text()).toContain('赛中/采集时点 · 第2名')
    expect(w.get('.record-panel').text()).toContain('2024-09-25')
    await w.get('#tab-profiles').trigger('click')
    await w.get('select[aria-label="筛选证据状态"]').setValue('PENDING_MATCH')
    expect(w.findAll('.person-card')).toHaveLength(1)
    expect(w.get('.person-card').text()).toContain('相近昵称待核')
    await w.get('#tab-evidence').trigger('click')
    expect(w.find('.record-panel').exists()).toBe(false)
    await w.get('select[aria-label="选择证据人物"]').setValue('alias-test')
    expect(w.get('.record-panel').text()).toContain('2024-09-25')
    await w.get('#tab-profiles').trigger('click')
    expect(w.get('.profile-detail').text()).toContain('相近昵称待核')
    w.unmount()
  })
})

import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import MentorOperations from './MentorOperations.vue'
import type {MentorOperation,MentorProfile,MentorSource} from '../types/mentors'

// UI fixtures, not real trader data.
const profiles=[{id:'a',name:'样本甲',linkedAccountId:'account-a'},{id:'b',name:'样本乙'},{id:'empty',name:'无操作样本'}] as MentorProfile[]
const sources=[{id:'s',publisher:'测试原始出处',url:'https://example.com/source'}] as MentorSource[]
const records:MentorOperation[]=Array.from({length:8},(_,i)=>({id:`fixture-${i}`,profileId:i<7?'a':'b',periodLabel:'2010年回顾',datePrecision:'YEAR',dateStart:'2010-01-01',dateEnd:'2010-12-31',instrument:i<7?'棉花期货':'豆油期货',contractCodes:[],market:'测试市场',action:i<7?'CLOSE':'POSITION',direction:i<7?'LONG':'UNSPECIFIED',summary:'仅用于界面验收',sourceIds:['s'],sourceLocator:'问题2',sourceType:i<7?'FIRST_PERSON_RECALL':'REGULATORY_DISCLOSURE',ownerScope:i<7?'INDIVIDUAL':'CONTROLLED_COMPANIES',price:null,priceLabel:'未披露',quantity:null,quantityLabel:'未披露',publishedAt:'2012-01-01',limitations:['日期仅为回忆范围'],researchQuestion:'测试问题',interpretation:'研究者的待验证解释',validationStatus:'DESCRIPTIVE_ONLY',executionVerified:false,eligibleForLedgerAnalysis:false}))

describe('operation record library',()=>{
  it('paginates records, resets after filters, and keeps company positions distinct from personal executions',async()=>{
    const w=mount(MentorOperations,{props:{records,profiles,sources,version:'fixture'}})
    expect(w.findAll('.operation-card')).toHaveLength(6)
    await w.findAll('.pagination button')[2]!.trigger('click')
    expect(w.findAll('.operation-card')).toHaveLength(2)
    await w.get('[aria-label="筛选操作证据"]').setValue('REGULATORY_DISCLOSURE')
    expect(w.findAll('.operation-card')).toHaveLength(1)
    expect(w.get('.operation-card').text()).toContain('控制公司 / 合并头寸')
    expect(w.get('.operation-card').text()).toContain('方向未披露')
    expect(w.get('.operation-card').text()).toContain('研究者解读 · 待验证')
    expect(w.get('.operation-card a').attributes('href')).toBe('https://example.com/source')
    await w.get('[aria-label="检索操作记录"]').setValue('没有此品种')
    expect(w.findAll('.operation-card')).toHaveLength(0)
    expect(w.get('.empty').text()).toContain('没有已收录操作')
  })
  it('supports person navigation and never substitutes another persons records for an empty profile',async()=>{
    const w=mount(MentorOperations,{props:{records,profiles,sources,version:'fixture',preferredProfileId:'a'}})
    await w.get('.operation-card footer').findAll('button')[1]!.trigger('click')
    expect(w.emitted('account')).toEqual([['a']])
    await w.get('.operation-card footer').findAll('button')[0]!.trigger('click')
    expect(w.emitted('profile')).toEqual([['a']])
    await w.setProps({preferredProfileId:'empty'})
    expect(w.findAll('.operation-card')).toHaveLength(0)
    expect(w.get('.empty').text()).toContain('账户与赛期')
    await w.get('.filters button').trigger('click')
    expect(w.findAll('.operation-card')).toHaveLength(6)
  })
})

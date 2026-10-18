import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import ContestEvidence from './ContestEvidence.vue'
import type {MentorCatalog} from '../types/mentors'

// Presentation fixture only; actual published numbers are checked in Python.
const snapshot:MentorCatalog['contestSnapshot']={status:'OBSERVED_PUBLIC_AGGREGATES',accounts:['a','b'].map(id=>({
  id,alias:`样本${id}`,rank:1,groupLabel:'测试赛期',identityStatus:'PUBLIC_CONTEST_ALIAS',evidenceType:'ORGANIZER_AGGREGATE',statementStatus:'NO_EXECUTION_LEDGER',periodStart:'2024-01-01',asOf:'2024-01-31',sourceUrls:[],sourceSha256:'fixture',
  analysis:{metrics:{dailyProfitPointCount:21},findings:[],byBreed:[],netWorth:[],daily:Array.from({length:21},(_,i)=>({date:`2024-01-${String(i+1).padStart(2,'0')}`,netWorth:1,netProfit:i,reportedRiskDegree:100+i}))}
}))}

describe('published contest evidence',()=>{
  it('selects the linked account and resets daily pagination when the person changes',async()=>{
    const w=mount(ContestEvidence,{props:{snapshot,preferredAccountId:'b'}})
    expect((w.get('select').element as HTMLSelectElement).value).toBe('b')
    expect(w.get('.account-caption').text()).toContain('样本b')
    expect(w.findAll('.raw-nav[open] tbody tr')).toHaveLength(20)
    await w.get('nav[aria-label="账户日度记录分页"]').findAll('button')[2]!.trigger('click')
    expect(w.findAll('.raw-nav[open] tbody tr')).toHaveLength(1)
    await w.setProps({preferredAccountId:'a'})
    expect(w.get('.account-caption').text()).toContain('样本a')
    expect(w.findAll('.raw-nav[open] tbody tr')).toHaveLength(20)
    expect(w.text()).toContain('无逐笔交割单')
    expect(w.text()).toContain('口径未经独立核准')
  })
})

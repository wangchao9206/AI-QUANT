import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import SettlementEvidence from './SettlementEvidence.vue'

describe('public settlement evidence',()=>{
  it('shows disclosed cash rows newest first, paginates, and preserves the permission boundary',async()=>{
    const w=mount(SettlementEvidence,{props:{snapshot:{accounts:[{id:'fixture',alias:'测试账户',rank:1,sourceUrl:'https://example.com',sourceUrls:[],sourceSha256:'fixture',rawTradesPublic:false,rows:Array.from({length:21},(_,i)=>({dateline:`2026-01-${String(i+1).padStart(2,'0')}`,fee:2,equity:100,cbalance:100,balance:102,today_in:0,today_out:0,profit:0,royalty:0,cashResidual:0}))}]}}})
    expect(w.findAll('tbody tr')).toHaveLength(20)
    expect(w.findAll('tbody tr')[0]!.text()).toContain('2026-01-21')
    expect(w.text()).toContain('未开放此账户的逐笔成交明细')
    expect(w.text()).toContain('不能据此替代某位前辈的交易记录')
    await w.findAll('.pagination button')[2]!.trigger('click')
    expect(w.findAll('tbody tr')).toHaveLength(1)
    expect(w.findAll('tbody tr')[0]!.text()).toContain('2026-01-01')
  })
})

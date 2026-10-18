import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,describe,it,expect,vi} from 'vitest'
import LedgerLab from './LedgerLab.vue'
import {api} from '../services/api'
import type {LedgerAnalysis} from '../types/mentors'
vi.mock('../services/api',()=>({api:{analyzeMentorLedger:vi.fn()}}))
const report:LedgerAnalysis={sourceLabel:'测试资料',sourceUrl:'',inputSha256:'abc',authenticity:'USER_SUPPLIED_UNVERIFIED',validationStatus:'DESCRIPTIVE_ONLY',period:{start:'2025-01-02',end:'2025-01-03'},metrics:{netClosedPnl:98,allocatedClosedFees:2,netWithoutBest1:0,netAtDoubleClosedFees:96,fillCount:2,pairedFragments:1,accountReturnPct:null,accountMaxDrawdownPct:null},pairs:[],byContract:[],openPositions:[],learningChecks:[],warnings:['来源真实性和账户归属未获独立认证。']}
beforeEach(()=>{vi.mocked(api.analyzeMentorLedger).mockReset()})
describe('ledger analysis input boundary',()=>{
  it('requires explicit rights and marks changed input as stale',async()=>{
    vi.mocked(api.analyzeMentorLedger).mockResolvedValue(report)
    const w=mount(LedgerLab)
    await w.get('form').trigger('submit')
    expect(api.analyzeMentorLedger).not.toHaveBeenCalled()
    await w.get('input[maxlength="150"]').setValue('测试资料')
    await w.get('textarea').setValue('CSV测试内容')
    await w.get('input[type="checkbox"]').setValue(true)
    await w.get('form').trigger('submit');await flushPromises()
    expect(api.analyzeMentorLedger).toHaveBeenCalledWith({csvText:'CSV测试内容',sourceLabel:'测试资料',sourceUrl:'',rightsConfirmed:true})
    expect(w.get('[aria-label="成交分析结果"]').text()).toContain('未独立认证')
    expect(w.text()).toContain('账户收益率与最大回撤：资料不足，不能计算')
    await w.get('textarea').setValue('已修改')
    expect(w.text()).toContain('输入已变更')
    expect(w.findAll('button').find(b=>b.text()==='导出分析报告')?.attributes('disabled')).toBeDefined()
    w.unmount()
  })
  it('shows actionable server rejection without inventing a result',async()=>{
    vi.mocked(api.analyzeMentorLedger).mockRejectedValue(new Error('缺少期初开仓记录'))
    const w=mount(LedgerLab)
    await w.get('input[maxlength="150"]').setValue('测试资料')
    await w.get('textarea').setValue('仅平仓测试')
    await w.get('input[type="checkbox"]').setValue(true)
    await w.get('form').trigger('submit');await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('缺少期初开仓记录')
    expect(w.find('[aria-label="成交分析结果"]').exists()).toBe(false)
    w.unmount()
  })
})

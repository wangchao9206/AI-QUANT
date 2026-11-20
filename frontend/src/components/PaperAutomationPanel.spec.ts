import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import PaperAutomationPanel from './PaperAutomationPanel.vue'
import {api,type PaperSession,type PaperAutomationState} from '../services/api'
import {TRINITY_DEFAULT,trinityPaperConfig} from '../utils/personalTrinity'
vi.mock('../services/api',()=>({api:{paperAutomation:vi.fn(),startPaperAutomation:vi.fn(),stopPaperAutomation:vi.fn()}}))
vi.mock('../services/workflows',()=>({workflowsApi:{versions:vi.fn()}}))
const account={id:'one-wallet',currentContract:'FG701',multiInstrument:true} as PaperSession
const run={id:'run-fg',contract:'FG701',strategy:'MA20_MACD',lots:1,enabled:true,status:'RUNNING',message:'等待新突破',stopLossTicks:10,stopLossAtr:0,takeProfitAtr:0,intradayOnly:true}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.clearAllMocks();vi.mocked(api.paperAutomation).mockResolvedValue({runs:[],events:[]})})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers()})
async function render(){wrapper=mount(PaperAutomationPanel,{props:{session:account,presets:null,busy:false},global:{stubs:{RouterLink:true}}});await flushPromises()}
describe('paper strategy automation',()=>{
 it('shows startup refreshing separately from the last received history timestamps',async()=>{
  vi.mocked(api.paperAutomation).mockResolvedValue({runs:[{...run,status:'REFRESHING',message:'正在重新拉取最新数据',dataRefresh:{completedAt:'2026-11-18T08:00:00Z',latestDailyTime:'2026-11-17T16:00:00Z',latestMinuteTime:'2026-11-18T06:59:00Z',dailyCount:200,minuteCount:600}}],events:[]})
  await render();expect(wrapper!.text()).toContain('正在拉取最新数据')
  const receipt=wrapper!.get('[aria-label="FG701 数据更新回执"]')
  expect(receipt.text()).toContain('上次数据更新');expect(receipt.text()).toContain('200根');expect(receipt.text()).toContain('600根')
  expect(api.startPaperAutomation).not.toHaveBeenCalled()
 })
 it('starts the selected actual contract with MA20 MACD defaults and stops without a close order',async()=>{
  vi.mocked(api.startPaperAutomation).mockResolvedValue({runs:[run],events:[]})
  vi.mocked(api.stopPaperAutomation).mockResolvedValue({runs:[{...run,enabled:false,status:'STOPPED',message:'已有持仓保留'}],events:[]})
  await render();await wrapper!.get('form').trigger('submit');await flushPromises()
  expect(api.startPaperAutomation).toHaveBeenCalledWith('one-wallet',expect.objectContaining({contract:'FG701',strategy:'MA20_MACD',lots:1,stopLossTicks:10,takeProfitAtr:0,intradayOnly:true}))
  expect(wrapper!.find('form').exists()).toBe(false);expect(wrapper!.text()).toContain('后台运行')
  await wrapper!.findAll('button').find(b=>b.text()==='停止 FG701 策略')!.trigger('click');await flushPromises()
  expect(api.stopPaperAutomation).toHaveBeenCalledWith('one-wallet','run-fg');expect(wrapper!.text()).toContain('已停止')
  expect(wrapper!.text()).toContain('已有持仓保留');expect(wrapper!.emitted('locked')?.at(-1)).toEqual([false])
 })
 it('polls read-only status and stops polling on unmount',async()=>{
  vi.useFakeTimers();vi.mocked(api.paperAutomation).mockResolvedValue({runs:[run],events:[]})
  await render();await vi.advanceTimersByTimeAsync(5000);await flushPromises()
  expect(api.paperAutomation).toHaveBeenCalledTimes(2);expect(api.startPaperAutomation).not.toHaveBeenCalled()
  expect(api.stopPaperAutomation).not.toHaveBeenCalled();wrapper!.unmount();wrapper=undefined
  await vi.advanceTimersByTimeAsync(10000);expect(api.paperAutomation).toHaveBeenCalledTimes(2)
 })
 it('keeps a delayed start bound to its original contract without locking another selected contract',async()=>{
  let resolve!:(state:PaperAutomationState)=>void
  vi.mocked(api.startPaperAutomation).mockReturnValue(new Promise(r=>{resolve=r}))
  await render();await wrapper!.get('form').trigger('submit')
  await wrapper!.setProps({session:{...account,currentContract:'RB2701'}})
  resolve({runs:[run],events:[]});await flushPromises()
  expect(api.startPaperAutomation).toHaveBeenCalledWith('one-wallet',expect.objectContaining({contract:'FG701'}))
  expect(wrapper!.emitted('locked')?.at(-1)).toEqual([false]);expect(wrapper!.text()).toContain('RB2701')
 })
 it('does not emit a late start result after its account is unmounted',async()=>{
  let resolve!:(state:PaperAutomationState)=>void
  vi.mocked(api.startPaperAutomation).mockReturnValue(new Promise(r=>{resolve=r}))
  await render();await wrapper!.get('form').trigger('submit');wrapper!.unmount()
  const count=wrapper!.emitted('locked')?.length
  resolve({runs:[run],events:[]});await flushPromises()
  expect(wrapper!.emitted('locked')?.length).toBe(count)
 })
 it('only starts Trinity on an eligible contract and freezes the selected one-lot rules',async()=>{
  vi.mocked(api.startPaperAutomation).mockResolvedValue({runs:[],events:[]})
  await render()
  const config={...TRINITY_DEFAULT,entryMinutes:60 as const,addMode:'NONE' as const}
  await wrapper!.setProps({initialStrategy:'PERSONAL_TRINITY',selectedTrinity:{id:'custom',name:'自选分钟策略',config},session:{...account,currentContract:'SC2701'}})
  expect(wrapper!.get('button[type=submit]').attributes('disabled')).toBeDefined()
  await wrapper!.get('form').trigger('submit')
  await wrapper!.setProps({session:account,trinityLaunchMissing:true})
  await wrapper!.get('form').trigger('submit')
  expect(api.startPaperAutomation).not.toHaveBeenCalled()
  await wrapper!.setProps({trinityLaunchMissing:false})
  expect(wrapper!.text()).toContain('自选分钟策略')
  await wrapper!.get('form').trigger('submit')
  await flushPromises()
  expect(api.startPaperAutomation).toHaveBeenCalledOnce()
  expect(api.startPaperAutomation).toHaveBeenCalledWith('one-wallet',{
    contract:'FG701',strategy:'PERSONAL_TRINITY',lots:1,stopLossTicks:0,stopLossAtr:0,takeProfitAtr:0,intradayOnly:false,trinity:trinityPaperConfig(config),
  })
 })
})

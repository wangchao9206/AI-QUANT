import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { authState, type Identity } from '../services/auth'
import { request } from '../services/api'
import { TRINITY_DEFAULT, TRINITY_NAME, exportTrinity, loadTrinityDrafts, readTrinityPaperLaunch, type TrinityResult } from '../utils/personalTrinity'
import { setStorageScope } from '../utils/storageScope'
import PersonalTrinityView from './PersonalTrinityView.vue'

vi.mock('../services/api', () => ({ request: vi.fn(), ApiError: Error }))

const identity: Identity = {
  id: 'alice', tenantId: 'research', username: 'alice', email: null, role: 'MEMBER',
  platformAdmin: false, mustChangePassword: false, tenants: [], permissions: ['workflows.read', 'research.write'],
}

const result: TrinityResult = {
  symbol: 'FG701', scope: { first: '2026-09-10', last: '2026-11-16', scoreDays: 42 },
  metrics: { netPnl: 130, returnPct: .013, maxDrawdownPct: .08, primaryOpens: 1, addOpens: 1, closedTrades: 2 },
  trades: [{ slot: 1, direction: 1, entryAt: '2026-10-01T10:15:00+08:00', exitAt: '2026-11-16T15:00:00+08:00',
    entryPrice: 895, exitPrice: 905, netPnl: 130, exitReason: 'WINDOW_END' }],
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  authState.user = identity
  setStorageScope('alice:research')
  vi.resetAllMocks()
})

async function render() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/strategy/self-developed-trinity', component: PersonalTrinityView },
    { path: '/strategy', component: { template: '<div>策略中心</div>' } },
    { path: '/paper', component: { template: '<div>模拟交易</div>' } },
  ] })
  await router.push('/strategy/self-developed-trinity')
  await router.isReady()
  return mount(PersonalTrinityView, { global: { plugins: [router] } })
}

describe('personal trinity strategy editor', () => {
  it('keeps the original template and supports naming, re-opening, and updating a browser draft', async () => {
    const wrapper = await render()
    expect(wrapper.get('h2').text()).toBe('改造策略')
    expect((wrapper.get('input[type=text]').element as HTMLInputElement).value).toBe(`${TRINITY_NAME} · 副本`)
    expect(wrapper.get('a').attributes('href')).toBe('/strategy')
    await wrapper.get('select').setValue(30)
    await wrapper.get('input[type=text]').setValue('中周期测试')
    await wrapper.findAll('button').find(button => button.text() === '保存为草稿')!.trigger('click')
    const [draft] = loadTrinityDrafts()
    expect(draft).toMatchObject({ name: '中周期测试', config: { entryMinutes: 30 } })
    await wrapper.findAll('button').find(button => button.text() === '恢复内置模板')!.trigger('click')
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('15')
    await wrapper.get('aside select').setValue(draft!.id)
    await wrapper.get('select').setValue(60)
    await wrapper.findAll('button').find(button => button.text() === '保存修改')!.trigger('click')
    expect(loadTrinityDrafts()).toEqual([{ ...draft, config: { ...draft!.config, entryMinutes: 60 } }])
    expect(TRINITY_DEFAULT.entryMinutes).toBe(15)
    wrapper.unmount()
  })

  it('runs edited parameters through historical replay and clears stale results after an edit', async () => {
    vi.mocked(request).mockResolvedValueOnce(result).mockRejectedValueOnce(new Error('档案暂不可用'))
    const wrapper = await render()
    await wrapper.get('select').setValue(30)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(request).toHaveBeenCalledWith('/api/v1/research/personal-trinity/backtest',
      expect.objectContaining({ body: JSON.stringify({ ...TRINITY_DEFAULT, entryMinutes: 30 }) }), 60000)
    expect(wrapper.get('.trinity-result').text()).toContain('+130.00 元')
    expect(wrapper.get('.trinity-result').text()).toContain('42 个交易日')
    expect(wrapper.get('.trinity-result').text()).toContain('30 分钟')
    await wrapper.get('select').setValue(60)
    expect(wrapper.find('.trinity-result').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toBe('档案暂不可用')
    expect(wrapper.find('.trinity-result').exists()).toBe(false)
    wrapper.unmount()
  })

  it('imports an editable copy without overwriting the matching original draft', async () => {
    const wrapper = await render()
    await wrapper.findAll('button').find(button => button.text() === '保存为草稿')!.trigger('click')
    const [original] = loadTrinityDrafts()
    const incoming = { ...original!, name: '导入副本', config: { ...TRINITY_DEFAULT, entryMinutes: 60 as const } }
    const fileInput = wrapper.get('input[type=file]')
    Object.defineProperty(fileInput.element, 'files', { value: [{ size: 100, text: async () => exportTrinity(incoming) }] })
    await fileInput.trigger('change')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '保存为草稿')!.trigger('click')
    const [saved, retained] = loadTrinityDrafts()
    expect(saved).toMatchObject({ name: '导入副本', config: { entryMinutes: 60 } })
    expect(saved!.id).not.toBe(original!.id)
    expect(retained).toEqual(original)
    wrapper.unmount()
  })

  it('leaves the editor open for read-only users and prevents replay without research write permission', async () => {
    authState.user = { ...identity, permissions: ['workflows.read'] }
    const wrapper = await render()
    expect((wrapper.get('button[type=submit]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.text()).toContain('当前账号没有运行历史回测的权限')
    await wrapper.get('form').trigger('submit')
    expect(request).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('takes edited rules to paper setup without launching an order and isolates them by identity', async () => {
    authState.user={...identity,permissions:['workflows.read','paper.read','paper.write','market.read']}
    const wrapper=await render()
    const router=wrapper.vm.$router
    await wrapper.get('select').setValue(60)
    await wrapper.findAll('button').find(button=>button.text()==='带参数去模拟盘')!.trigger('click')
    await flushPromises()
    const route=router.currentRoute.value
    expect(route.path).toBe('/paper')
    expect(route.query.automation).toBe('PERSONAL_TRINITY')
    expect(readTrinityPaperLaunch(route.query.trinity)?.config.entryMinutes).toBe(60)
    setStorageScope('alice:other-tenant')
    expect(readTrinityPaperLaunch(route.query.trinity)).toBeNull()
    expect(request).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

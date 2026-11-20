import {beforeEach,describe,expect,it,vi} from 'vitest'
import {request} from '../services/api'
import {setStorageScope} from './storageScope'
import {
  TRINITY_DEFAULT,TRINITY_NAME,backtestTrinity,exportTrinity,importTrinity,
  loadTrinityDrafts,persistTrinityDrafts,validateTrinity,
} from './personalTrinity'

vi.mock('../services/api',()=>({request:vi.fn()}))

const config={...TRINITY_DEFAULT,entryMinutes:30 as const,addMode:'MA10_ADD' as const}
const draft={id:'modified-copy',name:`${TRINITY_NAME} · 改造版`,config}

beforeEach(()=>{
  localStorage.clear()
  setStorageScope('alice:team-one')
  vi.clearAllMocks()
})

describe('personal trinity configuration',()=>{
  it('preserves supported settings across JSON import and storage without mutating the template',()=>{
    expect(importTrinity(exportTrinity(draft))).toEqual(draft)
    persistTrinityDrafts([draft])
    expect(loadTrinityDrafts()).toEqual([draft])
    expect(TRINITY_DEFAULT.entryMinutes).toBe(15)
    expect(TRINITY_DEFAULT.addMode).toBe('MINUTE_ADD')
  })

  it('scopes drafts by account and workspace and preserves unreadable raw storage',()=>{
    persistTrinityDrafts([draft])
    setStorageScope('alice:team-two')
    expect(loadTrinityDrafts()).toEqual([])
    setStorageScope('other:team-one')
    expect(loadTrinityDrafts()).toEqual([])
    setStorageScope('alice:team-one')
    expect(loadTrinityDrafts()).toEqual([draft])
    const key=localStorage.key(0)!
    localStorage.setItem(key,'{')
    expect(()=>persistTrinityDrafts([draft])).toThrow(/原记录已保留/)
    expect(localStorage.getItem(key)).toBe('{')
  })

  it('rejects invalid periods, unsupported contracts and unknown imported parameters',()=>{
    expect(validateTrinity({...config,fastPeriod:20})).toMatch(/均线周期/)
    expect(validateTrinity({...config,symbol:'SC2612'})).toMatch(/实际交割合约/)
    expect(validateTrinity({...config,extra:'unknown'})).toMatch(/未知字段/)
    expect(()=>importTrinity('{"version":2}')).toThrow(/版本/)
  })

  it('sends the edited parameters to the dedicated historical replay',async()=>{
    await backtestTrinity(config)
    expect(request).toHaveBeenCalledWith('/api/v1/research/personal-trinity/backtest',
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)},60000)
    await expect(backtestTrinity({...config,slowPeriod:5})).rejects.toThrow(/均线周期/)
    expect(request).toHaveBeenCalledTimes(1)
  })
})

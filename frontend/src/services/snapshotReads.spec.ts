import {afterEach,describe,it,expect,vi} from 'vitest'
import {readSnapshot} from './api'
import {setStorageScope} from '../utils/storageScope'
afterEach(()=>{setStorageScope(null);document.cookie='aq_csrf=; max-age=0';vi.unstubAllGlobals()})
describe('concurrent snapshot reads',()=>{
  it('shares only in-flight reads, and never shares credentials or tenants',async()=>{
    const resolvers:((value:unknown)=>void)[]=[]
    const fetcher=vi.fn(()=>new Promise(resolve=>resolvers.push(resolve)))
    vi.stubGlobal('fetch',fetcher)
    setStorageScope('u1:t1');document.cookie='aq_csrf=first'
    const first=readSnapshot('/snapshot'),same=readSnapshot('/snapshot')
    expect(fetcher).toHaveBeenCalledTimes(1)
    setStorageScope('u1:t2');const otherTenant=readSnapshot('/snapshot')
    document.cookie='aq_csrf=second';const otherLogin=readSnapshot('/snapshot')
    expect(fetcher).toHaveBeenCalledTimes(3)
    resolvers.forEach((resolve,i)=>resolve({ok:true,status:200,json:async()=>({i})}))
    expect(await first).toEqual(await same)
    expect(await otherTenant).not.toEqual(await otherLogin)
    fetcher.mockResolvedValue({ok:true,status:200,json:async()=>({new:true})} as never)
    expect(await readSnapshot('/snapshot')).toEqual({new:true})
    expect(fetcher).toHaveBeenCalledTimes(4)
  })
  it('does not cache errors',async()=>{
    const fetcher=vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ok:true,status:200,json:async()=>({fresh:true})})
    vi.stubGlobal('fetch',fetcher)
    await expect(readSnapshot('/snapshot')).rejects.toThrow()
    expect(await readSnapshot('/snapshot')).toEqual({fresh:true})
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})

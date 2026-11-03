import {afterEach,describe,it,expect,vi} from 'vitest'
import {requestUuid} from './requestId'
afterEach(()=>vi.unstubAllGlobals())
describe('UUID idempotency commands',()=>{
  it('supports HTTP origins without randomUUID',()=>{vi.stubGlobal('crypto',{getRandomValues:(bytes:Uint8Array)=>{bytes.fill(171);return bytes}});expect(requestUuid()).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/)})
})

import {afterEach,describe,it,expect,vi} from 'vitest'
import {api} from './api'
afterEach(()=>{vi.unstubAllGlobals()})
describe('ledger API wire format',()=>{
  it('sends an actual JSON object with a JSON content type accepted by FastAPI',async()=>{
    const request={csvText:'test fixture',sourceLabel:'虚构测试资料',sourceUrl:'',rightsConfirmed:true}
    const fetchMock=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({authenticity:'USER_SUPPLIED_UNVERIFIED'})})
    vi.stubGlobal('fetch',fetchMock)
    await api.analyzeMentorLedger(request)
    const [url,options]=fetchMock.mock.calls[0]!
    expect(url).toBe('/api/v1/research/mentors/analyze-ledger')
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(options.body)).toEqual(request)
  })
})

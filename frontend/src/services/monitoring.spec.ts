import {beforeEach,describe,it,expect,vi} from 'vitest'
const mock=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('./api',()=>({request:mock.request}))
import {monitoringApi,monitorJson} from './monitoring'
beforeEach(()=>vi.clearAllMocks())
describe('persistent monitor transport',()=>{
 it('normalizes database JSON without executing any metadata',()=>{expect(monitorJson({type:'jsonb',value:'{"lots":120}'})).toEqual({lots:120});expect(monitorJson('["MACD_GOLDEN"]')).toEqual(['MACD_GOLDEN'])})
 it('uses the options permission boundary and encodes search values',async()=>{mock.request.mockResolvedValue({items:[],total:0,page:1,size:20});await monitoringApi.jobs('OPTION','a&b',2);expect(mock.request).toHaveBeenCalledWith('/api/v1/options/monitors?q=a%26b&page=2&size=20')})
 it('preserves the optimistic version and never accepts a caller-provided tenant selector',async()=>{mock.request.mockResolvedValue({});await monitoringApi.enabled('FUTURE',{id:'one',version:7} as never,false);expect(mock.request).toHaveBeenCalledWith('/api/v1/market/monitors/one/enabled',expect.objectContaining({method:'POST',body:'{"enabled":false,"version":7}'}),20000)})
})

import {beforeEach,describe,it,expect,vi} from 'vitest'
const mock=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('./api',()=>({request:mock.request}))
import {liveApi} from './live'
beforeEach(()=>vi.clearAllMocks())
describe('live chart period requests',()=>{
 it('keeps short seconds separate from calendar months and requests history for MA180',async()=>{await liveApi.bars('RBM','MONTH');expect(mock.request).toHaveBeenLastCalledWith('/api/v1/market/RBM/intraday?period=MONTH&limit=600');await liveApi.bars('RBM',15);expect(mock.request).toHaveBeenLastCalledWith('/api/v1/market/RBM/intraday?seconds=15&limit=600')})
})

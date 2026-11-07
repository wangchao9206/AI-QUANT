import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import {createRouter,createMemoryHistory} from 'vue-router'
import {authState,installAuthGuard,safeNext,forgetIdentity} from './auth'
import {storageKey} from '../utils/storageScope'
const mock=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('./api',()=>({request:mock.request,ApiError:class extends Error{status=401}}))
beforeEach(()=>{sessionStorage.clear();forgetIdentity();authState.user=null;authState.loaded=false;vi.clearAllMocks()})
afterEach(()=>{sessionStorage.clear();forgetIdentity()})
describe('identity boundary in the browser',()=>{
 it('redirects unauthenticated business routes and keeps public verification reachable',async()=>{mock.request.mockResolvedValue(null);authState.loaded=true;const router=createRouter({history:createMemoryHistory(),routes:[{path:'/account',component:{template:'<p/>'}},{path:'/auth/login',meta:{public:true},component:{template:'<p/>'}},{path:'/auth/verify',meta:{public:true},component:{template:'<p/>'}}]});installAuthGuard(router);await router.push('/account');expect(router.currentRoute.value.path).toBe('/auth/login');await router.push('/auth/verify#token=example');expect(router.currentRoute.value.path).toBe('/auth/verify')})
 it('rejects external redirect URLs and defaults to today',()=>{expect(safeNext('https://evil.test')).toBe('/today');expect(safeNext('//evil.test')).toBe('/today');expect(safeNext('/auth/login')).toBe('/today');expect(safeNext('/options')).toBe('/options')})
 it('separates local notes by both user and workspace',()=>{expect(storageKey('notes')).toBe('notes');sessionStorage.setItem('aq_context','alice:tenant1');const one=storageKey('notes');sessionStorage.setItem('aq_context','alice:tenant2');expect(storageKey('notes')).not.toBe(one);sessionStorage.setItem('aq_context','bob:tenant1');expect(storageKey('notes')).not.toBe(one);forgetIdentity();expect(sessionStorage.getItem('aq_context')).toBeNull()})
})

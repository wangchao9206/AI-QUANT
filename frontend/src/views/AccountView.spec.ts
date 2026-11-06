import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,describe,it,expect,vi} from 'vitest'
import AccountView from './AccountView.vue'
const mocks=vi.hoisted(()=>({call:vi.fn(),user:{id:'alice',username:'alice',email:'alice@example.test',tenantId:'one',role:'OWNER',platformAdmin:false,tenants:[{id:'one',name:'我的工作空间',role:'OWNER'}]}}))
vi.mock('../services/auth',()=>({authCall:mocks.call,authState:{get user(){return mocks.user}},loadIdentity:vi.fn()}))
beforeEach(()=>{vi.clearAllMocks();mocks.user.role='OWNER';mocks.user.platformAdmin=false;mocks.call.mockResolvedValue([])})
describe('account workspace management',()=>{
 it('does not expose platform or membership controls to a normal member',async()=>{mocks.user.role='MEMBER';const w=mount(AccountView,{global:{stubs:{RouterLink:true}}});await flushPromises();expect(w.text()).not.toContain('平台管理');expect(w.text()).not.toContain('成员与角色');expect(mocks.call.mock.calls.some(c=>c[0]==='/members')).toBe(false);w.unmount()})
 it('links platform management to the separate console without duplicating its forms',async()=>{mocks.user.platformAdmin=true;const w=mount(AccountView,{global:{stubs:{RouterLink:true}}});await flushPromises();expect(w.text()).toContain('独立后台');expect(w.findAll('button').some(b=>b.text()==='平台管理')).toBe(false);expect(mocks.call.mock.calls.some(c=>c[0].startsWith('/admin/'))).toBe(false);w.unmount()})
 it('shows an integration key once and lets the user hide it',async()=>{mocks.call.mockImplementation(async(path,body)=>path==='/keys'&&body?{token:'aqk_test_secret'}:[]);const w=mount(AccountView,{global:{stubs:{RouterLink:true}}});await flushPromises();await w.findAll('button').find(b=>b.text()==='平台接入')!.trigger('click');await w.get('[aria-label="密钥名称"]').setValue('SaaS');await w.get('form').trigger('submit');await flushPromises();expect(w.text()).toContain('aqk_test_secret');await w.findAll('button').find(b=>b.text()==='已保存，隐藏')!.trigger('click');expect(w.text()).not.toContain('aqk_test_secret');w.unmount()})
})

import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,describe,expect,it,vi} from 'vitest'
import PaperFillJournal from './PaperFillJournal.vue'
import {api,type PaperFill} from '../services/api'
vi.mock('../services/api',()=>({api:{paperFillNote:vi.fn(),savePaperFillNote:vi.fn()}}))
const fill={id:'fill-a',contract:'FG701',side:'BUY',offset:'OPEN',fillPrice:843,quantity:1,marketTime:'2026-10-19T01:01:00Z'} as PaperFill
beforeEach(()=>{vi.resetAllMocks();vi.mocked(api.paperFillNote).mockResolvedValue({content:'',version:0})})
describe('private fill journal',()=>{
 it('loads saved notes, saves revisions, retains dirty text when account refreshes',async()=>{
  vi.mocked(api.paperFillNote).mockResolvedValue({content:'原有心得',version:2})
  vi.mocked(api.savePaperFillNote).mockResolvedValue({content:'耐心等待回踩',version:3})
  const w=mount(PaperFillJournal,{props:{sessionId:'s',fill}});await flushPromises()
  await w.get('textarea').setValue('耐心等待回踩');await w.setProps({fill:{...fill,fillPrice:843}})
  expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('耐心等待回踩')
  await w.get('footer button').trigger('click');await flushPromises()
  expect(api.savePaperFillNote).toHaveBeenCalledWith('s','fill-a',{content:'耐心等待回踩',version:2})
  expect(w.text()).toContain('心得已保存');w.unmount()
 })
 it('preserves unsaved drafts across fill selection and does not overwrite on conflict',async()=>{
  const w=mount(PaperFillJournal,{props:{sessionId:'s',fill}});await flushPromises()
  await w.get('textarea').setValue('本地草稿')
  await w.setProps({fill:{...fill,id:'fill-b'}});await flushPromises()
  await w.setProps({fill});await flushPromises()
  expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('本地草稿')
  vi.mocked(api.savePaperFillNote).mockRejectedValue(new Error('另一页面已更新'))
  await w.get('footer button').trigger('click');await flushPromises()
  expect(w.text()).toContain('另一页面已更新');expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('本地草稿');w.unmount()
 })
 it('ignores a slow response from the previously selected fill',async()=>{
  let finish!:(v:{content:string;version:number})=>void
  vi.mocked(api.paperFillNote).mockImplementationOnce(()=>new Promise(r=>{finish=r})).mockResolvedValueOnce({content:'B心得',version:1})
  const w=mount(PaperFillJournal,{props:{sessionId:'s',fill}})
  await w.setProps({fill:{...fill,id:'fill-b'}});await flushPromises();finish({content:'A旧响应',version:3});await flushPromises()
  expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('B心得');w.unmount()
 })
})

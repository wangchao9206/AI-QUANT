import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import BookPreviewPanel from './BookPreviewPanel.vue'
import {booksApi,type BookPreview,type ReadingBook} from '../services/books'
import {featuredBook} from '../content/bookReflections'
vi.mock('../services/books',()=>({booksApi:{preview:vi.fn()}}))
const resource={provider:'微信读书',title:'遥远的救世主（《天道》影视原著）',author:'豆豆',publisher:'作家出版社',readerUrl:'https://weread.qq.com/web/reader/24e32400813abbf82g011d29',accessNote:'后续章节可能需要登录或购买',verifiedAt:'2026-10-27T03:13:26Z'}
const ready:BookPreview={status:'READY',message:'已找到阅读入口',resources:[resource],checkedAt:'2026-10-27T03:13:26Z'}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.clearAllMocks();vi.mocked(booksApi.preview).mockResolvedValue(ready)})
afterEach(()=>wrapper?.unmount())
describe('book online preview',()=>{
  it('opens the verified official reader in a separate window while preserving platform access rules',async()=>{
    wrapper=mount(BookPreviewPanel,{props:{book:featuredBook}});await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('.open-reader').attributes('href')).toBe(resource.readerUrl)
    expect(wrapper.get('.open-reader').attributes('target')).toBe('_blank')
    expect(wrapper.get('.open-reader').attributes('rel')).toContain('noopener')
    expect(wrapper.text()).toContain('登录或购买')
  })
  it('refuses unexpected reader links even if an upstream response supplies them',async()=>{
    vi.mocked(booksApi.preview).mockResolvedValue({...ready,resources:[{...resource,readerUrl:'https://evil.test/book'}]})
    wrapper=mount(BookPreviewPanel,{props:{book:featuredBook}});await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false);expect(wrapper.find('.open-reader').exists()).toBe(false)
  })
  it('never shows another book after a late lookup completes',async()=>{
    let release!:(v:BookPreview)=>void
    vi.mocked(booksApi.preview).mockImplementationOnce(()=>new Promise(r=>{release=r})).mockResolvedValueOnce({status:'NOT_FOUND',message:'未找到新书的匹配入口',resources:[],checkedAt:ready.checkedAt})
    wrapper=mount(BookPreviewPanel,{props:{book:featuredBook}})
    await wrapper.setProps({book:{...featuredBook,id:'other',title:'新书'} as ReadingBook});await flushPromises()
    release(ready);await flushPromises();expect(wrapper.text()).toContain('未找到新书');expect(wrapper.find('iframe').exists()).toBe(false)
  })
  it('offers a retry after a lookup failure and requests a refreshed lookup',async()=>{
    vi.mocked(booksApi.preview).mockRejectedValueOnce(new Error('连接超时')).mockResolvedValueOnce(ready)
    wrapper=mount(BookPreviewPanel,{props:{book:featuredBook}});await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('连接超时')
    await wrapper.get('.preview-heading button').trigger('click');await flushPromises()
    expect(booksApi.preview).toHaveBeenLastCalledWith(featuredBook.id,true);expect(wrapper.find('.open-reader').exists()).toBe(true)
  })
})

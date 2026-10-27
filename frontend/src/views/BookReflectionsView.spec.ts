import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import BookReflectionsView from './BookReflectionsView.vue'
import {booksApi,type ReadingBook} from '../services/books'
import {featuredBook} from '../content/bookReflections'

vi.mock('../services/books',()=>({booksApi:{books:vi.fn(),create:vi.fn(),reflections:vi.fn(),reflect:vi.fn(),preview:vi.fn()}}))
const second:ReadingBook={id:'b2',slug:null,title:'第二本书',author:'读者自选',reflectionCount:0,createdAt:'2026-10-27T00:00:00Z'}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.clearAllMocks();vi.mocked(booksApi.books).mockResolvedValue([{...featuredBook},second]);vi.mocked(booksApi.reflections).mockResolvedValue({page:1,pageSize:10,total:0,items:[]})})
afterEach(()=>wrapper?.unmount())
async function render(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/books',component:BookReflectionsView}]});await router.push('/books');await router.isReady();wrapper=mount(BookReflectionsView,{global:{plugins:[router]}});await flushPromises()}
async function tab(label:string){await wrapper!.get('[aria-label="书籍内容"]').findAll('button').find(b=>b.text()===label)!.trigger('click')}

describe('book reflections',()=>{
  it('opens preview from the book entry and preserves an unsaved reflection across tabs',async()=>{
    vi.mocked(booksApi.preview).mockResolvedValue({status:'NOT_FOUND',message:'暂未找到匹配资源',resources:[],checkedAt:'2026-10-27T00:00:00Z'})
    await render();await tab('我的感悟');await wrapper!.get('textarea').setValue('读原著时继续思考')
    await wrapper!.get('.preview-entry').trigger('click');await flushPromises()
    expect(booksApi.preview).toHaveBeenCalledWith(featuredBook.id,false)
    expect(wrapper!.find('[aria-label="书籍在线预览"]').exists()).toBe(true)
    expect(wrapper!.find('.idea-card').exists()).toBe(false)
    await tab('我的感悟');expect((wrapper!.get('textarea').element as HTMLTextAreaElement).value).toBe('读原著时继续思考')
  })
  it('separates editorial interpretation, trading applications and private reflection history',async()=>{
    await render();expect(wrapper!.text()).toContain('非原著逐字引文');expect(wrapper!.text()).toContain('走出等待救赎')
    await tab('交易应用');expect(wrapper!.text()).toContain('纪律替代了有效性检验');expect(wrapper!.find('a[href="/paper"]').exists()).toBe(true)
    await tab('我的感悟');expect(wrapper!.text()).toContain('还没有个人感悟')
  })
  it('keeps a failed save draft and reuses its command on an unchanged retry',async()=>{
    vi.mocked(booksApi.reflect).mockRejectedValueOnce(new Error('响应超时')).mockResolvedValueOnce({id:'n1',bookId:featuredBook.id,category:'IDEA',content:'独立判断也要允许证伪',createdAt:'2026-10-27T00:00:00Z'})
    await render();await tab('我的感悟');await wrapper!.get('textarea').setValue('独立判断也要允许证伪')
    await wrapper!.get('.reflection-form').trigger('submit');await flushPromises()
    expect((wrapper!.get('textarea').element as HTMLTextAreaElement).value).toBe('独立判断也要允许证伪')
    await wrapper!.get('.reflection-form').trigger('submit');await flushPromises()
    expect(booksApi.reflect).toHaveBeenCalledTimes(2)
    expect(vi.mocked(booksApi.reflect).mock.calls[0]![1].clientRequestId).toBe(vi.mocked(booksApi.reflect).mock.calls[1]![1].clientRequestId)
    expect((wrapper!.get('textarea').element as HTMLTextAreaElement).value).toBe('')
  })
  it('uses a new command if content is revised after an uncertain save',async()=>{
    vi.mocked(booksApi.reflect).mockRejectedValue(new Error('请求超时'))
    await render();await tab('我的感悟');await wrapper!.get('textarea').setValue('第一版')
    await wrapper!.get('.reflection-form').trigger('submit');await flushPromises()
    await wrapper!.get('textarea').setValue('修订后的独立记录');await wrapper!.get('.reflection-form').trigger('submit');await flushPromises()
    expect(vi.mocked(booksApi.reflect).mock.calls[0]![1].clientRequestId).not.toBe(vi.mocked(booksApi.reflect).mock.calls[1]![1].clientRequestId)
  })
  it('retains separate book drafts and ignores a late history response from another book',async()=>{
    await render();await tab('我的感悟');await wrapper!.get('textarea').setValue('第一本的草稿')
    let release!:(v:Awaited<ReturnType<typeof booksApi.reflections>>)=>void
    vi.mocked(booksApi.reflections).mockImplementationOnce(()=>new Promise(resolve=>{release=resolve}))
    await wrapper!.findAll('.book-choice')[1]!.trigger('click');await flushPromises();await wrapper!.get('textarea').setValue('第二本的草稿')
    await wrapper!.findAll('.book-choice')[0]!.trigger('click');await flushPromises();await tab('我的感悟')
    release({page:1,pageSize:10,total:1,items:[{id:'late',bookId:'b2',category:'IDEA',content:'不应串入第一本',createdAt:'2026-10-27T00:00:00Z'}]});await flushPromises()
    expect(wrapper!.text()).not.toContain('不应串入第一本')
    expect((wrapper!.get('textarea').element as HTMLTextAreaElement).value).toBe('第一本的草稿')
  })
  it('creates a book, selects its own journal, and never fabricates an interpretation',async()=>{
    vi.mocked(booksApi.create).mockResolvedValue({...second,id:'new',title:'我的新书'})
    await render();await wrapper!.get('.add-book').trigger('click');await wrapper!.get('[aria-label="书名"]').setValue('我的新书')
    await wrapper!.get('[aria-label="添加书籍"]').trigger('submit');await flushPromises()
    expect(booksApi.create).toHaveBeenCalledWith(expect.objectContaining({title:'我的新书',author:''}))
    expect(wrapper!.get('.book-intro').text()).toContain('我的新书');expect(wrapper!.find('textarea').exists()).toBe(true)
    await tab('思想解读');expect(wrapper!.text()).toContain('暂未收录内置解读');expect(wrapper!.text()).not.toContain('走出等待救赎')
  })
  it('leaves the built-in reading available and clearly disables saving if the server is unavailable',async()=>{
    vi.mocked(booksApi.books).mockRejectedValue(new Error('服务不可用'))
    await render();expect(wrapper!.text()).toContain('走出等待救赎');expect(wrapper!.text()).toContain('书架加载失败')
    await tab('我的感悟');await wrapper!.get('textarea').setValue('尚未保存')
    expect(wrapper!.get('.reflection-actions button').attributes('disabled')).toBeDefined()
  })
})

import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import ChanlunReader from './ChanlunReader.vue'
import catalog from '../content/chanlunChapters.json'
import chapter1 from '../../public/reading-assets/chanlun/d2a87d5bd9c8/chapter-001.json'
import chapter2 from '../../public/reading-assets/chanlun/d2a87d5bd9c8/chapter-002.json'
import chapter3 from '../../public/reading-assets/chanlun/d2a87d5bd9c8/chapter-003.json'
import chapter62 from '../../public/reading-assets/chanlun/d2a87d5bd9c8/chapter-062.json'
import chapter108 from '../../public/reading-assets/chanlun/d2a87d5bd9c8/chapter-108.json'
const fixtures:Record<number,unknown>={1:chapter1,2:chapter2,3:chapter3,62:chapter62,108:chapter108}
const readChapter=(number:number)=>fixtures[number]
const response=(data:unknown)=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>data})
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  localStorage.clear()
  vi.stubGlobal('fetch',vi.fn(async(path:string)=>{
    const number=Number(path.match(/chapter-(\d+)\.json$/)?.[1]);return response(readChapter(number))
  }))
})
afterEach(()=>{wrapper?.unmount();vi.unstubAllGlobals()})

describe('internal Chanlun reading',()=>{
  it('renders the full long chapter and its local illustration, rather than the truncated source preview',async()=>{
    localStorage.setItem('aiquant-chanlun-chapter','62')
    wrapper=mount(ChanlunReader);await flushPromises()
    expect(catalog.chapters).toHaveLength(108)
    expect(wrapper.get('article').text()).toContain('大家也腐败去吧')
    expect(wrapper.get('article img').attributes('src')).toMatch(/^\/reading-assets\/chanlun\/d2a87d5bd9c8\/images\//)
  })
  it('renders native text without frames or external reading links',async()=>{
    wrapper=mount(ChanlunReader);await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('article').text()).toContain('这市场')
    expect(wrapper.findAll('a').every(a=>a.attributes('href')?.startsWith('/reading-assets/chanlun/'))).toBe(true)
    expect(vi.mocked(fetch).mock.calls.every(([path])=>String(path).startsWith('/reading-assets/chanlun/'))).toBe(true)
  })
  it('switches and searches chapters, adjusts typography, and resumes the last chapter',async()=>{
    wrapper=mount(ChanlunReader);await flushPromises()
    expect(wrapper.get('.chapter-controls button').attributes('disabled')).toBeDefined()
    await wrapper.findAll('.chapter-controls button')[1]!.trigger('click');await flushPromises()
    expect(wrapper.get('article').attributes('aria-label')).toBe('第2课正文')
    expect(localStorage.getItem('aiquant-chanlun-chapter')).toBe('2')
    await wrapper.get('input').setValue('108')
    expect(wrapper.findAll('.chapter-list button')).toHaveLength(1)
    await wrapper.get('.chapter-list button').trigger('click');await flushPromises()
    expect(wrapper.get('article').attributes('aria-label')).toBe('第108课正文')
    expect(wrapper.findAll('.chapter-controls button')[1]!.attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="放大正文字号"]').trigger('click')
    expect(wrapper.get('article').classes()).toContain('font-large')
    wrapper.unmount();wrapper=mount(ChanlunReader);await flushPromises()
    expect(wrapper.get('article').attributes('aria-label')).toBe('第108课正文')
  })
  it('ignores late text from a previous chapter and offers retry when a file is unavailable',async()=>{
    let release!:(value:unknown)=>void
    vi.mocked(fetch).mockImplementationOnce(()=>new Promise(resolve=>{release=resolve as (value:unknown)=>void}))
    wrapper=mount(ChanlunReader)
    await wrapper.findAll('.chapter-controls button')[1]!.trigger('click');await flushPromises()
    release(response(readChapter(1)));await flushPromises()
    expect(wrapper.get('article').attributes('aria-label')).toBe('第2课正文')
    vi.mocked(fetch).mockResolvedValueOnce({ok:false} as Response)
    await wrapper.findAll('.chapter-controls button')[1]!.trigger('click');await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('正文文件暂时不可用')
    await wrapper.findAll('.chapter-controls button')[2]!.trigger('click');await flushPromises()
    expect(wrapper.get('article').attributes('aria-label')).toBe('第3课正文')
  })
})

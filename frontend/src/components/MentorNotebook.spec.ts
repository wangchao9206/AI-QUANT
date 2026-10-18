import {mount} from '@vue/test-utils'
import {beforeEach,describe,it,expect} from 'vitest'
import MentorNotebook from './MentorNotebook.vue'
const template={id:'risk',title:'风险预算',question:'是否按计划执行？',practice:'检查实际记录',required:'完整记录',failure:'超出约束则失败'}
beforeEach(()=>localStorage.clear())
describe('local mentor learning notes',()=>{
  it('persists an explicit hypothesis and reopens without overwriting it',async()=>{
    const w=mount(MentorNotebook,{props:{person:'傅海棠',templates:[template]},global:{stubs:{RouterLink:true}}})
    await w.get('.templates button').trigger('click')
    await w.get('textarea').setValue('预留一段未观察的样本检验风险预算')
    await w.get('form').trigger('submit')
    expect(JSON.parse(localStorage.getItem('aiquant.mentor-notes.v1')??'[]')).toHaveLength(1)
    await w.get('.templates button').trigger('click')
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toContain('预留一段')
    expect(w.text()).toContain('未覆盖你的内容')
    w.unmount()
    const reopened=mount(MentorNotebook,{props:{person:'傅海棠',templates:[template]},global:{stubs:{RouterLink:true}}})
    expect(reopened.get('.saved').text()).toContain('预留一段')
    reopened.unmount()
  })
  it('does not merge learning notes for the same alias in different account scopes',async()=>{
    const w=mount(MentorNotebook,{props:{person:'同名昵称',personId:'2024-light-A',templates:[template]},global:{stubs:{RouterLink:true}}})
    await w.get('.templates button').trigger('click')
    await w.get('textarea').setValue('2024账户A的风险假设')
    await w.get('form').trigger('submit')
    await w.setProps({personId:'2025-heavy-B'})
    await w.get('.templates button').trigger('click')
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    await w.get('textarea').setValue('2025账户B的另一假设')
    await w.get('form').trigger('submit')
    const notes=JSON.parse(localStorage.getItem('aiquant.mentor-notes.v1')??'[]')
    expect(notes).toHaveLength(2)
    expect(new Set(notes.map((n:{subjectId:string})=>n.subjectId)).size).toBe(2)
    w.unmount()
  })
})

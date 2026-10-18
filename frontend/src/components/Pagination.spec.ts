import {describe,it,expect} from 'vitest'
import {mount} from '@vue/test-utils'
import {computed,ref,nextTick} from 'vue'
import Pagination from './Pagination.vue'
import {usePagination} from '../composables/usePagination'

describe('list pagination',()=>{
  it('disables boundaries and emits a clamped page for direct navigation',async()=>{
    const wrapper=mount(Pagination,{props:{page:1,pageSize:10,total:21,label:'消息分页'}})
    expect(wrapper.findAll('button')[0].attributes('disabled')).toBeDefined()
    await wrapper.get('input').setValue(999);await wrapper.get('input').trigger('change')
    expect(wrapper.emitted('update:page')?.at(-1)).toEqual([3])
    await wrapper.setProps({page:3})
    expect(wrapper.findAll('button').at(-1)?.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('resets filters, keeps a page on refresh and clamps after shrink',async()=>{
    const values=ref(Array.from({length:25},(_,i)=>i)),filter=ref('')
    const state=usePagination(computed(()=>values.value),10,[filter])
    state.page.value=3
    expect(state.items.value).toEqual([20,21,22,23,24])
    values.value=[...values.value];await nextTick();expect(state.page.value).toBe(3)
    values.value=[1,2];await nextTick();expect(state.page.value).toBe(1)
    values.value=Array.from({length:25},(_,i)=>i);state.page.value=2
    filter.value='铜';await nextTick();expect(state.page.value).toBe(1)
  })
})

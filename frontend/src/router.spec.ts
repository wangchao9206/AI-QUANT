import {createRouter,createMemoryHistory} from 'vue-router'
import {describe,it,expect} from 'vitest'
import appRouter from './router'
describe('market and research navigation',()=>{
  it('preserves old product links, parameters and plan anchors',async()=>{
    const router=createRouter({history:createMemoryHistory(),routes:appRouter.options.routes})
    await router.push('/strategy?symbol=cjm&stage=review#trade-plan')
    expect(router.currentRoute.value.path).toBe('/strategy/CJM')
    expect(router.currentRoute.value.query).toEqual({stage:'review'})
    expect(router.currentRoute.value.hash).toBe('#trade-plan')
    await router.push('/market?symbol=rbm')
    expect(router.currentRoute.value.path).toBe('/market/RBM')
    await router.push('/market')
    expect(router.currentRoute.value.name).toBe('market')
    expect(router.currentRoute.value.query).toEqual({})
  })
})

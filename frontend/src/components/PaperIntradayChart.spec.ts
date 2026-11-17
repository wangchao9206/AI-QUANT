import {mount} from '@vue/test-utils'
import {describe,expect,it} from 'vitest'
import PaperIntradayChart from './PaperIntradayChart.vue'
import type {HistoryPoint,PaperFill} from '../services/api'
const p=(stamp:string,day:string,price=840):HistoryPoint=>({timestamp:stamp,tradingDate:day,price,changePct:0,contract:'FG701',volume:10})
describe('manual intraday line chart',()=>{
 it('draws the latest trading day as a price line with empty future space and no candlesticks',()=>{
  const w=mount(PaperIntradayChart,{props:{points:[p('2026-10-16T06:59:00Z','2026-10-16'),p('2026-10-16T13:00:00Z','2026-10-19'),p('2026-10-16T13:01:00Z','2026-10-19')],fills:[],asOf:'2026-10-16T13:01:00Z'}})
  expect(w.text()).toContain('2026-10-19');expect(w.findAll('.hit')).toHaveLength(1)
  expect(w.find('.price-line').exists()).toBe(true);expect(w.get('svg').attributes('aria-label')).toContain('已展示1分钟');w.unmount()
 })
 it('opens the corresponding fill journal from a marker and ignores future fills',async()=>{
  const fill={id:'f',contract:'FG701',side:'BUY',offset:'OPEN',fillPrice:841,marketTime:'2026-10-16T13:00:00Z'} as PaperFill
  const w=mount(PaperIntradayChart,{props:{points:[p('2026-10-16T13:00:00Z','2026-10-19')],fills:[fill,{...fill,id:'future',marketTime:'2026-10-16T13:05:00Z'}],asOf:'2026-10-16T13:01:00Z'}})
  expect(w.findAll('.trade')).toHaveLength(1);await w.get('.trade').trigger('click');expect(w.emitted('trade')?.[0]).toEqual([fill]);w.unmount()
 })
})

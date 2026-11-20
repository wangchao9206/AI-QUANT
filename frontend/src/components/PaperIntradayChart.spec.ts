import {mount} from '@vue/test-utils'
import {describe,expect,it} from 'vitest'
import PaperIntradayChart from './PaperIntradayChart.vue'
import type {HistoryPoint,PaperFill} from '../services/api'
const p=(stamp:string,day:string,price=840):HistoryPoint=>({timestamp:stamp,tradingDate:day,price,changePct:0,contract:'FG701',volume:10})
describe('manual intraday line chart',()=>{
 it('draws DKX only from known OHLC bars and can hide it without changing trades',async()=>{
  const points=Array.from({length:35},(_,i)=>({...p(new Date(Date.UTC(2026,10,18,1,i)).toISOString(),'2026-11-18',100+i),open:100+i,high:101+i,low:99+i}))
  const w=mount(PaperIntradayChart,{props:{points,fills:[],asOf:'2026-11-18T01:30:00Z',showDkx:true}})
  expect(w.get('[aria-label="DKX指标读数"] span').text()).not.toContain('—')
  const d=w.get('[data-indicator="dkx"]').attributes('d');expect(d).toContain('L');expect(d).not.toMatch(/NaN|Infinity/)
  await w.setProps({points:points.map((v,i)=>i>=30?{...v,price:1e9,high:1e9}:v)});expect(w.get('[data-indicator="dkx"]').attributes('d')).toBe(d)
  await w.setProps({showDkx:false});expect(w.find('[data-indicator="dkx"]').exists()).toBe(false);expect(w.findAll('.hit')).toHaveLength(30);w.unmount()
 })
 it('shows the forming live minute and uses the actual cross-midnight trading sessions',()=>{
  const w=mount(PaperIntradayChart,{props:{live:true,tradingDay:'2026-11-18',tradingSessions:{night:[['21:00:00','26:30:00']],day:[['09:00:00','10:15:00'],['10:30:00','11:30:00'],['13:30:00','15:00:00']]},points:[{...p('2026-11-17T18:29:00Z','2026-11-18'),provisional:true}],fills:[],asOf:'2026-11-17T18:29:30Z'}})
  expect(w.findAll('.hit')).toHaveLength(1);expect(w.text()).toContain('09:00');expect(w.text()).toContain('当前分钟随实时行情更新')
  const cx=Number(w.get('.hit').attributes('cx'));expect(cx).toBeGreaterThan(400);expect(cx).toBeLessThan(862);w.unmount()
 })
 it('does not substitute a previous trading day when the current live day is missing',()=>{
  const w=mount(PaperIntradayChart,{props:{live:true,tradingDay:'2026-11-18',points:[p('2026-11-17T01:30:00Z','2026-11-17')],fills:[],asOf:'2026-11-18T01:31:00Z'}})
  expect(w.find('svg').exists()).toBe(false);expect(w.text()).toContain('当前交易日分时尚未就绪');w.unmount()
 })
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

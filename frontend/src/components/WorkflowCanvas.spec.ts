import {test,expect} from 'vitest'
import {mount} from '@vue/test-utils'
import WorkflowCanvas from './WorkflowCanvas.vue'
import {customTemplate} from '../utils/workflowGraph'
test('canvas commits a node drag and connects typed ports',async()=>{
 const graph=customTemplate(),w=mount(WorkflowCanvas,{props:{modelValue:graph,selected:'',trace:[]}})
 const svg=w.get('svg[aria-label="策略编排画布"]');(svg.element as SVGSVGElement).getBoundingClientRect=()=>({left:0,top:0,width:1200,height:720,right:1200,bottom:720,x:0,y:0,toJSON(){}});(svg.element as SVGSVGElement).setPointerCapture=()=>{}
 await w.get('[data-node="price"]').trigger('pointerdown',{clientX:350,clientY:75,pointerId:1})
 await svg.trigger('pointermove',{clientX:450,clientY:175,pointerId:1});await svg.trigger('pointerup',{pointerId:1})
 const moved=w.emitted('update:modelValue')?.[0]?.[0] as typeof graph
 expect(moved.nodes.find(n=>n.id==='price')?.x).toBe(430)
 expect(graph.nodes.find(n=>n.id==='price')?.x).toBe(330)
 await w.setProps({modelValue:moved})
 await w.get('[data-output="price:value"]').trigger('pointerdown',{clientX:670,clientY:226,pointerId:2})
 await w.get('[data-input="compare:right"]').trigger('pointerup',{clientX:630,clientY:234,pointerId:2})
 const connected=w.emitted('update:modelValue')?.at(-1)?.[0] as typeof graph
 expect(connected.edges.find(e=>e.target==='compare'&&e.targetPort==='right')?.source).toBe('price')
 w.unmount()
})

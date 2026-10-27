import {describe,it,expect} from 'vitest'
import {connect,customTemplate,makeNode,ports,template} from './workflowGraph'
describe('editable strategy graphs',()=>{
 it('provides six executable preset graphs and a connected custom graph',()=>{
  for(const id of ['MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','BUY_AND_HOLD','HOLISTIC_14D','DUAL_THRUST','ADAPTIVE_CTA']){
   const g=template(id);expect(g.nodes.find(n=>n.type==='PRESET')?.params.strategy).toBe(id)
   for(const edge of g.edges){const a=g.nodes.find(n=>n.id===edge.source)!,b=g.nodes.find(n=>n.id===edge.target)!;expect(ports(a).outputs[edge.sourcePort]).toBe(ports(b).inputs[edge.targetPort])}
  }
  expect(customTemplate().nodes.some(n=>n.type==='INDICATOR')).toBe(true)
 })
 it('replaces one input without mutating a draft and rejects types and cycles',()=>{
  const g=customTemplate(),other={...makeNode('CONSTANT'),id:'constant'};g.nodes.push(other)
  const changed=connect(g,'constant','value','compare','right')
  expect(g.edges.find(e=>e.target==='compare'&&e.targetPort==='right')?.source).toBe('sma')
  expect(changed.edges.filter(e=>e.target==='compare'&&e.targetPort==='right')).toHaveLength(1)
  expect(()=>connect(g,'risk','risk','compare','left')).toThrow('类型')
  const logic={...makeNode('LOGIC'),id:'logic'};g.nodes.push(logic);g.edges.push({id:'cycle1',source:'compare',sourcePort:'result',target:'logic',targetPort:'a'})
  expect(()=>connect(g,'logic','result','logic','b')).toThrow()
  const b={...makeNode('LOGIC'),id:'logic2'};g.nodes.push(b);g.edges.push({id:'cycle2',source:'logic',sourcePort:'result',target:'logic2',targetPort:'a'})
  expect(()=>connect(g,'logic2','result','logic','b')).toThrow('循环')
 })
})

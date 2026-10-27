<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {Maximize2,Minus,Plus,Trash2,MousePointer2} from 'lucide-vue-next'
import type {FlowGraph,FlowNode,NodeTrace,NodeType} from '../services/workflows'
import {clone,connect,makeNode,ports,portLabels,specs,traceValue} from '../utils/workflowGraph'
const props=defineProps<{modelValue:FlowGraph;selected:string;trace:NodeTrace[];disabled?:boolean}>()
const emit=defineEmits<{'update:modelValue':[FlowGraph];'update:selected':[string];error:[string]}>()
const svg=ref<SVGSVGElement>(),draft=ref<FlowGraph|null>(null),zoom=ref(1),pan=ref({x:0,y:0})
const graph=computed(()=>draft.value??props.modelValue)
const pending=ref<{node:string;port:string}|null>(null),pointer=ref({x:0,y:0}),edgeSelected=ref('')
let drag:{id:string;start:{x:number;y:number};x:number;y:number}|null=null
let panning:{x:number;y:number;start:{x:number;y:number}}|null=null
const W=240
const height=(n:FlowNode)=>76+Math.max(Object.keys(ports(n).inputs).length,Object.keys(ports(n).outputs).length)*28
function point(e:{clientX:number;clientY:number}){const r=svg.value!.getBoundingClientRect();return {x:(e.clientX-r.left)*1200/r.width/zoom.value-pan.value.x,y:(e.clientY-r.top)*720/r.height/zoom.value-pan.value.y}}
function at(n:FlowNode,port:string,output:boolean){return {x:n.x+(output?W:0),y:n.y+76+Object.keys(output?ports(n).outputs:ports(n).inputs).indexOf(port)*28}}
function curve(a:{x:number;y:number},b:{x:number;y:number}){const d=Math.max(70,Math.abs(a.x-b.x)*.45);return 'M '+a.x+' '+a.y+' C '+(a.x+d)+' '+a.y+', '+(b.x-d)+' '+b.y+', '+b.x+' '+b.y}
function edgePath(e:FlowGraph['edges'][number]){const a=graph.value.nodes.find(n=>n.id===e.source),b=graph.value.nodes.find(n=>n.id===e.target);return a&&b?curve(at(a,e.sourcePort,true),at(b,e.targetPort,false)):''}
const pendingPath=computed(()=>{const n=graph.value.nodes.find(n=>n.id===pending.value?.node);return n&&pending.value?curve(at(n,pending.value.port,true),pointer.value):''})
function startNode(e:PointerEvent,n:FlowNode){if(props.disabled)return;e.stopPropagation();emit('update:selected',n.id);edgeSelected.value='';drag={id:n.id,start:point(e),x:n.x,y:n.y};draft.value=clone(props.modelValue);svg.value?.setPointerCapture(e.pointerId)}
function down(e:PointerEvent){if((e.target as Element).closest('[data-node], [data-edge]'))return;emit('update:selected','');edgeSelected.value='';pending.value=null;panning={x:pan.value.x,y:pan.value.y,start:{x:e.clientX,y:e.clientY}};svg.value?.setPointerCapture(e.pointerId)}
function move(e:PointerEvent){pointer.value=point(e);if(drag&&draft.value){const n=draft.value.nodes.find(n=>n.id===drag!.id)!;n.x=Math.round(Math.max(-4000,Math.min(8000,drag.x+pointer.value.x-drag.start.x)));n.y=Math.round(Math.max(-4000,Math.min(8000,drag.y+pointer.value.y-drag.start.y)))}if(panning){const r=svg.value!.getBoundingClientRect();pan.value={x:panning.x+(e.clientX-panning.start.x)*1200/r.width/zoom.value,y:panning.y+(e.clientY-panning.start.y)*720/r.height/zoom.value}}}
function up(){if(drag&&draft.value)emit('update:modelValue',draft.value);draft.value=null;drag=null;panning=null}
function cancel(){draft.value=null;drag=null;panning=null;pending.value=null}
function output(e:PointerEvent,n:FlowNode,port:string){if(props.disabled)return;e.stopPropagation();pending.value={node:n.id,port};pointer.value=point(e)}
function input(n:FlowNode,port:string){if(!pending.value||props.disabled)return;try{emit('update:modelValue',connect(props.modelValue,pending.value.node,pending.value.port,n.id,port));pending.value=null}catch(e){emit('error',e instanceof Error?e.message:'连接失败')}}
function remove(){if(props.disabled)return;if(edgeSelected.value){emit('update:modelValue',{...clone(props.modelValue),edges:props.modelValue.edges.filter(e=>e.id!==edgeSelected.value)});edgeSelected.value=''}else if(props.selected){emit('update:modelValue',{...clone(props.modelValue),nodes:props.modelValue.nodes.filter(n=>n.id!==props.selected),edges:props.modelValue.edges.filter(e=>e.source!==props.selected&&e.target!==props.selected)});emit('update:selected','')}}
function fit(){if(!props.modelValue.nodes.length){zoom.value=1;pan.value={x:0,y:0};return}const ns=props.modelValue.nodes,minX=Math.min(...ns.map(n=>n.x)),minY=Math.min(...ns.map(n=>n.y)),maxX=Math.max(...ns.map(n=>n.x+W)),maxY=Math.max(...ns.map(n=>n.y+height(n)));zoom.value=Math.max(.15,Math.min(1.4,1100/(maxX-minX),620/(maxY-minY)));pan.value={x:(1200/zoom.value-(maxX-minX))/2-minX,y:(720/zoom.value-(maxY-minY))/2-minY}}
function drop(e:DragEvent){if(props.disabled)return;const type=e.dataTransfer?.getData('application/x-strategy-node') as NodeType;if(!type||!specs[type])return;if(graph.value.nodes.length>=40){emit('error','最多40个节点');return}const p=point(e),node=makeNode(type,Math.round(p.x-120),Math.round(p.y-30));emit('update:modelValue',{...clone(props.modelValue),nodes:[...props.modelValue.nodes,node]});emit('update:selected',node.id)}
function caption(n:FlowNode){if(n.type==='RISK')return n.params.lots+' 手 · '+n.params.stopLossAtr+' / '+n.params.takeProfitAtr+' ATR';if(n.type==='INDICATOR')return n.params.kind+' ('+n.params.period+') · 偏移 '+n.params.shift;if(n.type==='PRESET')return specs.PRESET.params[0]?.options?.[n.params.strategy!]??'';return Object.entries(n.params).map(([k,v])=>specs[n.type].params.find(p=>p.key===k)?.options?.[v]??v).join(' · ')||specs[n.type].hint}
watch(()=>props.modelValue.nodes.map(n=>n.id).join(','),()=>{pending.value=null})
defineExpose({fit,remove})
</script>
<template>
 <div class="flow-canvas" @dragover.prevent @drop.prevent="drop">
  <div class="canvas-tools"><span><MousePointer2 :size="13"/> 拖动节点 · 从输出圆点连到输入圆点</span><div><button aria-label="缩小画布" @click="zoom=Math.max(.15,zoom/1.15)"><Minus :size="15"/></button><span>{{Math.round(zoom*100)}}%</span><button aria-label="放大画布" @click="zoom=Math.min(2.5,zoom*1.15)"><Plus :size="15"/></button><button aria-label="适应画布" @click="fit"><Maximize2 :size="15"/></button><button aria-label="删除选中节点或连线" :disabled="disabled||(!selected&&!edgeSelected)" @click="remove"><Trash2 :size="15"/></button></div></div>
  <svg class="graph-svg" ref="svg" viewBox="0 0 1200 720" preserveAspectRatio="none" tabindex="0" aria-label="策略编排画布" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="cancel" @keydown.delete.prevent="remove" @keydown.backspace.prevent="remove" @keydown.esc="pending=null" @wheel.ctrl.prevent="zoom=Math.max(.15,Math.min(2.5,zoom*(($event.deltaY>0)?.92:1.08)))">
   <defs><pattern id="flow-dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="currentColor"/></pattern></defs>
   <rect width="100%" height="100%" fill="url(#flow-dots)" class="dot-grid"/>
   <g :transform="'scale('+zoom+') translate('+pan.x+' '+pan.y+')'">
    <g v-for="edge in graph.edges" :key="edge.id" :data-edge="edge.id" @pointerdown.stop="edgeSelected=edge.id;emit('update:selected','')">
     <path :d="edgePath(edge)" fill="none" stroke="transparent" stroke-width="18" class="edge-hit"/><path :d="edgePath(edge)" fill="none" :stroke="edgeSelected===edge.id?'var(--color-accent)':'#9cabb2'" :stroke-width="edgeSelected===edge.id?3:2" class="edge-line"/>
    </g>
    <path v-if="pending" :d="pendingPath" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-dasharray="7 5" pointer-events="none"/>
    <g v-for="node in graph.nodes" :key="node.id" :data-node="node.id" :transform="'translate('+node.x+' '+node.y+')'" class="flow-node" @pointerdown="startNode($event,node)">
     <rect :width="W" :height="height(node)" rx="10" fill="var(--color-surface-raised)" :stroke="selected===node.id?'var(--color-accent)':'var(--color-line)'" :stroke-width="selected===node.id?2:1"/>
     <rect x="0" y="14" width="4" height="27" rx="2" :fill="specs[node.type].color"/>
     <text x="16" y="28" class="node-label">{{node.label.slice(0,17)}}</text><text x="16" y="49" class="node-caption">{{caption(node).slice(0,32)}}</text>
     <g v-for="(kind,port,index) in ports(node).inputs" :key="'in'+port" :transform="'translate(0 '+(76+index*28)+')'" @pointerdown.stop @pointerup.stop="input(node,String(port))">
      <circle r="9" fill="transparent" :data-input="node.id+':'+port" class="port-target"/><circle r="5" :fill="kind==='BOOLEAN'?'#b78b49':kind==='RISK'?'#ac725b':'#5e8fa0'" pointer-events="none"/><text x="14" y="4" class="port-label">{{portLabels[port]}}</text>
     </g>
     <g v-for="(kind,port,index) in ports(node).outputs" :key="'out'+port" :transform="'translate('+W+' '+(76+index*28)+')'" @pointerdown="output($event,node,String(port))">
      <circle r="10" fill="transparent" :data-output="node.id+':'+port" class="port-target"/><circle r="5" :fill="kind==='BOOLEAN'?'#b78b49':kind==='RISK'?'#ac725b':'#5e8fa0'" pointer-events="none"/><text x="-14" y="4" text-anchor="end" class="port-label">{{portLabels[port]}}</text>
     </g>
     <g v-if="trace.find(t=>t.nodeId===node.id)" pointer-events="none"><circle :cx="W-16" cy="24" r="4" :fill="trace.find(t=>t.nodeId===node.id)?.status==='ERROR'?'#c45e55':trace.find(t=>t.nodeId===node.id)?.status==='CANDIDATE'?'#2c9d7c':'#b78b49'"/><title>{{trace.find(t=>t.nodeId===node.id)?.reason}} {{traceValue(trace.find(t=>t.nodeId===node.id)?.value)}}</title></g>
    </g>
   </g>
  </svg>
  <p v-if="pending" class="connect-note">正在连接 {{portLabels[pending.port]}} → 点击目标输入圆点 · Esc 取消</p>
 </div>
</template>
<style scoped>
.flow-canvas{position:relative;min-width:0;background:var(--color-surface);border:1px solid var(--color-line);border-radius:.7rem;overflow:hidden}.canvas-tools{display:flex;justify-content:space-between;align-items:center;gap:.7rem;padding:.65rem .8rem;border-bottom:1px solid var(--color-line);font-size:.65rem;color:var(--color-ink-tertiary);background:var(--color-surface-raised)}.canvas-tools>span,.canvas-tools>div{display:flex;align-items:center;gap:.5rem}.canvas-tools button{display:grid;place-items:center;background:transparent;border:0;color:var(--color-ink-secondary);padding:.35rem;cursor:pointer}.canvas-tools button:disabled{opacity:.3;cursor:default}.graph-svg{width:100%;height:620px;display:block;touch-action:none;outline-offset:-3px}.dot-grid{color:var(--color-line);opacity:.65}.flow-node{cursor:grab;user-select:none}.flow-node:active{cursor:grabbing}.node-label{fill:var(--color-ink);font-size:13px;font-weight:600}.node-caption,.port-label{fill:var(--color-ink-secondary);font-size:10px}.port-target{cursor:crosshair}.edge-hit{cursor:pointer}.edge-line{pointer-events:none}.connect-note{position:absolute;bottom:.5rem;left:1rem;padding:.5rem .8rem;background:var(--color-accent-soft);color:var(--color-accent);font-size:.7rem;border-radius:.4rem;pointer-events:none}@media(max-width:900px){.graph-svg{height:520px}.canvas-tools>span{display:none}}
</style>

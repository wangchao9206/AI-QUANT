import type {Identity} from '../services/auth'
import {routeResource} from '../services/auth'

export type Workspace='today'|'opportunities'|'trade'|'strategies'|'review'
export interface WorkspaceLink {label:string;to:string}
const defaults:WorkspaceLink[]=[
 {label:'市场总览',to:'/overview'},{label:'消息与事件',to:'/news'},{label:'线索池',to:'/leads'},{label:'品种目录',to:'/market'},
 {label:'行情与预警',to:'/live'},{label:'期权研究',to:'/options'},{label:'缠论工作区',to:'/chanlun'},
 {label:'研究工具',to:'/strategy'},{label:'自主研究',to:'/research'},{label:'学习',to:'/learn'},{label:'大佬解读',to:'/mentors'},
 {label:'个人总结与训练',to:'/personal'},{label:'书籍感悟',to:'/books'},{label:'历史回测',to:'/backtest'},
 {label:'模拟账本',to:'/paper'},{label:'系统状态',to:'/system'},
]
export function workspaceFor(path:string):Workspace|undefined {
 if(path==='/today'||path==='/')return 'today'
 if(/^\/(overview|news|leads|market)(\/|$)/.test(path))return 'opportunities'
 if(/^\/paper\/decisions(\/|$)/.test(path)||/^\/(personal)(\/|$)/.test(path)||/^\/chanlun\/(reviews|replay)(\/|$)/.test(path))return 'review'
 if(/^\/chanlun\/(lab|compare|settings|judgments)(\/|$)/.test(path)||/^\/(research|backtest)(\/|$)/.test(path)||path==='/strategy'||path.startsWith('/strategy/workflows'))return 'strategies'
 if(/^\/chanlun\/academy(\/|$)/.test(path))return undefined
 if(/^\/(live|options|paper|chanlun)(\/|$)/.test(path)||/^\/strategy\/[^/]+/.test(path))return 'trade'
 return undefined
}
export function workspaceNavigation(user:Identity|null){
 const allowed=(code:string)=>user?.permissions===undefined||user.permissions.includes(code)
 const permitted=(path:string)=>{const resource=routeResource(path);return (!resource||allowed(resource+'.read'))&&(!path.startsWith('/paper/decisions')||allowed('market.read'))}
 let links:WorkspaceLink[]=[]
 if(user?.menus===undefined)links=defaults.filter(l=>permitted(l.to))
 else {
  const nodes=user.menus,seen=new Set<string>()
  const walk=(parent:string|null)=>{for(const n of nodes.filter(n=>n.parentId===parent).sort((a,b)=>a.sortOrder-b.sortOrder)){
   if(seen.has(n.id))continue;seen.add(n.id)
   if(n.path?.startsWith('/')&&!n.path.startsWith('//')&&(!n.permission||allowed(n.permission))&&permitted(n.path))links.push({label:n.label,to:n.path})
   walk(n.id)
  }}
  walk(null)
 }
 const add=(parent:string,to:string,label:string)=>{if(links.some(l=>l.to===parent)&&!links.some(l=>l.to===to)&&permitted(to))links.push({label,to})}
 add('/paper','/paper/decisions','决策档案与复盘')
 add('/strategy','/strategy/workflows','策略工作流')
 links=links.filter((l,i)=>links.findIndex(other=>other.to===l.to)===i)
 const definitions:{id:Workspace;label:string;preferred:string}[]=[
  {id:'today',label:'今日',preferred:'/today'},{id:'opportunities',label:'机会',preferred:'/leads'},
  {id:'trade',label:'交易台',preferred:'/live'},{id:'strategies',label:'策略',preferred:'/strategy/workflows'},
  {id:'review',label:'复盘',preferred:'/paper/decisions'},
 ]
 const groups=definitions.map(g=>{const children=links.filter(l=>workspaceFor(l.to)===g.id);return {...g,to:children.find(l=>l.to===g.preferred)?.to??children[0]?.to??g.preferred,children}}).filter(g=>g.id==='today'||g.children.length>0)
 return {groups,secondary:links.filter(l=>!workspaceFor(l.to)&&l.to!=='/account'),links}
}

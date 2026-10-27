import {defineComponent,h,type VNodeChild} from 'vue'

export function reportUrl(raw:string,links:Record<string,string>,asset:(name:string)=>string,image=false):string|null {
  if(links[raw]==="@observation")return image?null:"/api/v1/research/studies/fu-regime/observation?download=true"
  if(links[raw]) return image && !links[raw].endsWith('.png') ? null : asset(links[raw])
  if(image)return null
  if(raw.startsWith('#'))return raw
  try {const url=new URL(raw);return url.protocol==='https:'&&!url.username&&!url.password?url.href:null} catch{return null}
}

// Build Vue text nodes, never evaluate HTML from a report or external source.
export default defineComponent({
  props:{text:{type:String,required:true},links:{type:Object as ()=>Record<string,string>,required:true},asset:{type:Function as unknown as ()=>((name:string)=>string),required:true}},
  setup(props){
    function inline(text:string):VNodeChild[]{
      const output:VNodeChild[]=[]
      const pattern=/(!?\[([^\]]*)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`)/g
      let offset=0
      for(const match of text.matchAll(pattern)){
        output.push(text.slice(offset,match.index))
        if(match[2]!==undefined){
          const isImage=match[0].startsWith('!'),url=reportUrl(match[3]!,props.links,props.asset,isImage)
          output.push(url?(isImage?h('img',{src:url,alt:match[2],loading:'lazy'}):h('a',{href:url,target:url.startsWith('#')?undefined:'_blank',rel:'noopener noreferrer'},match[2])):match[2])
        }else output.push(h(match[4]?'strong':'code',match[4]??match[5]))
        offset=match.index!+match[0].length
      }
      output.push(text.slice(offset));return output
    }
    return ()=>{
      const lines=props.text.split('\n'),blocks:VNodeChild[]=[]
      for(let i=0;i<lines.length;i++){
        const line=lines[i]!.trim()
        if(!line)continue
        if(line.startsWith('```')){
          const code:string[]=[];while(++i<lines.length&&!lines[i]!.startsWith('```'))code.push(lines[i]!);blocks.push(h('pre',h('code',code.join('\n'))));continue
        }
        const heading=/^(#{1,6})\s+(.+)$/.exec(line)
        if(heading){blocks.push(h(`h${Math.min(heading[1]!.length+1,6)}`,{id:heading[2]},inline(heading[2]!)));continue}
        if(line.startsWith('|')&&/^\|?\s*:?-{3}/.test(lines[i+1]?.trim()??'')){
          const cells=(row:string)=>row.trim().replace(/^\||\|$/g,'').split('|').map(t=>t.trim())
          const headers=cells(line),rows:string[][]=[];i++
          while(lines[i+1]?.trim().startsWith('|'))rows.push(cells(lines[++i]!))
          blocks.push(h('div',{class:'report-table'},h('table',[h('thead',h('tr',headers.map(t=>h('th',inline(t))))),h('tbody',rows.map(r=>h('tr',r.map(t=>h('td',inline(t))))))])));continue
        }
        if(/^[-*]\s+/.test(line)){
          const items=[line.replace(/^[-*]\s+/,'')];while(/^[-*]\s+/.test(lines[i+1]?.trim()??''))items.push(lines[++i]!.trim().replace(/^[-*]\s+/,''))
          blocks.push(h('ul',items.map(t=>h('li',inline(t)))));continue
        }
        blocks.push(h('p',inline(line)))
      }
      return h('article',{class:'research-report'},blocks)
    }
  },
})

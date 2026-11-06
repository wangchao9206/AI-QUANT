import {describe,it,expect,vi} from 'vitest'
import {jsonValue,exportAdminPage} from './administration'
describe('administration record export',()=>{
 it('decodes PostgreSQL json metadata without executing it',()=>{expect(jsonValue({type:'jsonb',value:'["options.read"]'})).toEqual(['options.read']);expect(jsonValue('["x"]')).toEqual(['x'])})
 it('escapes CSV formula values and excludes before/after snapshots from current-page export',async()=>{let output:Blob|undefined;Object.defineProperty(URL,'createObjectURL',{configurable:true,value:vi.fn((blob:Blob)=>{output=blob;return 'blob:test'})});Object.defineProperty(URL,'revokeObjectURL',{configurable:true,value:vi.fn()});vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});exportAdminPage([{username:'=FORMULA()',path:'/example',beforeState:'secretless',afterState:'updated'}],'records');const reader=new FileReader();const text=await new Promise<string>(resolve=>{reader.onload=()=>resolve(String(reader.result));reader.readAsText(output!)});expect(text).toContain("'=FORMULA()");expect(text).not.toContain('beforeState');expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test')})
})

import {describe,it,expect} from 'vitest'
import {instrumentName,instrumentLabel,productName,registerInstrumentCatalog,registerOptionNames} from './instrumentNames'

describe('Chinese futures and options presentation',()=>{
 it.each([['RBM','螺纹钢主连'],['RB2701','螺纹钢2701合约'],['KQ.m@SHFE.rb','螺纹钢主连'],['CZCE.CJ701','红枣701合约'],['MM','豆粕主连'],['JM','焦炭主连'],['JM2701','焦煤2701合约'],['JMM','焦煤主连'],['RM701','菜粕701合约'],['T2703','10年期国债2703合约'],['TAM','精对苯二甲酸主连'],['VM','聚氯乙烯主连']])('names %s without changing its identity',(code,name)=>{expect(instrumentName(code)).toBe(name);expect(instrumentLabel(code)).toBe(`${name}（${code}）`)})
 it.each([['SHFE.rb2701C3050','螺纹钢2701认购期权 · 行权价3050'],['DCE.m2701-P-3000','豆粕2701认沽期权 · 行权价3000'],['CZCE.CJ701P10000','红枣701认沽期权 · 行权价10000'],['CFFEX.IO2612-C-4300','沪深300股指2612认购期权 · 行权价4300']])('names option %s',(code,name)=>expect(instrumentName(code)).toBe(name))
 it('names actual index underlyings and product roots separately from aliases',()=>{expect(instrumentName('SSE.000300')).toBe('沪深300指数');expect(productName('JM')).toBe('焦煤');expect(productName('TA','PTA')).toBe('精对苯二甲酸')})
 it('uses a Chinese fallback and preserves unrecognized codes as auxiliary information',()=>{expect(instrumentLabel('NEW2701')).toBe('未命名品种2701合约（NEW2701）');expect(instrumentLabel('invalid')).toBe('未命名合约（invalid）');expect(instrumentName('test','豆粕认购')).toBe('豆粕认购')})
 it('uses runtime catalog names for newly introduced roots',()=>{registerInstrumentCatalog({exchanges:[{instruments:[{rootSymbol:'XYZ',name:'新增品种'}]}]});expect(instrumentName('XYZ2701')).toBe('新增品种2701合约')})
 it('can use option metadata for new instruments',()=>{registerOptionNames({chain:{underlyingSymbol:'XYZ2701'},contracts:[{symbol:'ZZZ2701-C-10',name:'ZZZ2701-C-10',strike:10,optionClass:'CALL'}]});expect(instrumentName('ZZZ2701-C-10')).toContain('新增品种2701合约认购期权')})
})

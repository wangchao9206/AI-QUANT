import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import ResearchReport,{reportUrl} from './ResearchReport'

describe('research report evidence rendering',()=>{
  const asset=(name:string)=>`/api/evidence/${name}`
  it('renders tables and known figures while treating HTML and unknown links as text',()=>{
    const wrapper=mount(ResearchReport,{props:{text:'# Report\n\n<script>alert(1)</script>\n\n| Rule | Result |\n| --- | --- |\n| **A** | -1% |\n\n![figure](chart.png)\n[download](ledger.gz)\n[bad](javascript:alert)\n![remote](https://evil.test/x.png)',links:{'chart.png':'chart.png','ledger.gz':'ledger.gz'},asset}})
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.findAll('img')).toHaveLength(1)
    expect(wrapper.get('img').attributes('src')).toBe('/api/evidence/chart.png')
    expect(wrapper.findAll('a')).toHaveLength(1)
    expect(wrapper.get('a').attributes('rel')).toContain('noopener')
  })
  it('restricts URLs and only maps the explicit dynamic observation reference',()=>{
    for(const url of ['javascript:alert(1)','data:text/html,bad','file:///D:/secrets','//evil.test','https://user:pass@evil.test'])expect(reportUrl(url,{},asset)).toBeNull()
    expect(reportUrl('https://www.shfe.cn/rule',{},asset)).toBe('https://www.shfe.cn/rule')
    expect(reportUrl('shadow.json',{'shadow.json':'@observation'},asset)).toContain('/fu-regime/observation?download=true')
    expect(reportUrl('https://evil.test/a.png',{},asset,true)).toBeNull()
  })
})

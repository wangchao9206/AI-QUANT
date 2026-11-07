"""Compile the authorized simulated research and concrete redesign; no invented user metrics."""
import hashlib,json,re
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether,Image,CondPageBreak
from reportlab.graphics.shapes import Drawing,Rect,Line,String,Polygon
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'docs/product-redesign/2026-11-07';OUT=ROOT/'output/product-redesign-2026-11-07'
OUT.mkdir(parents=True,exist_ok=True);PDF=OUT/'ai-quant-product-redesign-2026-11-07.pdf';WIDTH=A4[0]-84
CN='RedesignCN';pdfmetrics.registerFont(TTFont(CN,'C:/Windows/Fonts/msyh.ttc',subfontIndex=0))
styles={
 'Title':ParagraphStyle('Title',fontName=CN,fontSize=24,leading=34,spaceAfter=18,textColor=colors.HexColor('#153848')),
 'H1':ParagraphStyle('H1',fontName=CN,fontSize=14,leading=22,spaceBefore=16,spaceAfter=9,keepWithNext=True,textColor=colors.HexColor('#153848')),
 'H2':ParagraphStyle('H2',fontName=CN,fontSize=11,leading=18,spaceBefore=12,spaceAfter=7,keepWithNext=False),
 'H3':ParagraphStyle('H3',fontName=CN,fontSize=9.8,leading=16,spaceBefore=9,spaceAfter=5,keepWithNext=True),
 'Body':ParagraphStyle('Body',fontName=CN,fontSize=9.1,leading=15,spaceAfter=6,wordWrap='CJK'),
 'Cell':ParagraphStyle('Cell',fontName=CN,fontSize=7.5,leading=11.5,wordWrap='CJK'),
 'Header':ParagraphStyle('Header',fontName=CN,fontSize=7.7,leading=11.5,wordWrap='CJK',textColor=colors.white),
 'Small':ParagraphStyle('Small',fontName=CN,fontSize=7.5,leading=12,spaceAfter=6,wordWrap='CJK'),
}
story=[]
def markup(s):
    s=escape(str(s)).replace('—','-').replace('–','-').replace('‑','-')
    s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font color="#356573">\1</font>',s)
    s=re.sub(r'\[([^]]+)\]\(([^)]+)\)',lambda m:m[1]+' ('+m[2]+')',s)
    return s
def para(s,style='Body'):
    item=Paragraph(markup(s),styles[style]);story.append(item);return item
def heading(s,level=1):
    if level==2:story.append(CondPageBreak(105))
    return para(s,'H1' if level==1 else 'H2' if level==2 else 'H3')
def table(headers,rows,widths=None):
    widths=widths or [WIDTH/len(headers)]*len(headers)
    cells=[[Paragraph(markup(v),styles['Header']) for v in headers]]+[[Paragraph(markup(v),styles['Cell']) for v in row] for row in rows]
    t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#214554')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f5f7')]),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.extend([t,Spacer(1,8)])
def split_row(s):return [v.strip().replace('\\|','|') for v in re.split(r'(?<!\\)\|',s.strip().strip('|'))]
def markdown_file(path,label):
    story.append(PageBreak());heading(label);para('来源：'+path.relative_to(ROOT).as_posix(),'Small')
    lines=path.read_text(encoding='utf-8').splitlines();i=0;body=[]
    def flush():
        if body:para(' '.join(body));body.clear()
    while i<len(lines):
        line=lines[i].strip()
        if line.startswith('|'):
            flush();block=[]
            while i<len(lines) and lines[i].strip().startswith('|'):block.append(split_row(lines[i]));i+=1
            block=[row for row in block if not all(re.fullmatch(r':?-+:?',v.replace(' ','')) for v in row)]
            size=len(block[0]);rows=[row+['']*(size-len(row)) if len(row)<size else row[:size] for row in block]
            if len(rows)>1:table(rows[0],rows[1:])
            continue
        if not line:flush();i+=1;continue
        match=re.match(r'^(#{1,4})\s+(.+)',line)
        if match:
            flush();heading(match[2],min(3,len(match[1])));i+=1;continue
        if line.startswith('```'):
            flush();i+=1;code=[]
            while i<len(lines) and not lines[i].strip().startswith('```'):code.append(lines[i]);i+=1
            for value in code:para(value,'Small')
            i+=1;continue
        if re.match(r'^[-*]\s',line) or re.match(r'^\d+[.、]\s',line):
            flush();para(line);i+=1;continue
        body.append(line);i+=1
    flush()
class Report(SimpleDocTemplate):
    serial=0
    def afterFlowable(self,item):
        if isinstance(item,Paragraph) and item.style.name in ('H1','H2'):
            self.serial+=1;key='section'+str(self.serial);self.canv.bookmarkPage(key)
            # Make independent sections accessible without building a huge table of contents.
            self.canv.addOutlineEntry(item.getPlainText(),key,level=0 if item.style.name=='H1' or self.serial==1 else 1,closed=True)
def flow_diagram():
    d=Drawing(WIDTH,112);labels=['发现机会','核对判断','形成计划','观察 / 模拟','复盘迭代'];step=WIDTH/5
    for i,label in enumerate(labels):
        x=i*step+2;d.add(Rect(x,62,step-13,31,rx=4,fillColor=colors.HexColor('#eaf2f4'),strokeColor=colors.HexColor('#a3bec9')))
        d.add(String(x+10,74,label,fontName=CN,fontSize=9,fillColor=colors.HexColor('#214554')))
        if i<4:d.add(Line(x+step-12,77,x+step,77,strokeColor=colors.HexColor('#55828d')))
    d.add(Rect(2,13,WIDTH-13,28,rx=4,fillColor=colors.HexColor('#f2f5f7'),strokeColor=None));d.add(String(15,24,'同一决策档案：合约 · 时点 · 证据 · 版本 · 风险预算',fontName=CN,fontSize=10))
    return d
def main():
    para('AI-QUANT\n交易决策与训练工作台\n产品重设计方案','Title')
    para('2026年11月7日 · 10类投资者模拟访谈 · 3种产品专家模拟评审')
    para('交付结论：以同一个决策对象贯穿发现、判断、计划、观察/模拟和复盘；保留专业工作区，合并重复入口，重新定义预测与策略的证据和运行资格。')
    story.append(flow_diagram())
    para('方法边界','H2');para('经用户明确许可，访谈与专家视角均为角色模拟，不是真人参与、真实原话、外部专家背书或用户行为验证。代码审查是事实来源；需求与方案是待验证假设。没有编造满意度、完成率或投资收益改善。')
    para('本次是方案和离线原型交付：未修改生产代码、算法权重、菜单权限、模拟账户或后台任务，未部署新产品。')
    table(['阅读顺序','内容'],[['1 具体方案','定位、五入口、全部模块去留、对象/流程、预测/策略规格、门槛、迁移与验收'],['2 专家裁决与需求映射','保留分歧、采纳理由；37条模拟设计需求逐项映射到方案与验收'],['3 完整模拟访谈','P01至P10，各含六问及追问、事实依据和真实验证题'],['4 独立专家评审','E01交互/零售产品、E02量化/金融决策、E03平台/联动'],['5 现状与证据','静态代码审查、来源指纹与本轮交付清单']],[100,WIDTH-100])
    para('离线交互原型：output/product-redesign-2026-11-07/prototype.html。原型只演示任务和状态，不连接生产账户、不生成真实或模拟成交。','Small')
    markdown_file(DATA/'redesign-plan.md','第一部分 具体产品方案')
    markdown_file(DATA/'expert-decisions.md','第二部分 三种专家视角后的裁决')
    story.append(PageBreak());heading('37条需求的设计与验收映射')
    trace=json.loads((DATA/'requirements-traceability.json').read_text(encoding='utf-8'))['needs']
    para('计数只表示本次写出的设计条目数量，不是用户支持率。原始访谈中的优先级与本方案分阶段交付的优先级可能不同，取舍见专家裁决。P06-N5与P07-N4明确后置，未计为本期验收覆盖。')
    table(['需求ID','来源','方案章节','验收','裁决'],[[r['needId'],r['source']+':'+str(r['line']),r['planSection'],' / '.join(r['acceptance']) or 'DEFERRED，独立立项后定义',' / '.join(r['expertDecision'])] for r in trace],[63,130,98,100,WIDTH-391])
    for name,label in [('investors-a.md','第三部分 P01至P04完整模拟访谈'),('investors-b.md','P05至P07完整模拟访谈'),('investors-c.md','P08至P10完整模拟访谈'),
                       ('experts-e01.md','第四部分 E01交互与零售产品评审'),('experts-e02.md','E02量化与金融决策产品评审'),('experts-e03.md','E03平台与联动产品评审'),('code-audit.md','第五部分 现状事实与边界')]:
        markdown_file(DATA/name,label)
    story.append(PageBreak());heading('交付范围与核验记录')
    para('真实访谈人数：0。真人专家受聘人数：0。模拟投资者视角：10。独立模拟专家视角：3。现状来源：仓库静态代码与已保存研究输出；不是生产用户行为分析。')
    para('基线仓库提交：4dc61699a108bcdea4047c7df3acef7b9bd1b9da。原始代码指纹在code-audit-manifest.json；模拟访谈与评审原文保留，不把后续裁决反写成最初用户意见。')
    for image_path,caption in [(OUT/'prototype-desktop.png','离线原型桌面视图，演示数据；不是当前生产产品截图'),(OUT/'prototype-mobile.png','离线原型手机视图，演示数据')]:
        if image_path.exists():
            from PIL import Image as PILImage
            w,h=PILImage.open(image_path).size;scale=min(WIDTH/w,570/h)
            story.append(PageBreak());heading(caption);story.append(Image(str(image_path),width=w*scale,height=h*scale))
    def footer(c,doc):
        c.setFont(CN,7.5);c.setFillColor(colors.HexColor('#62747d'));c.drawString(42,A4[1]-30,'AI-QUANT  产品重设计 · 经授权的角色模拟与代码审查  2026-11-07');c.drawString(42,24,'设计提案 / 非真人调研 / 无真实用户改善指标');c.drawRightString(A4[0]-42,24,str(doc.page))
    Report(str(PDF),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=48,bottomMargin=43,title='AI-QUANT交易决策与训练工作台产品重设计方案',author='AI-QUANT design analysis').build(story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(PDF);text='\n'.join(page.extract_text() or '' for page in reader.pages)
    for token in ('P01','P10','E01','E02','E03','DecisionCase','T10','D12','37'):assert token in text,token
    manifest={'pdf':PDF.relative_to(ROOT).as_posix(),'pages':len(reader.pages),'sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'textChecks':'PASSED','visualReview':'PENDING',
              'realParticipants':0,'simulatedInvestorPerspectives':10,'simulatedExpertPerspectives':3,'designNeeds':len(trace),'productionModified':False}
    (OUT/'report-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest))
if __name__=='__main__':main()

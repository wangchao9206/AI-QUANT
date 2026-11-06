"""Real candle drawings and a complete fixed-candidate geometry experiment report."""
import hashlib,json,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import build_experiment_report as layout
from reportlab.platypus import SimpleDocTemplate,PageBreak,KeepTogether
from reportlab.graphics.shapes import Drawing,Line,Rect,String,Polygon
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from pypdf import PdfReader

DATA=ROOT/'docs/research/data/line-geometry-2026-11-07'
PDF=ROOT/'output/pdf/line-geometry-study-2026-11-07.pdf'
MD=ROOT/'docs/research/line-geometry-2026-11-07.md'
SH=timezone(timedelta(hours=8))
def load(name):return json.loads((DATA/name).read_text(encoding='utf-8'))
def local(value):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(SH).strftime('%Y-%m-%d %H:%M')
def color(line):
    kind=line['kind']
    return '#2b8ca3' if kind.startswith('REGRESSION') else '#835eb0' if kind.startswith('TREND') else '#558b59'
def chart(example):
    bars=example['points'];lines=example['geometry']['lines'];width=layout.WIDTH;height=285
    draw=Drawing(width,height);left=46;right=width-12;bottom=46;top=254
    prices=[v for b in bars for v in (b['low'],b['high'])]+[v for line in lines for v in (line['startPrice'],line['endPrice'])]
    low,high=min(prices),max(prices);padding=(high-low)*.08 or 1;low-=padding;high+=padding
    x=lambda i:left+(i+.5)*(right-left)/len(bars)
    y=lambda v:bottom+(v-low)/(high-low)*(top-bottom)
    draw.add(Rect(left,bottom,right-left,top-bottom,fillColor=colors.HexColor('#fafcfd'),strokeColor=colors.HexColor('#d7e1e8')))
    upper=next((line for line in lines if line['kind']=='REGRESSION_UPPER'),None)
    lower=next((line for line in lines if line['kind']=='REGRESSION_LOWER'),None)
    if upper and lower:
        coordinates=[x(upper['startIndex']),y(upper['startPrice']),x(upper['endIndex']),y(upper['endPrice']),x(lower['endIndex']),y(lower['endPrice']),x(lower['startIndex']),y(lower['startPrice'])]
        draw.add(Polygon(coordinates,fillColor=colors.HexColor('#e9f3f6'),strokeColor=None))
    for i in range(5):
        value=low+(high-low)*i/4;pos=y(value)
        draw.add(Line(left,pos,right,pos,strokeColor=colors.HexColor('#dbe3e8'),strokeWidth=.4))
        draw.add(String(0,pos-2,f'{value:,.1f}',fontName=layout.CN,fontSize=7,fillColor=colors.HexColor('#617182')))
    body=max(1,(right-left)/len(bars)*.65)
    for i,b in enumerate(bars):
        close=b.get('price',b.get('close'));shade=colors.HexColor('#cc5056' if close>=b['open'] else '#1c8a76')
        draw.add(Line(x(i),y(b['low']),x(i),y(b['high']),strokeColor=shade,strokeWidth=.6))
        draw.add(Rect(x(i)-body/2,min(y(b['open']),y(close)),body,max(.5,abs(y(close)-y(b['open']))),strokeColor=shade,fillColor=shade,strokeWidth=.3))
    for line in lines:
        draw.add(Line(x(line['startIndex']),y(line['startPrice']),x(line['endIndex']),y(line['endPrice']),strokeColor=colors.HexColor(color(line)),strokeWidth=1.1,
                      strokeDashArray=[4,3] if line['kind']=='REGRESSION_CENTER' or line['kind'].startswith('HORIZONTAL') else None))
    for i in (0,len(bars)//2,len(bars)-1):
        stamp=local(bars[i]['timestamp']);xx=x(i)
        draw.add(String(max(left,min(xx-33,right-70)),29,stamp[5:],fontName=layout.CN,fontSize=7,fillColor=colors.HexColor('#617182')))
    draw.add(String(left,9,'青色：回归通道   紫色：确认枢轴斜线   绿色虚线：前20柱高低点',fontName=layout.CN,fontSize=7.5))
    draw.add(String(left,270,'真实OHLC / 按柱序等距 / 自动线只代表所示截面已知条件',fontName=layout.CN,fontSize=8))
    return draw

def main():
    result=load('results.json');protocol=load('protocol.json');examples=load('chart-examples.json')
    model=json.loads((ROOT/'config/line-patterns.json').read_text(encoding='utf-8'))
    p,h,table=layout.p,layout.h,layout.table
    pct,n=layout.pct,layout.n;families=result['families']
    def path_text(path):return ' 且 '.join(model['featureLabels'].get(r['feature'],r['feature'])+(' > ' if r['operator']=='GT' else ' <= ')+str(r['threshold']) for r in path)
    def grade(value):return '概率提升有区间支持' if value.startswith('PROBABILITY_LIFT_SUPPORTED') else '概率改善待验证' if value.startswith('TENTATIVE') else '样本不足' if value.startswith('INSUFFICIENT') else '品种或阶段依赖'
    layout.story.append(layout.text('通道与趋势斜线\n画线及概率实验补充报告','Title'))
    p('执行日期：2026年11月7日。报告使用真实历史K线作图，记录自动线的拟合窗口、确认时点与价格，并检验画线条件和量能、缠论组合后的历史结果。')
    p(f"34个活跃品种，{result['labeledDecisions']:,}个符合既有活跃口径的截面，预先固定{result['candidateCount']}个候选。该批历史已经用于前几轮研究，不能冒称全新独立验证。图形上的漂亮线条不能替代概率、费用与失败记录。")
    improved=sum(v['improvedPatterns'] for v in families.values())
    p(f"实测：DEV选中{len(result['patterns'])}个候选，其中{improved}个在后段和留出品种均有标签概率改善，其余为阶段依赖或证据不足。附加量能和缠论并未普遍带来改善。")
    p(f"从上一轮64,605个活跃截面中，统一排除{len(result['geometryExclusions'])}个此前14柱没有价格波动、无法以ATR归一的截面。最初失败的协议、源码与运行记录保留；排除发生在本轮候选统计之前，所有实验组及对照执行相同口径。")
    h('一 图表新增的画线功能')
    p('实时看盘主图新增自动回归通道、确认高低点趋势斜线、水平支撑阻力三个开关。也可以手动画两点斜线、趋势射线、水平线、三点平行通道，支持预览、撤销、清空和Esc取消。手动画线按浏览器中的合约和周期保存，锚点使用时间戳与价格，行情窗口滚动时不重新绑定到别的K线。')
    p('手动画线仅作个人判断，不被当作自动训练结果，也不输入后台预警。已有锚点超出当前加载历史时暂时隐藏但记录保留。自动线有计算口径及可知时点；它是该截面的参考投影，不是未来价格预测。')
    h('二 自动通道与斜线的严格口径')
    table(['线形','口径','可知边界'],[
      ['回归通道','此前60柱收盘OLS直线；上下轨为中线加减2倍总体残差标准差','不含当前被评价完成柱及形成中柱'],
      ['水平支撑阻力','此前20柱最高价与最低价','只用当前柱之前的高低点'],
      ['枢轴斜线','前120柱内严格左右各2柱确认的高点／低点，最后两点间隔至少5柱','右侧确认柱完成后才可用；缺锚点则缺线'],
      ['突破／收回','将同一条旧线投影到前一柱与当前柱，比较两次收盘所在侧','不把当前价格拉入拟合后再宣称突破'],
    ],[78,235,layout.WIDTH-313])
    p('回归斜率按每根K线价格变动计算，除以前14柱ATR以跨品种比较。图上横轴按柱等距显示，休市间隔压缩。支撑／阻力斜线是连接确认枢轴的几何参考，不代表之后必然守住；倾斜方向和通道宽度均可能变化。')
    p('图上整段线是当前截面的拟合和投影，不表示左侧历史各个时点已经知道今天这条线。实验在每一个过去截面重新计算当时的线，使用同一冻结旧线判断当根突破，避免用最终全图回填历史买卖点。')
    h('三 四个固定截面的真实K线图')
    p('示例品种事先固定为螺纹钢、沪铜、豆粕和沪深300股指实际合约；各自取2026年10月1日之前最后121根记录。没有按是否盈利选例子，也不把示意图作为交易胜率证据。以下图中的所有K线均来自保存的实际OHLC，不切碎或补造更细周期。')
    for example in examples:
        layout.story.append(PageBreak());h(example['contract']+' 自动通道与斜线')
        p('历史截面：'+local(example['points'][-1]['timestamp'])+'（上海时间）。'+example['selection'])
        layout.story.append(chart(example));layout.story.append(layout.Spacer(1,10))
        table(['线／参考','起点价格','末端价格','可知时间'],[[line['label'],n(line['startPrice'],2),n(line['endPrice'],2),local(line['knownAt'])] for line in example['geometry']['lines']],[195,65,65,layout.WIDTH-325])
        p('原始输入SHA-256：'+example['sourceSha256'])
        p('实际几何特征：斜率/ATR '+n(example['geometry']['features']['line.slopeATR'])+'；通道宽度/ATR '+n(example['geometry']['features']['line.widthATR'])+'。不足两个确认锚点时不画对应趋势线。')
    layout.story.append(PageBreak());h('四 固定候选与结果反推过程')
    p('先沿用已经冻结的未来结果标签，再比较当时的几何条件。候选包括：上破上轨、下破下轨、下轨外收回、上轨外跌回、上破高点斜线、下破低点斜线、前20柱高低突破、上斜通道靠近下轨、下斜通道靠近上轨。每一类分别组合“仅线形／线形加量能／线形加缠论／三者结合”，没有根据后段结果挑阈值。')
    p('量能条件固定为当前完整柱量比大于1.2。缠论条件固定为存在已确认三笔中枢，并按预先记录的方向检查价格在中枢中的位置；它不是对全部一二三买卖点的检验。通道靠近范围固定为上下0.3ATR。这些是本轮检验的具体假设，不能说穷尽所有画线方法。')
    p(protocol['selection']);p(protocol['partitions']);p(protocol['costs'])
    p('DEV训练门槛为至少100截面、8品种、20正标签，且概率比匹配基准提升至少1个百分点；各实验组各目标最多按DEV改善保留2个。TIME、ASSET、RECENT只评价冻结候选，不改变阈值。对照按品种、月份、小时和分区匹配并排除事件自己；不是随机因果试验。')
    table(['分区','合格截面'],[[k,v] for k,v in result['partitions'].items()])
    table(['实验组','全部候选','DEV选中','后段与留出均改善'],[[v['label'],v['candidates'],v['selectedPatterns'],v['improvedPatterns']] for v in families.values()])
    p('路径数量不同、目标不同、信号重叠，不能仅用“改善条数”给四组作整体收益排名。所有候选，包括未过训练门槛、样本不足、阶段依赖和成本后为负的结果，均保留。')
    h('五 全部固定候选检验结果')
    p('表中概率均为特定未来结果标签的条件频率；不是实际账户赚钱概率。退出风险标签对应持仓不利路径，收益列为反向观察交易，不能当作实际平仓政策成绩。周块bootstrap仅缓解部分事件重叠，未完成多重试验确证。')
    for candidate in result['allCandidates']:
        start=len(layout.story)
        h(candidate['id']+' '+candidate['label'],2)
        p(path_text(candidate['path']))
        p(('DEV选中；' if candidate['selected'] else '未选中；')+grade(candidate['grade'])+'。训练拒绝原因：'+('、'.join(candidate['trainingRejectionReasons']) or '通过门槛；仍受每组每目标最多两条限制。'))
        table(['分区','截面/品种','概率/基准','提升百分点','平均净变动%','双倍成本%'],[[part,f"{s['samples']}/{s['roots']}",pct(s['probability'])+' / '+pct(s['matchedBaseProbability']),n(s['liftPp']),n(s['meanNetPct']),n(s.get('meanStressPct'))] for part,s in candidate['statistics'].items()],[42,58,130,83,94,layout.WIDTH-407])
        layout.story[start:]=[KeepTogether(layout.story[start:])]
    h('六 接入预警与使用边界')
    p('新增“通道／趋势线概率预警”模板，沿用后台概率预警的权限、租约、去重和记录机制。默认只展示后段及留出品种有改善的观察候选；探索范围可查看阶段依赖条件。启动、切换版本和延迟恢复不补发历史信号；过时、品种不符、活跃度不足、缺历史或缺线时不捏造预警。')
    p('事件冻结当时自动线坐标、锚点及可知时点、几何特征、固定条件、分区统计和模型版本。已有日线均线、基础概率和多周期缠论模型保留；没有自动修改用户任务。旧盘口扫描和每分钟盘口快照保持停用。')
    p('原始标签：入场观察以次柱开盘、1ATR止损、2ATR目标和16柱上限计算，基础成本每边1bp加1跳；双倍成本同时加倍两项。同柱止盈止损同时触及先计止损。次柱开盘是历史观察假设，实际信号确认、网络和成交延迟不保证能取得该价。')
    h('七 局限与可继续验证的问题')
    p('仍复用前几轮已经使用的历史，且只取采集时活跃合约，不是历史完整可投资市场；不能将本轮结果称为新的独立验证或实盘收益。96个相关候选和重叠持有窗口增加选择偏差，周区间不代表已消除过拟合。')
    p('本轮通道为收盘线性回归加残差宽度，未声称验证安德鲁斯叉、任意手画通道或全部图形学方法。枢轴左右确认有延迟，自动线随后续数据更新；手动画线依赖人的判断，若未来要检验，必须冻结当时的锚点与理由，再用后续新行情验证。')
    p('下一步应在冻结候选后收集新的市场日期，分别比较线形本身、量能和缠论附加条件带来的覆盖率、标签概率、成本后期望与漂移；不能只展示穿线后上涨的几个例子。')
    h('八 完整证据与复现')
    p('核心：backtesting/line_geometry.py；固定实验：scripts/research_line_geometry.py；实时匹配：algorithm_service/line_monitor.py；图形报告：scripts/build_line_geometry_report.py。原始输入每份均按采集SHA-256复核；完整截面、所有候选路径、失败原因及源代码快照在本报告同名证据目录中。')
    p('源数据保留在本机data/history/intraday-active-study。4个图例的真实OHLC及每条线坐标保存在chart-examples.json，方便核对图形。未将授权原始行情全集上传到公开仓库。')
    manifest=[{'path':f.relative_to(ROOT).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(DATA.iterdir()) if f.is_file()]
    table(['证据文件','字节数','SHA-256'],[[r['path'],r['bytes'],r['sha256']] for r in manifest],[192,62,layout.WIDTH-254])
    MD.write_text('\n'.join(layout.markdown),encoding='utf-8')
    def footer(canvas,doc):
        canvas.setFont(layout.CN,8);canvas.setFillColor(colors.HexColor('#62707d'));canvas.drawString(42,A4[1]-32,'AI-QUANT  通道与趋势斜线实验  2026-11-07')
        canvas.drawString(42,25,'真实历史K线 / 当时已知几何条件 / 非确定性交易指令');canvas.drawRightString(A4[0]-42,25,str(doc.page))
    SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=52,bottomMargin=46,
                      title='通道与趋势斜线画线及概率实验补充报告',author='AI-QUANT experiment records').build(layout.story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(PDF);extracted='\n'.join(p.extract_text() or '' for p in reader.pages)
    for value in ('34',str(result['candidateCount']),examples[0]['contract'],'OLS'):assert value in extracted,value
    receipt={'pdf':PDF.relative_to(ROOT).as_posix(),'pages':len(reader.pages),'sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'textChecks':'PASSED','visualReview':'PENDING','evidenceFiles':manifest}
    (ROOT/'output/pdf/line-geometry-report-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pages':len(reader.pages),'bytes':PDF.stat().st_size,'pdf':str(PDF)}))

if __name__=='__main__':main()

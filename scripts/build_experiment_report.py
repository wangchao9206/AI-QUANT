"""Render the complete experiment report from actual frozen artifacts, without invented results."""
import base64,gzip,hashlib,json,math,subprocess
from datetime import datetime,timedelta,timezone
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
from reportlab.graphics.shapes import Drawing,String,Rect
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'docs/research/data';OUT=ROOT/'output/pdf';OUT.mkdir(parents=True,exist_ok=True)
REPORT=OUT/'active-futures-outcome-study-2026-11-07.pdf'
CN='CN';pdfmetrics.registerFont(TTFont(CN,'C:/Windows/Fonts/msyh.ttc',subfontIndex=0))
styles={
 'Title':ParagraphStyle('Title',fontName=CN,fontSize=24,leading=35,spaceAfter=24,textColor=colors.HexColor('#142839')),
 'H1':ParagraphStyle('H1',fontName=CN,fontSize=15,leading=23,spaceBefore=16,spaceAfter=10,keepWithNext=True),
 'H2':ParagraphStyle('H2',fontName=CN,fontSize=11.5,leading=18,spaceBefore=12,spaceAfter=7,keepWithNext=True),
 'Body':ParagraphStyle('Body',fontName=CN,fontSize=9.2,leading=16,spaceAfter=8,wordWrap='CJK'),
 'Cell':ParagraphStyle('Cell',fontName=CN,fontSize=7.6,leading=11.5,wordWrap='CJK'),
 'Header':ParagraphStyle('Header',fontName=CN,fontSize=7.8,leading=12,textColor=colors.white,wordWrap='CJK'),
 'Small':ParagraphStyle('Small',fontName=CN,fontSize=7.6,leading=12,spaceAfter=6,wordWrap='CJK'),
}
story=[];markdown=[];WIDTH=A4[0]-84
def load(name):return json.loads((DATA/name/'results.json').read_text(encoding='utf-8'))
def text(s,style='Body'):return Paragraph(escape(str(s).replace('—','-').replace('–','-')).replace('\n','<br/>'),styles[style])
def p(s):story.append(text(s));markdown.extend([str(s),''])
def h(s,level=1):story.append(text(s,'H1' if level==1 else 'H2'));markdown.extend(['#'*level+' '+s,''])
def table(headers,rows,widths=None):
    cells=[[text(v,'Header') for v in headers]]+[[text(v,'Cell') for v in row] for row in rows]
    t=Table(cells,colWidths=widths or [WIDTH/len(headers)]*len(headers),repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#233e51')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f2f5f7')]),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#233e51'))]))
    story.extend([t,Spacer(1,10)])
    markdown.extend(['| '+' | '.join(map(str,headers))+' |','| '+' | '.join('---' for _ in headers)+' |'])
    markdown.extend('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in row)+' |' for row in rows);markdown.append('')
def n(v,digits=3):return '未报告' if v is None else f'{v:,.{digits}f}'
def pct(v):return '未报告' if v is None else f'{v*100:.2f}%'
def ci(v,percent=True):return '不报告（周数不足）' if v is None else ' 至 '.join(pct(x) if percent else n(x) for x in v)
def path(rule):return f"{FEATURES.get(rule['feature'],rule['feature'])} {'<=' if rule['operator']=='LE' else '>'} {rule['threshold']:.6f}"
FEATURES={
 'dayMA5DistancePct':'价格距日线MA5百分比','dayMA20DistancePct':'价格距日线MA20百分比','dayMA20Slope5Pct':'日线MA20五日斜率百分比','dayMA5vs20Pct':'日线MA5相对MA20百分比',
 'minuteMA20DistanceATR':'价格距15分钟MA20除以ATR','minuteMA5vs20ATR':'15分钟MA5与MA20之差除以ATR','minuteMA20Slope5ATR':'15分钟MA20五柱斜率除以ATR','macdHistogramATR':'MACD双倍柱除以ATR',
 'rsi14Simple':'RSI14简单均值','volumeRatio20':'当前柱量除以前20柱均量','atrPct':'15分钟ATR占价格百分比','closeLocation':'收盘在柱内的位置','bodyATR':'当前柱实体除以ATR','return4ATR':'过去四柱价格变动除以ATR','oiChange5Pct':'持仓量五柱变化百分比'}

def plot(patterns,part,title):
    items=[r for r in patterns if r['statistics'][part]['probability'] is not None]
    draw=Drawing(WIDTH,280);draw.add(String(0,264,title,fontName=CN,fontSize=10))
    chart=HorizontalBarChart();chart.x=112;chart.y=36;chart.width=WIDTH-126;chart.height=210
    chart.data=[tuple(r['statistics'][part]['probability']*100 for r in items),tuple(r['statistics'][part]['matchedBaseProbability']*100 for r in items)]
    chart.categoryAxis.categoryNames=[r['id'] for r in items];chart.categoryAxis.labels.fontName=CN;chart.categoryAxis.labels.fontSize=7
    chart.valueAxis.valueMin=0;chart.valueAxis.valueMax=50;chart.valueAxis.valueStep=10;chart.valueAxis.labels.fontName=CN;chart.valueAxis.labels.fontSize=7
    chart.bars[0].fillColor=colors.HexColor('#255e82');chart.bars[1].fillColor=colors.HexColor('#b6c2cb');chart.barSpacing=1;chart.groupSpacing=5
    draw.add(chart);draw.add(Rect(112,7,10,7,fillColor=colors.HexColor('#255e82'),strokeColor=None));draw.add(String(128,7,'条件下标签频率',fontName=CN,fontSize=8))
    draw.add(Rect(266,7,10,7,fillColor=colors.HexColor('#b6c2cb'),strokeColor=None));draw.add(String(282,7,'同类对照频率  坐标单位 %',fontName=CN,fontSize=8))
    story.extend([draw,Spacer(1,12)]);markdown.extend(['图：'+title+'。所有数值见下方逐组合表。',''])

def main():
    result=load('outcome-discovery-2026-11-07');quality=json.loads((DATA/'outcome-discovery-2026-11-07/verification.json').read_text(encoding='utf-8'))
    protocol=json.loads((DATA/'outcome-discovery-2026-11-07/protocol.json').read_text(encoding='utf-8'))
    v1=load('trend-opportunities-2026-11-07');v2=load('trend-feedback-2026-11-07-r2');intra=load('intraday-alert-validation-2026-11-07')
    now=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds');head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    story.extend([Spacer(1,70),text('活跃期货结果反推实验报告','Title')]);markdown.extend(['# 活跃期货结果反推实验报告',''])
    p('实验主题：先识别已经发生的历史走势与进出场结果，再反推事前特征及其条件概率，并接入实时预警。')
    p('执行日期：2026年11月7日。报告生成时刻：'+now+'。基础仓库提交（本轮扩展前）：'+head+'。最终交付提交以仓库记录为准。')
    p('本轮不是寻找100%成功的公式。34个活跃品种形成87,976个带未来结果标签的决策截面，训练筛出11组历史条件线索。部分组合在后续时间和留出品种中出现相对基准的概率提升；概率提升不等于费用后必然盈利，也不代表已完成实盘前向验证。')
    p('报告由真实运行输出自动汇编。实测结果、解释及待验证事项分别标注；没有把未执行的实验、独立性或成交保证写成事实。完整代码、压缩事件、源指纹与失败记录另附。')
    story.append(PageBreak())
    h('一 实验问题与结果反推路线')
    p('用户目标是在实时看盘中筛选上涨、下跌、转折以及较合适的入场与离场机会。最终确认的方法是：先看历史结果，再推导过程；要求至少十几个活跃品种，而不是一两个品种的例子。')
    p('实际研究路线依次为：预设日线条件检验；针对失败结果加入量价、波动和退出过滤；补采15分钟真实合约；扩大到34个活跃品种；以未来结果作为历史标签，反向学习过去已知特征的组合；在分离的时间和品种中检验；将符合条件的历史概率线索用于预警。前几轮失败没有删除。')
    table(['概念','本报告的含义'],[
        ['实测结果','从保存的数据、标签或事件计算出的样本数、条件频率、成本后变动和校验状态。'],
        ['推导解释','为什么某类量价或位置可能与结果相关。相关性不是因果证明，解释不替代数据。'],
        ['待验证假设','标签、样本、成本或市场状态改变后，规律能否继续成立。必须重新验证，不能填上想当然的数值。'],
        ['概率目标','P(特定未来结果标签成立 | 当前满足组合条件)，与同类对照比较。不是要求每次正确，也不是当前单次获利保证。']])
    h('二 数据来源与完整性核对')
    p('日线研究使用81份标准实际交割合约和换月日线缓存，共137,790根记录，最长覆盖2016年至2026年10月30日，各品种历史长度不同。内部核对通过不等于独立行情源认证；缓存品种池也不是完整的历史可投资品种池。')
    p(f"最终反推研究单独采集34个当前活跃期货实际交割合约，原始15分钟柱 {result['rawBars']:,} 根；按生命周期断档规则清洗后 {result['usableBars']:,} 根。最近20个完整日线成交量中位数必须至少10,000手。所有34个候选在采集时通过该阈值。")
    p('使用独立TqSdk进程、模拟账号接口做只读数据收集，没有调用任何下单方法。SDK序列最多请求8,000根，实际有效数量以返回值为准。当前活跃合约名单由采集时点决定，存在幸存者、合约生命周期和时点选择偏差。')
    p('发现交易所代码复用造成跨年代序列拼接。对日线时间差超过365天的断档，只保留最后一个生命周期，并同步截断15分钟序列。这是数据质量处理，不按盈利筛选。每个合约的剔除数量见下表。')
    universe=[]
    for item in result['data']:
        universe.append([item['root'].split('.')[-1].upper(),item['contract'],n(item['medianCompleteDailyVolume20'],0),str(item['bars15m']),str(item['usableBars']),str(item['lifecycleRejected'])])
    table(['品种','实际合约','20日量中位数','原始15分柱','清洗后','剔除旧生命周期'],universe,[42,103,85,70,70,WIDTH-370])
    h('三 结果标签的精确定义')
    p('令 t 为已经完成的15分钟柱，t+1 为其后继柱。特征只取截至 t 的分钟柱和当时已经完成的日线；历史执行假设从 t+1 的实际开盘价格开始。未来最多16根柱只用于构造训练标签，不进入实时特征计算。')
    table(['结果目标','历史标签成立的条件'],[
        ['多头入场窗口 LONG_ENTRY','未来16根内，上涨2个事前ATR先于下跌1个ATR，并且按费用假设计算后为正；同一柱同时触及两个门槛按不利路径。'],
        ['空头入场窗口 SHORT_ENTRY','未来16根内，下跌2个事前ATR先于上涨1个ATR，并且计成本后为正，规则与多头对称。'],
        ['后续上行 UP_MOVE','从次柱开盘起，第8根收盘至少高于入场参考价格1个事前ATR。'],
        ['后续下行 DOWN_MOVE','从次柱开盘起，第8根收盘至少低于入场参考价格1个事前ATR。'],
        ['向上转折 LOW_TURN','当前柱低点严格低于前4柱及后4柱低点，并在未来第8根收盘至少回升到当前收盘加1个ATR。'],
        ['向下转折 HIGH_TURN','当前柱高点严格高于前4柱及后4柱高点，并在未来第8根收盘至少回落到当前收盘减1个ATR。'],
        ['多头回撤风险 EXIT_LONG','未来8根最大不利波动至少1.5ATR，且第8根收盘仍低于入场参考价格0.5ATR。'],
        ['空头反弹风险 EXIT_SHORT','未来8根最大不利波动至少1.5ATR，且第8根收盘仍高于入场参考价格0.5ATR。']],[150,WIDTH-150])
    p('这些是本次可计算的结果定义，并非市场唯一的“最佳进出场”定义。转折概率14%不表示其余86%全部亏损：未形成严格局部转折仍可能上涨、横盘或小幅盈利。LONG_ENTRY标签频率与所有观察交易的成本后盈利比例也不是同一指标。')
    p('费用观察模型为每边名义金额1bp加每边一个不利跳动；止损／目标以连续价格距离作为研究门槛。这不是含排队、涨跌停、资金、保证金、每笔价格取整及完整历史经纪商费用的交易撮合器。收益为名义事件百分比，不是可投入账户的收益。')
    h('四 所有事前特征与计算公式')
    table(['特征','实际计算'],[
        [FEATURES['dayMA5DistancePct'],'100 × (当前完整15分钟收盘 / 前5个完整日线收盘均值 - 1)。'],
        [FEATURES['dayMA20DistancePct'],'100 × (当前完整15分钟收盘 / 前20个完整日线收盘均值 - 1)。'],
        [FEATURES['dayMA20Slope5Pct'],'100 × (当前日线MA20 / 五个日线柱之前的MA20 - 1)。'],
        [FEATURES['dayMA5vs20Pct'],'100 × (日线MA5 / 日线MA20 - 1)。'],
        [FEATURES['minuteMA20DistanceATR'],'(15分钟收盘 - 15分钟MA20) / ATR14。'],
        [FEATURES['minuteMA5vs20ATR'],'(15分钟MA5 - 15分钟MA20) / ATR14。'],
        [FEATURES['minuteMA20Slope5ATR'],'(15分钟MA20 - 五柱前MA20) / ATR14。'],
        [FEATURES['macdHistogramATR'],'2 × (DIF - DEA) / ATR14；DIF=EMA12-EMA26，DEA=EMA9(DIF)。EMA在最后120根内以首值初始化，训练／实时一致。'],
        [FEATURES['rsi14Simple'],'最近14个收盘变动的平均上涨额 / 平均上涨额与平均下跌额之和 ×100；无涨跌时50。是简单均值版本，不是Wilder递推。'],
        [FEATURES['volumeRatio20'],'当前完整柱成交量 / 此前20根完整柱平均成交量，不纳入当前柱进分母。'],
        [FEATURES['atrPct'],'ATR14 / 当前收盘 ×100；TR=max(高-低, abs(高-前收), abs(低-前收))，ATR取最近14个TR算术平均。'],
        [FEATURES['closeLocation'],'(收盘-最低)/(最高-最低)，取值0至1；零区间时0.5。'],
        [FEATURES['bodyATR'],'(当前收盘-当前开盘) / ATR14。'],
        [FEATURES['return4ATR'],'(当前收盘-四柱前收盘) / ATR14。'],
        [FEATURES['oiChange5Pct'],'100 × (当前持仓量/五柱前持仓量 -1)。实现对缺失或无效分母使用0并返回缺失状态；本批原始15分钟输入缺失持仓字段数经核对为0。']],[160,WIDTH-160])
    p('特征函数至少需要120根分钟柱和25根已完成日线。未来柱、当前未完成日线及未来结果标签不作为特征。实时模型复用同一个函数，未另写一套近似指标。')
    h('五 推导规则与时间品种分离')
    p('每个结果目标分别训练一棵最大深度3的可解释二叉树。候选阈值只取训练样本特征的20%、40%、60%、80%分位数，以Gini不纯度降低选择分裂；每个叶子至少400个截面。该方法从带结果的样本反推最多三个事前条件的组合，不把教科书形态当作已证实规律。')
    p('叶子在训练集中的目标频率要比训练总体至少高3个百分点、目标成立至少30次、覆盖至少12个训练品种。每个目标最多保留两组，按训练概率提升排序。没有满足条件的目标不强补。最终得到11组；UP_MOVE没有满足本轮筛选限制的叶子，这不证明市场不存在上涨规律。')
    table(['分区','数据范围','截面数'],[
        ['开发 DEV','26个训练品种，2026年7月之前；未来标签不能跨7月边界。',str(result['partitions']['DEV'])],
        ['时间检验 TIME','相同26个品种，2026年7至9月；不用于拟合阈值或训练叶子筛选。',str(result['partitions']['TIME'])],
        ['品种检验 ASSET','另8个品种，2026年7至9月；从本次模型拟合中留出。',str(result['partitions']['ASSET'])],
        ['近期比较 RECENT','全部34个品种，2026年10月以后至采集截止。',str(result['partitions']['RECENT'])]],[95,WIDTH-155,60])
    p('训练品种：'+'、'.join(s.split('.')[-1].upper() for s in result['trainingRoots'])+'。')
    p('留出品种：'+'、'.join(s.split('.')[-1].upper() for s in result['heldoutRoots'])+'。分组用品种名称SHA-256排序预先决定，不按成绩挑选。这里的“留出”仅指本次模型的拟合；这些历史日期曾用于项目其他探索，不能称从未看过的独立新历史。')
    h('六 条件概率 对照与不确定性')
    p('条件概率 P(Y=1|C)=该组合中目标成立截面数/满足组合的截面数。同类基准按品种、分区、年月、小时分组，排除该截面自己后计算；最终按该组合截面加权。提升百分点=条件频率与同类基准频率之差，不是收益率。对照不是随机干预，不能作因果归因。')
    p('使用500次按周分块重抽样，保留同一周不同品种共同波动及部分序列相关；至少8周才给出约95%百分位区间。区间把已估计匹配基准视为固定，未完整传播基准估计误差；多目标、多叶子也没有做确证性的多重检验校正。因此分层名为探索性证据，不是统计确证或已校准的实时胜率。')
    p('样本数是决策截面，不是独立交易数：后续16柱标签会重叠，同一时间多个品种可能共同受市场因素影响。近期仅约5周，区间不报告，不能补造一个精确范围。')
    table(['证据分层','实际含义'],[
        ['本次分块估计支持概率提升','时间检验和留出品种均有正提升，样本覆盖达门槛，且本次条件化区间下界为正；仍不是盈利证明。'],
        ['概率改善待验证','两类检验的点估计改善，但区间可能跨零，继续观察。'],
        ['品种或阶段依赖','不同品种或时间段的提升方向不一致，不统一判成失效，也不宣传成普适优势。'],
        ['样本不足或近期走弱','明确显示不足或衰减；不要求100%成功，用层级、幅度和不确定性判断。']])
    h('七 全部推导组合与检验结果')
    plot(result['patterns'],'TIME','图1 同品种后段的结果标签概率与匹配基准')
    plot(result['patterns'],'ASSET','图2 留出品种的结果标签概率与匹配基准')
    for pattern in result['patterns']:
        h(pattern['id']+' '+pattern['label'],2)
        p('数据推导条件：'+'；且 '.join(path(rule) for rule in pattern['path'])+'。')
        p('探索性分层：'+pattern['grade']+'。阈值是本批训练数据产生的数值，不是市场通用常数；预警使用完整精度，报告为阅读显示六位小数。')
        table(['分区','n/品种','结果概率','匹配基准','提升百分点','观察交易均净变动%'],[
            [part,f"{s['samples']}/{s['roots']}",pct(s['probability']),pct(s['matchedBaseProbability']),n(s['liftPp']),n(s['meanNetPct'])]
            for part,s in pattern['statistics'].items()],[65,60,75,75,80,WIDTH-355])
        table(['分区','周数','目标概率区间','提升百分点区间','目标成立数／成本后正值比例'],[
            [part,str(s.get('weeks',0)),ci(s.get('probabilityInterval')),ci(s.get('liftIntervalPp'),False),f"{s.get('positiveLabels',0)} / {pct(s.get('costPositiveFraction'))}"]
            for part,s in pattern['statistics'].items()],[65,40,125,125,WIDTH-355])
        p('收益列采用统一的1ATR止损、2ATR目标、最多16根柱的独立观察交易；对EXIT_LONG等风险标签，收益列是反向观察，不是“实际平仓比继续持有好多少”的已验证平仓策略。',)
    audit_file=DATA/'outcome-discovery-2026-11-07/tree-candidate-audit.json'
    if audit_file.exists():
        audit=json.loads(audit_file.read_text(encoding='utf-8'))
        h('全部候选叶与未入选原因')
        p(f"另行重建了全部 {audit['testedSplitComparisons']:,} 次候选分裂比较和 {audit['allLeaves']} 个终端叶子，所有叶子及最终11组选择与冻结实现一致。这里不是只保留表现好的组合；未通过门槛的路径也列出。全部节点的分裂增益、左右样本与候选阈值保存在tree-candidate-audit.json。")
        rejection={'TRAINING_LIFT_BELOW_3PP':'训练提升不足3个百分点','POSITIVE_LABELS_BELOW_30':'正标签不足30次','TRAINING_ROOTS_BELOW_12':'训练覆盖不足12品种'}
        for target,item in audit['targets'].items():
            h(target+' 的所有训练叶子',2)
            table(['事前条件路径','样本/正标签/品种','训练概率/基准','选择或拒绝原因'],[
                ['；且 '.join(path(rule) for rule in leaf['path']),f"{leaf['samples']}/{leaf['positiveLabels']}/{leaf['roots']}",
                 pct(leaf['probability'])+' / '+pct(leaf['trainingBase']),
                 '入选' if leaf['selected'] else '；'.join(rejection.get(reason,reason) for reason in leaf['rejectionReasons']) or '训练排序在前两名之外']
                for leaf in item['leaves']],[220,75,85,WIDTH-380])
    h('八 主要发现的解释与反例')
    p('实测：LOW_TURN_1 在时间检验中为474/3240=14.63%，匹配基准3.79%；留出品种为143/987=14.49%，基准3.82%。其组合是过去四柱价格变化不高于-0.354430个ATR、当前柱量大于此前20柱均量的1.238901倍、收盘位置高于柱内0.111111。')
    p('解释：短期下行后量能增加，同时收盘未停在极低位置，与随后形成严格局部低点的频率相关。这是相关性线索，不证明量能本身“造成”反转；也不表示每次下跌放量都能抄底。近期该标签频率约12.09%，同类基准约3.57%。')
    p('实测：HIGH_TURN_1 的镜像组合在时间检验约14.57%、基准3.80%；留出品种约14.06%、基准3.49%。它可以提示局部转折观察或多头风险复核，但该固定观察退出下的均净变动仍为负，不能直接称盈利做空系统。')
    p('实测：LONG_ENTRY_1 在时间检验约34.83%、基准31.61%，留出品种约38.84%、基准33.13%；两类区间均可跨零，属于概率改善待验证。其费用后平均观察变动分别约-0.0541%和-0.0137%。因此概率提升、名义盈亏比与实际期望要分开看。')
    p('实测：EXIT_SHORT_1 的空头反弹风险标签在时间检验约33.86%、基准30.57%，留出品种约40.52%、基准32.95%。它适合用于“是否需要复核空头风险”的提示；本次没有验证某条具体平仓委托的资金效果。')
    h('九 入场 离场与止损的使用边界')
    p('入场观察：优先查看条件是否属于当前模型范围、历史概率比匹配基准提升多少、跨品种是否一致、成本后观察均值是否为正、当前价格距原触发点有多远。不要将低频转折标签的概率直接当成盈利胜率。')
    p('离场观察：多头回撤风险、空头反弹风险、反向转折候选可以帮助复核持仓。实际何时平仓还取决于已有入场成本、持仓方向、保护价、交易成本和风险预算，本次未接入账户自动决策。')
    p('最适合的单点不能由历史局部最高／最低价直接搬到实时。历史标签允许使用未来确认“事后发生了什么”，但实时只能判断“目前特征与哪类历史结果更相似”。没有未来数据时，拐点始终是候选。')
    h('十 前序实验与反馈过程')
    p('最初三轮先验证预设条件，确实不完全符合用户后来确认的“从结果反推”核心。它们作为失败与对照保留，之后改用结果标签反向推导，没有把旧研究包装成最终方法。')
    table(['实验','真实规模','主要结果与后续动作'],[
        ['固定日线条件','81份标准缓存；10条件×4持有期；141,345条结果','没有条件通过原有跨时段门槛。转向分析量能、波动、距离及退出机制，保留失败结果。'],
        ['反馈改进滚动检验','48候选+12对照；修正后244,525条结果','每年只用前三年选条件；选中420条后段事件均值-0.2134%，对照2592条-0.0159%。多年份没有合格训练候选，不强选。'],
        ['8合约15分钟专项','42,570根原始，38,961根清洗后；61,154条结果','MA20跨越等未呈稳定成本后优势；8个合约不足用户最终范围要求，所以扩充为34个活跃品种。'],
        ['结果反推实验','34活跃品种；173,560根原始，155,515根清洗后；87,976个标签截面','26品种推导、8品种留出；11组条件；相对概率分层，不要求100%成功。']],[108,145,WIDTH-253])
    p('第二轮第一次执行缺少未来零成交量柱保护；完成的原结果标为拒绝用于推广，保留其原源码与结果。修正仅增加零成交量执行拒绝并加回归测试，未按盈利成绩改参数。修正前244,635条、修正后244,525条，差异110条；选中折的420条汇总未变。')
    h('十一 前序全部固定条件与持有期')
    for name,value in v1['conditions'].items():
        h(name+' '+value['label'],2)
        table(['持有期','开发 n/均净%','2023-24 n/均净%','2025-26 n/均净%'],[
            [period]+[str(stats[part]['samples'])+' / '+n(stats[part]['meanNetPct']) for part in ('DEVELOPMENT','VALIDATION','RETROSPECTIVE_2025_2026')]
            for period,stats in value['horizons'].items()],[65,(WIDTH-65)/3,(WIDTH-65)/3,(WIDTH-65)/3])
    h('十二 逐年反馈检验选择与对照')
    table(['检验年','只用训练年份','训练选中的候选','检验 n/均净%','对照 n/均净%'],[
        [f['year'],str(f['trainingYears']),f['selected'] or '门槛不足，不选',
         str(f.get('test',{}).get('samples',0))+' / '+n(f.get('test',{}).get('meanNetPct')),
         str(f.get('control',{}).get('samples',0))+' / '+n(f.get('control',{}).get('meanNetPct'))] for f in v2['folds']],[48,80,160,(WIDTH-288)/2,(WIDTH-288)/2])
    p('全60个候选在每个训练窗口的成绩都保存在对应results.json中。对照同方向、同退出，但事件日期／数量不同，不是随机匹配实验。未把其差异当作因果改善或某个资金账户表现。')
    h('十三 专项15分钟全部持有期')
    for name,value in intra['conditions'].items():
        h(name,2)
        table(['持有15分柱数','开发 n/均净%','7-9月 n/均净%','10月后 n/均净%'],[
            [period]+[str(stats[part]['samples'])+' / '+n(stats[part]['meanNetPct']) for part in ('DEVELOPMENT','VALIDATION','RECENT_COMPARISON')]
            for period,stats in value['horizons'].items()],[65,(WIDTH-65)/3,(WIDTH-65)/3,(WIDTH-65)/3])
    p('该专项中的MA5条件是15分钟OHLC触及并收回代理。逐笔盘中接近／触及的顺序不能从OHLC精确还原，因此没有把其统计移植为逐笔触及胜率。')
    h('十四 审计结果与未伪造边界')
    table(['核对项目','实际结果'],[[k,str(v)] for k,v in quality.items()],[195,WIDTH-195])
    p('全部87,976个截面核对了来源指纹、日线参考先后关系、后继柱确认和时间／品种分区；另外随机固定种子抽1000个截面，从原始输入重新调用相同的冻结共享函数，核对全部特征与结果标签，结果一致。这检查归档和对齐一致性，不构成另一个算法实现的独立验证，也不是独立行情源认证。')
    p('没有生成或补齐缺失行情，没有把分钟线假装逐笔盘口，没有把原始根数当作独立交易笔数，没有把历史条件频率当作实时确定概率，没有把负均值删去，也没有把未测的前向收益写成完成。')
    h('十五 已接入的实时预警行为')
    p('实时看盘的“期货后台监控 · 机会预警”新增“结果反推 · 概率预警”模板。可选择入场窗口、离场风险、转折候选、走势方向或全部；可只接收概率改善候选，也可包含品种／阶段依赖的探索条件。')
    p('实时计算仅使用完整15分钟柱及当时已完成日线；只在新柱确认附近产生新预警。创建时建立基线、不回放旧信号；每根柱与条件组合去重。期权、非15分钟、未覆盖品种或不满足活跃度时明确不给模型推断。')
    p('触发依据保存模型版本、匹配条件、当时特征、特征时点、确认时点、记录可得时点，以及各检验阶段样本和概率。关闭页面后服务器继续执行；不自动改已有任务、不自动开平仓。首次触发和实时前向效果尚未据此报告为已经验证。')
    validation=DATA/'outcome-discovery-2026-11-07/final-validation.json'
    if validation.exists():
        h('程序与部署验收',2)
        table(['验收项目','实际状态'],[[k,str(v)] for k,v in json.loads(validation.read_text(encoding='utf-8')).items()],[205,WIDTH-205])
        p('组件测试及静态资源一致性核对不等于登录后的浏览器视觉验收。本轮没有将其写成已完成实盘交易或前向获利证明。')
    h('十六 局限与下一轮反馈路径')
    for line in [
        '当前活跃合约样本不是完全历史可投资品种池；不同品种、年份、日内时段具有相关性。',
        '历史日期和部分品种曾在项目中被观察；虽然本次阈值拟合严格分离时间和品种，仍不能称全新盲测或前瞻实盘。',
        '结果定义、ATR尺度、16柱观察窗和成本假设是研究选择；更改这些定义需新版本，不能继续沿用原概率。',
        '周块区间条件化于已估计对照，未做多重检验确证；近期只有约5周而未报区间。',
        '浅树适合解释，不保证捕捉所有交互；未筛到某类目标不等于证明该规律不存在。',
        '没有历史完整盘口排队、委托撤单和全部经纪商费用；本次收益不能声称还原真实账户。',
        '下一轮应按事先记录的反馈问题新增样本或新窗口，比较条件概率、校准和费用后期望，保留失败与漂移；不要为追求全正而反复换阈值。']:
        p(line)
    h('十七 来源与完整证据索引')
    p('方法参考原始研究：Bailey 等 The Probability of Backtest Overfitting，https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf 。它支持警惕多重试验过拟合，并不证明本次模型有效。行情接口说明：https://doc.shinnytech.com/tqsdk/latest/usage/mddatas.html 。')
    names=['trend-opportunities-2026-11-07','trend-feedback-2026-11-07','trend-feedback-2026-11-07-r2','intraday-alert-validation-2026-11-07','outcome-discovery-2026-11-07']
    manifests=[]
    for dirname in names:
        for file in sorted((DATA/dirname).iterdir()):
            if file.is_file():manifests.append({'path':str(file.relative_to(ROOT)).replace('\\','/'),'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
    table(['证据文件','字节数','SHA-256（完整）'],[[r['path'],r['bytes'],r['sha256']] for r in manifests],[205,55,WIDTH-260])
    p('原始新行情位于本机data/history/intraday-active-study，未提交完整SDK行情文件。每个输入的完整SHA-256保存在结果文件；压缩标签和事件保留计算过程。冻结源码包以原始字节保存，避免不同平台换行影响核验。')
    h('十八 所有输入指纹')
    table(['活跃实际合约','输入文件','原始输入 SHA-256'],[[r['contract'],r['file'],r['sha256']] for r in result['data']],[105,95,WIDTH-200])
    p('日线81个输入的指纹、内部核对状态、起止日期和可用天数详见首轮results.json的data数组；滚动检验另附逐品种审计。没有用未记录来源的演示数据替代。')
    h('十九 复现路径与报告一致性')
    p('脚本：scripts/research_trend_opportunities.py；scripts/validate_trend_feedback.py；scripts/collect_intraday_validation.py；scripts/validate_intraday_alerts.py；scripts/discover_outcome_patterns.py。已完成实验目录拒绝覆盖；复现应在独立工作目录或新命名输出中进行，并保留输入、协议及源码指纹。')
    p('实时共享特征与标签模块为backtesting/outcome_features.py；实时匹配模块为algorithm_service/outcome_monitor.py。实时路径只调用vector和matches，未来targets仅用于离线标签；测试通过故障注入确保实时匹配不调用未来标签器。')
    p('本PDF与Markdown由同一报告生成器读取真实JSON构建。附录清单指向全部中间分析，不把巨量事件压成无从核验的结论。最初8合约专项仅是历史探索，最终核心结论来自34个活跃品种的结果反推实验。')
    md=ROOT/'docs/research/outcome-first-2026-11-07.md';md.write_text('\n'.join(markdown),encoding='utf-8')
    def footer(canvas,doc):
        canvas.setFont(CN,8);canvas.setFillColor(colors.HexColor('#62707d'));canvas.drawString(42,A4[1]-32,'AI-QUANT  活跃期货结果反推实验  2026-11-07')
        canvas.drawString(42,25,'历史条件概率参考 / 非确定性交易指令');canvas.drawRightString(A4[0]-42,25,str(doc.page))
    doc=SimpleDocTemplate(str(REPORT),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=52,bottomMargin=46,title='活跃期货结果反推实验报告',author='AI-QUANT experiment records')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(REPORT);extracted='\n'.join(page.extract_text() or '' for page in reader.pages)
    for required in ['34','87976','LOW_TURN_1','LONG_ENTRY_1','EXIT_SHORT_1']:
        assert required in extracted.replace(',',''),required
    receipt={'pdf':str(REPORT.relative_to(ROOT)).replace('\\','/'),'pages':len(reader.pages),'sha256':hashlib.sha256(REPORT.read_bytes()).hexdigest(),
        'generatedAt':now,'markdown':str(md.relative_to(ROOT)).replace('\\','/'),'evidenceFiles':manifests,'textChecks':'PASSED','visualReview':'PENDING'}
    (OUT/'report-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pages':len(reader.pages),'pdfBytes':REPORT.stat().st_size,'pdf':str(REPORT)},ensure_ascii=True))
if __name__=='__main__':main()

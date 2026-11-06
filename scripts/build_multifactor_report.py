"""Build a detailed supplemental report entirely from frozen experiment outputs."""
import ast,gzip,hashlib,json,re,sys
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import build_experiment_report as layout
feature_ast=ast.parse((ROOT/'backtesting/multifactor_features.py').read_text(encoding='utf-8'))
constants={node.targets[0].id:ast.literal_eval(node.value) for node in feature_ast.body
           if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)
           and node.targets[0].id in ('TECH_NAMES','CHAN_NAMES')}
TECH_NAMES,CHAN_NAMES=constants['TECH_NAMES'],constants['CHAN_NAMES']
from reportlab.platypus import SimpleDocTemplate,PageBreak,KeepTogether
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing,Rect,String
from pypdf import PdfReader

DATA=ROOT/'docs/research/data/multifactor-chan-2026-11-07'
PDF=ROOT/'output/pdf/multifactor-chan-study-2026-11-07.pdf'
MD=ROOT/'docs/research/multifactor-chan-2026-11-07.md'
FAMILY={'INDICATORS_15':'15分钟指标对照','INDICATORS_MULTI':'多周期指标','CHAN_ONLY':'缠论结构','COMBINED':'指标与缠论结合'}
FEATURE={
 'ma5vs20ATR':'MA5与MA20差/ATR','ma10vs60ATR':'MA10与MA60差/ATR','ma20Slope5ATR':'MA20五柱斜率/ATR',
 'macdHistATR':'MACD双倍柱/ATR','macdHistChangeATR':'MACD双倍柱变化/ATR','rsi14':'RSI14简单平均',
 'stoch14':'14柱最高最低区间的收盘位置%','bollZ20':'价格距MA20/20柱总体标准差','bollWidth20Pct':'4倍20柱总体标准差/MA20%',
 'donchian20Position':'价格在此前20柱最高最低通道中的位置','priorHigh20DistanceATR':'价格距此前20柱高点/ATR',
 'priorLow20DistanceATR':'价格距此前20柱低点/ATR','volumeRatio20':'当前柱量/此前20柱均量',
 'volumeAcceleration5':'近5柱均量/前5柱均量','vwapCloseProxy20DistanceATR':'价格距20柱收盘价量加权代理/ATR',
 'obv20Normalized':'近20柱按收盘涨跌签名的成交量/总量','rangeExpansion14':'当柱高低振幅/ATR14',
 'efficiency20':'20柱收盘净位移绝对值/逐柱绝对变动总和','atrPct':'ATR14/收盘价%',
 'oiChange5Pct':'持仓量五柱变化%（缺失记0）','oiKnown':'当前及五柱前持仓量已知且前值为正',
 'penDirection':'最近确认笔方向（上1下-1未知0）','penAge':'最近确认笔距今柱数（未知120）',
 'segmentDirection':'最近确认线段方向（未知0）','fractalDirection':'最近确认分型方向（底1顶-1未知0）',
 'fractalAge':'最近确认分型距今柱数（未知120）','zoneKnown':'滚动窗口内存在已确认三笔中枢',
 'zonePositionATR':'价格距最近中枢边界/ATR（中枢内或未知0）','zoneWidthATR':'最近中枢宽度/ATR（未知0）',
 'penAreaRatio':'最近与上一同向笔MACD有向正面积比，上限8（未知0）',
 'B1':'近8柱内首次确认且尚未失效的一买候选','S1':'近8柱内首次确认且尚未失效的一卖候选',
 'B2':'近8柱内首次确认且尚未失效的二买候选','S2':'近8柱内首次确认且尚未失效的二卖候选',
 'B3':'近8柱内首次确认且尚未失效的三买候选','S3':'近8柱内首次确认且尚未失效的三卖候选',
 **layout.FEATURES,'dayMA10DistancePct':'价格距完整日线MA10%',
 'dayMA60DistancePct':'价格距完整日线MA60%','dayMA60Slope5Pct':'完整日线MA60五日斜率%',
}
def name(value):
    if '.' not in value:return FEATURE.get(value,value)
    period,key=value.split('.')
    return {'m15':'15分钟','m30':'30分钟','m60':'60分钟'}[period]+' '+FEATURE[key]
def path_text(path):
    return ' 且 '.join(name(r['feature'])+(' <= ' if r['operator']=='LE' else ' > ')+f"{r['threshold']:.6f}" for r in path) or '不加缠论过滤的宽条件对照'
def grade(value):
    return ('概率提升有周块区间支持' if value.startswith('PROBABILITY_LIFT_SUPPORTED') else
            '概率改善待验证' if value.startswith('TENTATIVE') else
            '样本不足' if value.startswith('INSUFFICIENT') else '品种或阶段依赖')+('；近期减弱' if value.endswith('WEAKENING') else '')
def load(name):return json.loads((DATA/name).read_text(encoding='utf-8'))
def main():
    result=load('results.json');audit=load('live-eligibility-audit.json');protocol=load('protocol.json');candidates=load('candidate-audit.json')
    p,h,table=layout.p,layout.h,layout.table;n,pct=layout.n,layout.pct
    now=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    layout.story.append(layout.text('多周期指标与缠论\n结果反推补充实验报告','Title'))
    p('执行日期：2026年11月7日。报告生成：'+now+'。本报告延续已交付的34品种结果反推研究，扩大周期与指标组合，并检验缠论是否提供额外信息。')
    p(f"115个候选特征、4组对照、8类未来结果标签；共同发现样本{result['labeledDecisions']:,}个截面，另核对实时活跃条件后{audit['liveEligibleDecisions']:,}个截面。所有数据来自保存的真实合约行情；本轮没有新增独立市场样本，不能冒称全新样本外确证。")
    p('实测结论：部分指标与缠论结合的条件，相对宽口径对照出现概率改善；单独去掉缠论过滤后，改善幅度并非在留出品种中都有区间支持。因此，不能推导为“缠论普遍优于普通指标”，也不能把结果标签概率直接作为盈利概率。')
    h('一 研究问题与先看结果再推导条件的方法')
    p('15分钟和MA20是用户举例，不能成为搜索边界。实验先使用已经冻结的未来结果标签，再仅用该时点之前可知的技术量价与缠论特征，训练可解释的深度三层分类树，反推哪些组合更常对应上涨、下跌、转折、入场窗口及持仓不利波动。')
    p('每组都在完全相同的决策截面上拟合，最多为每类标签选两个组合。训练条件固定后，分别检查同品种后段、留出品种和近期表现。验证结果只决定证据等级与默认预警范围，不修改树的阈值，不因为某个结果难看而删掉。')
    table(['实验组','特征数','训练选中路径','活跃条件下后段与留出均改善'],[[FAMILY[k],v['features'],v['selectedPatterns'],v['improvedPatterns']] for k,v in audit['families'].items()])
    p('“有改善的路径数”不是全组总体成绩：各路径覆盖事件、目标和样本数量不同，不能据此给四组作因果排名。每组全部选中路径与失败叶子保留在后文及机器可读审计中。')
    h('二 数据来源与原始输入核验')
    p(f"沿用34个当前活跃实际交割合约的{result['rawBars']:,}根原始15分钟记录。采集时最近20个完整日线成交量中位数至少10,000手。交易所代码复用形成的跨年旧生命周期，沿用超过365天日线断档截断规则。源文件每次读取重新计算SHA-256并与采集清单比较。")
    p('没有伪造5分钟数据。30／60分钟是上海时钟整桶汇总：必须包含每一根应有的15分钟柱，并在最后一根源柱完成后才可用。跨休市、缺柱、重复或残缺桶不拼接。它与某些交易所或终端按开市时点切分的60分钟K线可能不同；本报告不把自定义时钟桶冒充交易所原生周期。')
    p('每次只截取最近600根完整15分钟柱，各周期再使用最多120根完整柱；日线至少65根已完成柱。共享15分钟决策时间用于公平比较背景特征，本轮没有验证5分钟独立触发或每种周期的独立下单策略。')
    table(['当前实际合约','原始15分柱','清洗后柱','发现样本截面','输入SHA-256'],[[v['contract'],v['rawBars'],v['usableBars'],v['commonDecisions'],v['sha256']] for v in result['inventory']],[80,55,55,65,layout.WIDTH-255])
    h('三 时间 品种划分与样本复用边界')
    p('26个品种的2026年7月前数据用于DEV拟合；相同品种7月至9月用于TIME；8个留出品种同期用于ASSET；10月以后全部品种用于RECENT。未来16柱窗口越过分界的事件剔除。名称“留出”只针对本次树拟合；这些历史此前已用于项目研究，不能称为研究者从未见过的数据。')
    table(['分区','发现样本','符合实时活跃条件的样本'],[[part,result['partitions'][part],audit['partitions'][part]] for part in ('DEV','TIME','ASSET','RECENT')])
    p('拟合品种：'+'、'.join(protocol['trainingRoots'])+'。留出品种：'+'、'.join(protocol['heldoutRoots'])+'。')
    p('实时还要求当时此前20根完整日线成交量中位数至少10,000手。发现阶段以当前活跃合约和每柱至少100手为原始研究群体；随后对所有冻结路径统一增加这一实时口径核对，形成64,605个合格截面，并重新计算匹配对照。没有因此重拟合或重排路径。这个附加核对是事后运行口径核对，不能冒称预注册的独立实验。')
    h('四 未来结果标签与观察交易')
    p(protocol['labelDefinitions'])
    p('所有入场以信号之后下一根15分钟柱的开盘价为基准；同柱同时触及止损和目标保守先计止损。基本观察交易为1ATR止损、2ATR目标、最多16柱；隔夜越过止损按下一开盘价损失。每边1bp费用和每边1跳滑点为基础假设；压力结果同时把费用与滑点翻倍。没有还原真实委托排队、涨跌停无法成交或账户保证金过程。')
    p('上涨／下跌标签检查后8柱收盘相对入场价是否超过1ATR；局部拐点同时包含当前柱与前后4柱的相对高低和8柱后反向1ATR变化。这些未来条件只能用于离线标签，实时只报告概率候选。EXIT风险标签描述后8柱持仓不利路径；表中的收益统一为反向观察交易，不能冒称已验证实际平仓政策。')
    p(f"本次对{audit['exactLabelsRecomputed']:,}个截面逐条重新计算全部标签，对{audit['exactNextOpenReturnsRecomputed']:,}个多空方向收益逐条复算，与冻结数据在1e-8容差内一致。")
    h('五 115个特征的计算口径')
    p('每个15／30／60分钟背景包含21个量价指标及15个缠论特征，另有7个日线背景特征，共115项。ATR14使用真实波幅简单均值；RSI14用简单平均涨跌幅而非Wilder递推；MACD为12／26／9 EMA并使用双倍柱。EMA从固定最多120柱窗口首值初始化，离线和实时保持一致。')
    table(['量价指标后缀','精确定义（每个分钟周期各一份）'],[[v,FEATURE[v]] for v in TECH_NAMES],[145,layout.WIDTH-145])
    table(['缠论特征后缀','含义与未知值'],[[v,FEATURE[v]] for v in CHAN_NAMES],[145,layout.WIDTH-145])
    table(['日线特征','定义'],[[v,FEATURE[v]] for v in ('dayMA5DistancePct','dayMA20DistancePct','dayMA20Slope5Pct','dayMA5vs20Pct','dayMA10DistancePct','dayMA60DistancePct','dayMA60Slope5Pct')],[155,layout.WIDTH-155])
    p('未知值处理是模型定义的一部分：持仓缺失记0同时提供oiKnown；没有笔或分型时年龄记120；没有中枢时位置和宽度记0同时提供zoneKnown。中枢宽度小于某阈值的条件可能包含“尚无中枢”，不能一概解释成已经形成狭窄中枢。收盘价量加权代理只使用每柱收盘与成交量，不是真实逐笔VWAP。')
    h('六 缠论实现与防止事后提前知道结构')
    p('使用已有aiquant-chan-v1研究内核，不是声称涵盖缠论原文所有递归定义的唯一标准实现。包含关系合并K线先封闭后识别分型；笔等待后继反向笔成立才封闭；线段使用特征序列规则；中枢采用最初三根已确认笔的固定交集。动态尾部不进入已确认结构特征。')
    p('一买／一卖候选包含两组非重叠趋势中枢背景、同向笔新极值及MACD面积减弱；二买／二卖采用一类候选后更高低点／更低高点；三类候选采用离开固定中枢后的严格不回中枢回测。它们仍为研究候选，会被价格越过失效边界撤销；只统计当时尚未失效且首次可知后8柱内的候选。')
    p('真实结构确认存在延迟。实验特征在每一个历史决策时点重新从过去窗口生成，保存当时可知的确认年龄。图上落在较早极值位置的候选不能回填到极值当时成交。固定滚动窗口可能与全生命周期引擎结构不同，这个窗口口径同时用于实时，不隐瞒边界敏感性。')
    table(['周期','B1','S1','B2','S2','B3','S3'],[[period,*[v[x] for x in ('B1','S1','B2','S2','B3','S3')]] for period,v in result['nativeCandidateFrequency'].items()])
    p('上表是发现样本中“候选仍有效”的截面数量，持续8柱可能重复出现，不是独立买卖点次数。某些周期B1／S1／B2／S2非常稀少或为零，不能据此报告这些买卖点已经获得跨品种验证。')
    h('七 搜索过程与全部失败候选')
    p('每棵树深度最多3层，每叶至少400个训练截面；仅扫描训练样本20／40／60／80分位阈值，按二元标签Gini改善选择分割。叶子训练标签概率须比该目标全训练基准高至少3个百分点，正标签至少30个、覆盖至少12个训练品种，才能参加排序；每组每目标最多保留两个，排序只用训练提升与样本数。')
    rows=[]
    for family in FAMILY:
        for target in ('LONG_ENTRY','SHORT_ENTRY','UP_MOVE','DOWN_MOVE','LOW_TURN','HIGH_TURN','EXIT_LONG','EXIT_SHORT'):
            leaves=[r for r in candidates['leaves'] if r['family']==family and r['target']==target]
            reasons=Counter(v for r in leaves for v in r['rejected'])
            nodes=candidates['nodes'][family+':'+target]
            rows.append([FAMILY[family],target,len(leaves),sum(r['selected'] for r in leaves),sum(r['testedSplits'] for r in nodes),'; '.join(k+':'+str(v) for k,v in reasons.items()) or '无门槛剔除，仍受前二名限制'])
    table(['组别','目标','叶子','选中','分割比较','未达门槛原因计数'],rows,[66,70,34,34,54,layout.WIDTH-258])
    p('原因可重叠，不能将各原因计数相加当作总失败数。candidate-audit.json保存每个节点全部候选阈值、两侧样本、训练概率、Gini增益及最优选择，另有全部叶子路径、训练样本、正标签、品种覆盖、拒绝原因和最终选择标记。完整特征／标签截面另存压缩账本，失败结果没有删除。')
    h('八 概率对照 区间与证据等级')
    p('对照按根品种、分区、月份和上海时点小时匹配，剔除事件自己；不是随机因果实验。概率提升为条件频率减去该组匹配基准，单位为百分点。周块bootstrap共500次，同一周跨品种共同重抽，至少8周才报告区间；近期通常周数不足。重叠未来窗口仍使事件不独立。')
    p('后段至少100截面、8品种，留出至少100截面、4品种，且两边提升均为正，才算概率改善候选；两边周块提升区间下界都大于0，记为区间支持。该分级未作全部自适应搜索的多重检验校正，仍是探索性证据，tradeQualified统一为false。小样本中的100%仅表示当时样本频率，不是成功保证。')
    h('九 全部训练选中组合及验证结果')
    p('以下58条路径全部保留。统计使用统一实时活跃口径；DEV列是同一冻结路径在过滤后训练截面的描述，不是重新训练。近期负提升、样本不足、净收益为负均照实展示。阈值精度仅用于复现，不表示市场存在精确到六位的小数边界。')
    for pattern in audit['patterns']:
        block_start=len(layout.story)
        h(pattern['id']+'  '+FAMILY[pattern['family']]+'  '+pattern['label'],2)
        p(path_text(pattern['path']))
        p('证据等级：'+grade(pattern['grade'])+'。'+('该路径实际选择了缠论特征。' if pattern['containsChan'] else '虽然所在模型允许缠论，此条路径未选择缠论特征。'))
        table(['分区','截面/品种','条件概率','匹配基准','提升百分点','平均净变动%','双倍成本%'],[[part,f"{s['samples']}/{s['roots']}",pct(s['probability']),pct(s['matchedBaseProbability']),n(s['liftPp']),n(s['meanNetPct']),n(s.get('meanStressPct'))] for part,s in pattern['statistics'].items()],[42,61,70,70,76,94,layout.WIDTH-443])
        layout.story[block_start:]=[KeepTogether(layout.story[block_start:])]
    h('十 加入缠论以后是否有额外改善')
    p('对每条包含缠论的COMBINED路径，固定其普通指标条件，删除缠论条件形成宽条件对照，不重新拟合。比较P(标签|普通条件与缠论条件)减去P(标签|普通条件)，共享周重抽计算差异区间。嵌套组样本数不同，且路径来自适应搜索；这只回答本样本的条件信息增量，不能证明缠论具有因果收益。')
    for pattern in audit['patterns']:
        if not pattern.get('chanIncrement'):continue
        block_start=len(layout.story)
        h(pattern['id'],2)
        p('保留普通条件：'+path_text(pattern['withoutChanPath']))
        data=[]
        for part in ('TIME','ASSET','RECENT'):
            inc=pattern['chanIncrement'][part];s=pattern['statistics'][part];b=pattern['withoutChanStatistics'][part]
            interval=inc['intervalPp'] if inc['samples']>=100 else None
            data.append([part,f"{inc['samples']}/{inc['controlSamples']}",pct(s['probability']),pct(b['probability']),n(inc['differencePp']),(' 至 '.join(n(x) for x in interval)) if interval else '不报告（样本或周数不足）'])
        table(['分区','含缠论/宽条件n','含缠论概率','去掉缠论概率','差异百分点','周块差异区间'],data,[42,85,75,78,70,layout.WIDTH-350])
        layout.story[block_start:]=[KeepTogether(layout.story[block_start:])]
    p('以多头入场组合1为例：短周期布林宽度较窄、价格低于日线MA10一定幅度，再叠加较宽的已确认三笔中枢。后段对匹配全体基准的改善较明显；但与相同普通条件相比，留出品种的额外改善区间仍跨0。合理推论是“值得继续观察”，而不是“已经证明加缠论更好”。')
    p('向上转折的部分组合最终只选中了振幅、前低位置和随机位置，没有选择缠论。它提示极值附近的价格位置与波动变化可能是可研究的线索；这是对统计结果的解释假设，不是确认反转当时必然成立。')
    h('十一 反馈推导与未被证实的部分')
    p('反馈1：增加周期和特征并未保证更好。多周期组有更多训练选中组合，但活跃口径下双分区改善组合数并未超过15分钟指标对照。应继续比较相同目标和风险预算的前瞻表现，不能按特征数量判断有效性。')
    p('反馈2：缠论单独组有部分标签概率改善，也有品种依赖和弱样本。B1／B2等稀少候选不足以分开验证；后续需增加历史合约生命周期和新日期，而不是把多个重复截面算成大量独立买点。')
    p('反馈3：少数普通指标与中枢条件结合可能提供筛选价值，但删除缠论条件的对照显示额外增益在留出品种中并不稳定。下一轮应在冻结阈值后新增未来样本，保留全部满足条件事件，检验概率校准、成本后期望与漂移。')
    p('反馈4：概率改善不能直接决定入场。标签的2ATR／1ATR赔率结构、达到目标的路径、费用及样本重叠均影响收益；表中平均净变动和压力结果为负时必须照实保留。离场标签也只代表后续不利路径概率，尚未验证相对“继续持仓”政策的实际收益差。')
    h('十二 接入预警的具体行为')
    p('新增“多周期指标＋缠论概率预警”模板，保存时固定15分钟决策节奏，可选多周期指标、缠论结构或二者结合，以及入场／离场／转折／走势方向。实际路径可能不含缠论，页面与证据明确标注。原有基础模型和日线MA预警保留；旧盘口定时扫描及每分钟快照继续停用。')
    p('模型读取601根15分钟记录，其中最后一根形成中柱剔除后得到600根完整柱；日线也剔除形成中柱。订阅上限保持48组，没有为30／60分钟增加SDK订阅。首次建立基线、切换模型版本不补发历史；每根新确认柱只记录一次，延迟恢复超过确认附近15秒不回放。行情过时、品种不在范围、活跃度不足、窗口不足时不造信号。')
    p('触发证据冻结模型版本、实验组、具体路径、全部当时特征、各背景柱数、缠论实现与窗口、特征／确认／可得时间、分区概率、基准、样本及去掉缠论后的对照。默认只提示双分区有改善的历史观察候选；探索范围仍明确标记弱证据，无自动下单。')
    p('这次历史实验与实时计算使用共享特征函数，已完成102组逐值一致性核对；代码测试另检查完整时钟桶、历史不足、无未来标签调用、无启动补发、去重、过时与活跃度抑制。真实开市前向命中和账户成交效果尚未验证，不把部署成功当成策略成功。')
    h('十三 局限与下一步的可检验假设')
    for line in [
        '当前活跃主合约群体不是历史全市场可投资样本；品种间相关性和年度单一性限制泛化。',
        '重复使用同一历史检验窗口会积累研究者自由度。本轮保留训练内搜索审计，但没有宣称消除过拟合。',
        '全部策略观察以单个信号独立计算，允许重叠，不是合并持仓、资金使用与回撤控制后的组合业绩。',
        '中枢未知值和固定滚动窗口影响条件解释；小于宽度阈值的路径可能利用缺结构状态，应在新样本中单独检查。',
        '下一轮在冻结模型之后新增时间和更多历史交割合约；逐个目标比较模型的校准、覆盖率、概率提升、成本后期望和结构确认延迟。',
        '5分钟及交易所原生30／60分钟周期应另采真实数据验证。不得将15分钟柱切碎伪造更细周期。']:
        p(line)
    h('十四 完整复现证据与来源')
    p('原始输入保存在本机data/history/intraday-active-study，未把授权行情原文件上传到公开Git。逐输入SHA-256见第二节；decisions.json.gz保留76,316个事前特征、标签、匹配组和收益；eligibility-cost-ledger.json.gz保留逐条活跃度和压力成本结果。source-snapshot.json.gz冻结用于发现的源码。')
    p('脚本按顺序：scripts/research_multifactor_chan.py；scripts/audit_multifactor_chan.py；scripts/build_multifactor_report.py。已完成的发现目录和冻结模型拒绝覆盖。复现时应使用另一个输出目录，按原始指纹核对输入，并比较结果而非覆盖旧证据。')
    p('方法来源：TqSdk官方API说明 https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html 用于核对行情序列接口；Bailey等《The Probability of Backtest Overfitting》 https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf 用于说明多次搜索与样本外解释的局限。两项来源均不证明本次模型有效。缠论口径以仓库aiquant-chan-v1明确规则和原文课号映射为准。')
    manifest=[]
    for file in sorted(DATA.iterdir()):
        if file.is_file():manifest.append({'path':str(file.relative_to(ROOT)).replace('\\','/'),'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
    table(['证据文件','字节数','SHA-256'],[[v['path'],v['bytes'],v['sha256']] for v in manifest],[190,65,layout.WIDTH-255])
    MD.write_text('\n'.join(layout.markdown),encoding='utf-8')
    def footer(canvas,doc):
        canvas.setFont(layout.CN,8);canvas.setFillColor(colors.HexColor('#62707d'))
        canvas.drawString(42,A4[1]-32,'AI-QUANT  多周期指标与缠论补充实验  2026-11-07')
        canvas.drawString(42,25,'历史条件概率观察 / 重复历史探索 / 无确定性交易指令')
        canvas.drawRightString(A4[0]-42,25,str(doc.page))
    SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=52,bottomMargin=46,
                      title='多周期指标与缠论结果反推补充实验报告',author='AI-QUANT experiment records').build(layout.story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(PDF);extracted='\n'.join(page.extract_text() or '' for page in reader.pages)
    for required in ('76,316','64,605','COMBINED_LONG_ENTRY_1','CHAN_ONLY','INDICATORS_MULTI'):
        assert required in extracted,required
    receipt={'pdf':str(PDF.relative_to(ROOT)).replace('\\','/'),'pages':len(reader.pages),'sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),
             'generatedAt':now,'textChecks':'PASSED','visualReview':'PENDING','evidenceFiles':manifest}
    (ROOT/'output/pdf/multifactor-report-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pages':len(reader.pages),'pdfBytes':PDF.stat().st_size,'pdf':str(PDF)}))

if __name__=='__main__':main()

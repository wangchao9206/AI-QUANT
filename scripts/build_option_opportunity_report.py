"""Snapshot findings with real quotes and explicitly hypothetical payoff diagrams."""
import hashlib,json,sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import build_experiment_report as layout
from reportlab.platypus import SimpleDocTemplate,PageBreak,KeepTogether
from reportlab.graphics.shapes import Drawing,Line,String
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from pypdf import PdfReader
DATA=ROOT/'docs/research/data/options-opportunities-2026-11-07-r2'
PDF=ROOT/'output/pdf/options-opportunities-2026-11-07.pdf'
TYPES={'LONG_CALL':'买认购','LONG_PUT':'买认沽','NAKED_SHORT_CALL':'裸卖认购','NAKED_SHORT_PUT':'裸卖认沽','LONG_STRADDLE':'买跨式','SHORT_STRADDLE':'卖跨式','BEAR_PUT_DEBIT':'熊市认沽价差','BULL_CALL_DEBIT':'牛市认购价差','BEAR_CALL_CREDIT':'熊市认购信用价差','BULL_PUT_CREDIT':'牛市认沽信用价差'}
def leg(s):return '；'.join(('买 ' if r['side']=='BUY' else '卖 ')+r['symbol']+' @'+str(r['askPrice'] if r['side']=='BUY' else r['bidPrice']) for r in s['legs'])
def plot(s):
    draw=Drawing(layout.WIDTH,225);left=52;right=layout.WIDTH-10;bottom=36;top=200
    series=[('到期损益','#33475b',s['expiryScenarios'])]
    for vol,shade in [(-5,'#ce6c42'),(0,'#168e84'),(5,'#8463b8')]:
        series.append(('7天后IV'+str(vol)+'百分点',shade,[v for v in s['weekScenarios'] if abs(v['ivShiftPp']-vol)<1e-7]))
    ys=[v['pnl'] for _,_,rows in series for v in rows];lo=min(0,min(ys));hi=max(0,max(ys));pad=(hi-lo)*.08 or 1;lo-=pad;hi+=pad
    x=lambda move:left+(move+10)/20*(right-left)
    y=lambda value:bottom+(value-lo)/(hi-lo)*(top-bottom)
    for i in range(5):
        value=lo+(hi-lo)*i/4;draw.add(Line(left,y(value),right,y(value),strokeColor=colors.HexColor('#dce4ea'),strokeWidth=.4));draw.add(String(0,y(value)-2,f'{value:,.0f}',fontName=layout.CN,fontSize=7))
    draw.add(Line(left,y(0),right,y(0),strokeColor=colors.HexColor('#9ba9b5'),strokeWidth=.7))
    for idx,(label,shade,rows) in enumerate(series):
        for a,b in zip(rows,rows[1:]):draw.add(Line(x(a['underlyingMovePct']),y(a['pnl']),x(b['underlyingMovePct']),y(b['pnl']),strokeColor=colors.HexColor(shade),strokeWidth=1.3))
        draw.add(String(left+idx*111,213,label,fontName=layout.CN,fontSize=7,fillColor=colors.HexColor(shade)))
    for value in (-10,-5,0,5,10):draw.add(String(x(value)-8,20,str(value)+'%',fontName=layout.CN,fontSize=8))
    draw.add(String(left,3,'横轴：标的相对快照变动；纵轴：每组1手的情景损益（元）；不是历史业绩',fontName=layout.CN,fontSize=7))
    return draw
def main():
    r=json.loads((DATA/'results.json').read_text(encoding='utf-8'));p,h,table=layout.p,layout.h,layout.table;n,pct=layout.n,layout.pct
    layout.story.append(layout.text('国内期货期权\n投机机会快照研究','Title'))
    p('研究日期：2026年11月7日。范围按用户选择覆盖买方、卖方及组合。读取现有天勤行情线程，没有下单。18个品种、1,318个合约；180个通过核心流动性筛选，122个仅列观察，168个结构情景进入计算。')
    p('结论：有可继续观察的结构，但本轮没有证明正期望或期权历史胜率。优先核对玉米偏多买方、棉花偏空买方／认沽价差、铜的限损认购信用价差；豆粕认沽价差可作方向备选。豆油／棕榈油的IV相对过去RV低，但部分盘口和趋势延续问题仍需检查。')
    p('今天为周末，实际报价来自2026年11月6日晚至11月7日凌晨，各品种收市时间不同。所有候选都是旧报价下的数学结构，不能称为现在可成交的套利或直接开仓指令；下一交易时段须重新核对。利率2%为研究假设。')
    h('一 数据质量与筛选')
    p('454条真实链目录中，以固定18个期货根品种、14至100天到期、优先已有相同实际合约历史、单链不超过180个合约、总计不超过1,450份元数据选择。实际18链1,318合约，不覆盖白银等超大链、全部金融期权或所有到期月。不能声称全市场扫描。')
    p('核心：真实双边买卖价及挂单量为正、无交叉、与标的时点差不超过60秒、有效模型IV、成交量至少500手、持仓至少500手、价差／中间价不超过10%。观察层放宽至成交100、持仓200、价差15%，不进入核心结构。挂单量仅证明当时可见，不能保证多腿同时成交。')
    p('流动性是本轮主要限制：原油和塑料均没有通过核心过滤的合约；聚丙烯仅1个。因而某些高IV或低IV外观并非可执行优势。被拒绝的全部合约保存在liquidity-ledger.json，缺数据没有补造。')
    h('二 波动率与方向对照')
    p('IV取最接近平值的两份有效模型参考均值，可能包含未通过核心流动性的盘口，必须与合约级质量一起看。期货使用Black-76，美式期权为欧式近似，不含提前行权价值；这不是交易所发布的官方IV。')
    p('RV取同一实际期货合约最后10／20／60个日收益的样本标准差乘sqrt252。使用供应商“末根形成中”标记剔除末根日线，再保留时间不晚于报价的完成柱。原油当前链标的与已有历史合约不同，未拿另一合约冒充，RV留空。无历史IV序列，不能计算IV分位、IV Rank或偏斜历史异常程度。')
    table(['品种／实际标的','标的价','ATM IV','RV20／RV60','距日线MA20%','核心合约数'],[[s['root']+' / '+s['underlying'],n(s['spot'],2),pct(s['atmIV']),pct(s['realizedVol'].get('20'))+' / '+pct(s['realizedVol'].get('60')),n(s['trend'].get('distanceMA20Pct')),s['coreContracts']] for s in r['summaries']],[110,65,62,105,95,layout.WIDTH-437])
    p('IV低于过去RV只说明参考差异，不证明未来波动还会延续。棕榈油的IV20.6%、RV20约22.9%，但RV60约17.4%；PTA的IV33.4%高于RV20约26.9%，但与RV60约33%接近。只挑一个历史窗口会夸大“便宜／贵”的判断。')
    p('首轮采用“下一日历标签必须早于报价”的过严条件，使夜盘后的未来交易日标签导致少算一根已完成日线。该轮结果和源码保留；修正为剔除供应商标识的形成中末根，再核对完成柱时间。第二轮没有按盈利结果挑选数据。')
    h('三 重点候选与触发条件')
    selections=[('c','LONG_CALL',(2220,), '玉米：当前报价标的在MA20上方约0.7%，MA5也在MA20上方；若下一交易时段回踩后仍守住短线结构，可观察方向买方。IV约8.3%，与RV20约8.6%接近，不是明显波动率折价。失去结构或IV明显跳升时重评，不能机械追涨。'),
      ('CF','BEAR_PUT_DEBIT',(15200,15000),'棉花：IV约10.6%低于RV20约12.7%，标的在MA20下方。若反弹不能站回短线阻力、再出现下行确认，可比较认沽买方与价差。15200／15000价差成本较低但需要继续下跌，不能用最大盈利／成本倍数冒充高胜率。'),
      ('cu','BEAR_CALL_CREDIT',(106000,108000),'铜：IV约17.6%高于RV20约13.4%，标的低于MA20约3%。若反弹受阻且波动没有新的扩张，可观察带保护腿的认购信用价差。核心是判断铜到期前能否保持在卖出行权价附近下方；若快速反弹并突破，价差会亏损。此结构最大风险显著高于小额商品买方，保证金需另查。'),
      ('m','BEAR_PUT_DEBIT',(3050,3000),'豆粕：当前标的弱于MA20及MA5排列，但已明显离均线，存在反弹风险。若反弹受阻后再转弱，可比较3050／3000认沽价差；它比单买3100认沽少支付权利金，同时封顶下跌收益。不要只因为已跌很多就追空。'),
      ('MA','SHORT_STRADDLE',(3250,3250),'甲醇卖跨式作为反例研究，不列优先开仓：IV约50%，RV10约55%、RV20约44.5%，短期实际波动同样很大。“IV高”并不等于收租安全。裸卖的短Gamma、波动扩张、跳空和保证金风险需独立管理。')]
    chosen=[]
    for root,kind,strikes,reason in selections:
        s=next(v for v in r['strategies'] if v['root']==root and v['type']==kind and tuple(x['strike'] for x in v['legs'])==strikes);chosen.append(s)
        layout.story.append(PageBreak());h(root+' '+TYPES[kind]);p(reason);p(leg(s))
        maxloss=None if s['maxLossBeforeCosts'] is None else s['maxLossBeforeCosts']+s['costReserve'];maxprofit=None if s['maxProfitBeforeCosts'] is None else s['maxProfitBeforeCosts']-s['costReserve']
        table(['净支付／收取','额外成本预留','到期最大损失含预留','到期最大盈利含预留'],[[n(s['initialCashOutlay'],2),n(s['costReserve'],2),'未限定／未计算' if maxloss is None else n(maxloss,2),'未限定／未计算' if maxprofit is None else n(maxprofit,2)]])
        p('未计额外成本的到期盈亏平衡标的价：'+'、'.join(n(v,2) for v in s['breakevens'])+'。盈亏平衡及最大值都是持有至到期的数学结果，不等于盘中止损价或真实可承受损失。')
        p('最小腿成交量 '+n(s['minimumLegVolume'],0)+' 手；最小腿持仓 '+n(s['minimumLegOI'],0)+' 手；最大单腿买卖价差／中间价 '+n(s['maxRelativeSpreadPct'],2)+'%。')
        layout.story.append(plot(s))
        table(['标的不动7天后的模型损益','IV下降5点','IV不变','IV上升5点'],[['每组1手（元）',*[n(next(v['pnl'] for v in s['weekScenarios'] if v['underlyingMovePct']==0 and abs(v['ivShiftPp']-shift)<1e-6),2) for shift in (-5,0,5)]]])
        p('图中7天价值按欧式模型重新估值，已用买入ask／卖出bid建立初始成本，再预留每腿入场和离场各1跳。预留不等于实际手续费；未来价差扩大或跳空可能显著更差。模型曲线不是盈利预测。')
    h('四 买方 卖方与组合的比较')
    p('买方：损失权利金，需标的方向、速度及IV配合；方向看对但涨跌太慢、IV回落仍可能亏损。优先考虑有深度的平值／略虚值，不把几分钱的深虚值当便宜。单买和价差应按同一最大风险比较，不能仅比较权利金绝对值。')
    p('卖方：收取权利金不是无风险收入。裸卖认购上行风险无上限；裸卖认沽受标的价格下界及期货负价可能性影响，本轮未给出统一最大亏损。保证金和强平会早于到期损益的最终结算，缺少经纪商参数时不计算“保证金收益率”。')
    p('组合：垂直价差在两腿配对且保持有效的到期模型下限制损益；但两腿不同步成交、美式提前行权及期货交割、临近到期流动性和额外保证金需求均未被最大损失数字覆盖。窄价差中几跳成本占比可能很高，玉米小价差不能只看表面成本低。')
    p('跨式／宽跨式：买跨要求未来波动克服权利金和时间衰减，卖跨则承担大幅波动尾部。本轮168结构包含同执行价可用双腿的买卖跨式；未形成相同质量标准的宽跨式、铁鹰、跨月和Delta对冲历史实验，不把未执行部分写成完成。')
    h('五 全部168个结构与压力情景索引')
    p('以下金额均按每腿1手真实乘数计算。净支付负数代表收取；最大损失／盈利和BE为额外费用预留前的到期模型，0不是缺值。“—”表示未计算或未限定，不能理解为无风险。完整21个7天价格／IV冲击以及7个到期情景在results.json逐结构保存。')
    for root in [s['root'] for s in r['summaries']]:
        h(root,2);values=[s for s in r['strategies'] if s['root']==root]
        if not values:p('无结构通过核心流动性要求。');continue
        table(['结构／买卖行权价','净支付','最大损失','最大盈利','未计费BE'],[[TYPES[s['type']]+' '+('/'.join(str(x['strike']) for x in s['legs'])),n(s['initialCashOutlay'],1),n(s['maxLossBeforeCosts'],1),n(s['maxProfitBeforeCosts'],1),'/'.join(n(v,1) for v in s['breakevens'])] for s in values],[193,65,75,75,layout.WIDTH-408])
    h('六 当前没有被证明的事情')
    p('这是实际期权链快照、标的历史波动和模型情景研究，不是期权历史回测。没有伪造历史期权报价，也没有把标的趋势标签胜率转换成期权盈利胜率；未估计期权策略长期正期望。期货回测与期权损益之间还隔着IV、Theta、价差、到期与执行机制。')
    p('没有确认本轮存在可以锁定的无风险套利。当前是周末旧报价，不把合约间的局部差异当作可同时成交的套利。下一交易时段应按同一过滤重新采集，连续记录实际bid/ask、IV和标的，再研究事件后1／3／5日退出。不能靠反复修改阈值追求全正结果。')
    h('七 来源与核验')
    p('行情来源为现有天勤SDK真实期权链，只读HTTP接口；18份原始链保存在本机data/history/options-study-2026-11-07，采集清单保存每份原始SHA-256。公开仓库仅保留研究汇总、流动性账本、策略情景及脚本，不上传全部授权原始链。')
    p('已对100个垂直价差的400个关键边界到期损益核对，均符合模型最大损失／盈利界限。所有金额与乘数从真实元数据读取；研究假设和无历史数据的部分明确列出。')
    p('一手一个合约乘数，不代表建议的实际仓位。实际可投入资金、单笔可承受损失、交易权限和保证金能力尚未确认，因此没有给出资金分配或开仓数量。')
    p('策略定义参考CME交易所牛市价差说明：https://www.cmegroup.com/cn-s/education/courses/option-strategies/bull-spread.html 。行权、履约、保证金机制参考上海期货交易所期权交易管理办法：https://www.shfe.cn/regulation/exchangerules/otherrules/202606/t20260622_832190.html 。两项来源说明机制，不证明本轮候选能赚钱。')
    table(['实际标的／报价时点','原始链SHA-256'],[[s['underlying']+' '+s['quoteAt'],s['chainSha256']] for s in r['summaries']],[240,layout.WIDTH-240])
    md=ROOT/'docs/research/options-opportunities-2026-11-07.md';md.write_text('\n'.join(layout.markdown),encoding='utf-8')
    def footer(c,doc):
        c.setFont(layout.CN,8);c.setFillColor(colors.HexColor('#62707d'));c.drawString(42,A4[1]-32,'AI-QUANT  国内期货期权快照研究  2026-11-07');c.drawString(42,25,'真实旧报价 / 模型压力情景 / 非期权历史胜率');c.drawRightString(A4[0]-42,25,str(doc.page))
    SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=52,bottomMargin=46,title='国内期货期权投机机会快照研究').build(layout.story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(PDF);text='\n'.join(page.extract_text() or '' for page in reader.pages)
    for token in ('1,318','168','106000','3050','15200'):assert token in text,token
    manifest={'pdf':PDF.relative_to(ROOT).as_posix(),'pages':len(reader.pages),'sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'textChecks':'PASSED','visualReview':'PENDING'}
    (ROOT/'output/pdf/options-opportunities-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest))
if __name__=='__main__':main()

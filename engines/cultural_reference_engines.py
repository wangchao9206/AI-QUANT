# -*- coding: utf-8 -*-
"""
Traditional Chinese cultural reference engines with transparent time-calendar scoring.

Design principles:
  - Weight is small (3% each), supplementary only
  - Scoring is fully transparent, based on classical hexagram / nine-star mappings
  - category="CULTURAL_REFERENCE", included_in_score=True
  - Weights from settings (liuyao / iching / qimen)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from lunar_python import Solar

from config.settings import settings
from .base import BaseEngine, PredictionResult


SHANGHAI_TZ = timezone(timedelta(hours=8))
TRIGRAMS = ("\u4e7e", "\u5151", "\u79bb", "\u9707", "\u5dfd", "\u574e", "\u826e", "\u5764")

# 64 hexagram name matrix [upper][lower]
HEXAGRAMS = (
    ("\u4e7e\u4e3a\u5929", "\u5929\u6cfd\u5c65", "\u5929\u706b\u540c\u4eba", "\u5929\u96f7\u65e0\u59c4", "\u5929\u98ce\u59e4", "\u5929\u6c34\u8b1f", "\u5929\u5c71\u9041", "\u5929\u5730\u5426"),
    ("\u6cfd\u5929\u5938", "\u5151\u4e3a\u6cfd", "\u6cfd\u706b\u9769", "\u6cfd\u96f7\u968f", "\u6cfd\u98ce\u5927\u8fc7", "\u6cfd\u6c34\u56f0", "\u6cfd\u5c71\u548f", "\u6cfd\u5730\u8983"),
    ("\u706b\u5929\u5927\u6709", "\u706b\u6cfd\u7766", "\u79bb\u4e3a\u706b", "\u706b\u96f7\u566c\u5696", "\u706b\u98ce\u9f0e", "\u706b\u6c34\u672a\u6d4e", "\u706b\u5c71\u65c5", "\u706b\u5730\u664b"),
    ("\u96f7\u5929\u5927\u58ee", "\u96f7\u6cfd\u5f52\u59b9", "\u96f7\u706b\u4e30", "\u9707\u4e3a\u96f7", "\u96f7\u98ce\u6052", "\u96f7\u6c34\u89e3", "\u96f7\u5c71\u5c0f\u8fc7", "\u96f7\u5730\u8c6b"),
    ("\u98ce\u5929\u5c0f\u755c", "\u98ce\u6cfd\u4e2d\u5b5a", "\u98ce\u706b\u5bb6\u4eba", "\u98ce\u96f7\u76ca", "\u5dfd\u4e3a\u98ce", "\u98ce\u6c34\u6d23", "\u98ce\u5c71\u6e10", "\u98ce\u5730\u89c2"),
    ("\u6c34\u5929\u9700", "\u6c34\u6cfd\u8282", "\u6c34\u706b\u65e2\u6d4e", "\u6c34\u96f7\u5c6f", "\u6c34\u98ce\u4e95", "\u574e\u4e3a\u6c34", "\u6c34\u5c71\u8e47", "\u6c34\u5730\u6bd4"),
    ("\u5c71\u5929\u5927\u755c", "\u5c71\u6cfd\u635f", "\u5c71\u706b\u8d32", "\u5c71\u96f7\u9828", "\u5c71\u98ce\u8778", "\u5c71\u6c34\u8499", "\u826e\u4e3a\u5c71", "\u5c71\u5730\u5634"),
    ("\u5730\u5929\u6cf0", "\u5730\u6cfd\u4e34", "\u5730\u706b\u660e\u5937", "\u5730\u96f7\u590d", "\u5730\u98ce\u5347", "\u5730\u6c34\u5e08", "\u5730\u5c71\u8c26", "\u5764\u4e3a\u5730"),
)

HEXAGRAM_SCORES: dict[str, int] = {
    "\u4e7e\u4e3a\u5929": 70, "\u5929\u6cfd\u5c65": 35, "\u5929\u706b\u540c\u4eba": 50, "\u5929\u96f7\u65e0\u59c4": 0,
    "\u5929\u98ce\u59e4": -30, "\u5929\u6c34\u8b1f": -50, "\u5929\u5c71\u9041": -15, "\u5929\u5730\u5426": -70,
    "\u6cfd\u5929\u5938": 25, "\u5151\u4e3a\u6cfd": 40, "\u6cfd\u706b\u9769": 20, "\u6cfd\u96f7\u968f": 40,
    "\u6cfd\u98ce\u5927\u8fc7": -40, "\u6cfd\u6c34\u56f0": -55, "\u6cfd\u5c71\u548f": 50, "\u6cfd\u5730\u8983": 35,
    "\u706b\u5929\u5927\u6709": 70, "\u706b\u6cfd\u7766": -15, "\u79bb\u4e3a\u706b": 35, "\u706b\u96f7\u566c\u5696": 10,
    "\u706b\u98ce\u9f0e": 50, "\u706b\u6c34\u672a\u6d4e": -25, "\u706b\u5c71\u65c5": -30, "\u706b\u5730\u664b": 50,
    "\u96f7\u5929\u5927\u58ee": 20, "\u96f7\u6cfd\u5f52\u59b9": -40, "\u96f7\u706b\u4e30": 55, "\u9707\u4e3a\u96f7": -10,
    "\u96f7\u98ce\u6052": 40, "\u96f7\u6c34\u89e3": 40, "\u96f7\u5c71\u5c0f\u8fc7": -15, "\u96f7\u5730\u8c6b": 40,
    "\u98ce\u5929\u5c0f\u755c": 10, "\u98ce\u6cfd\u4e2d\u5b5a": 55, "\u98ce\u706b\u5bb6\u4eba": 40, "\u98ce\u96f7\u76ca": 60,
    "\u5dfd\u4e3a\u98ce": 10, "\u98ce\u6c34\u6d23": 10, "\u98ce\u5c71\u6e10": 40, "\u98ce\u5730\u89c2": 10,
    "\u6c34\u5929\u9700": 30, "\u6c34\u6cfd\u8282": 10, "\u6c34\u706b\u65e2\u6d4e": 55, "\u6c34\u96f7\u5c6f": -20,
    "\u6c34\u98ce\u4e95": 10, "\u574e\u4e3a\u6c34": -35, "\u6c34\u5c71\u8e47": -45, "\u6c34\u5730\u6bd4": 40,
    "\u5c71\u5929\u5927\u755c": 50, "\u5c71\u6cfd\u635f": -15, "\u5c71\u706b\u8d32": 20, "\u5c71\u96f7\u9828": 10,
    "\u5c71\u98ce\u8778": -35, "\u5c71\u6c34\u8499": 10, "\u826e\u4e3a\u5c71": 0, "\u5c71\u5730\u5634": -70,
    "\u5730\u5929\u6cf0": 75, "\u5730\u6cfd\u4e34": 50, "\u5730\u706b\u660e\u5937": -45, "\u5730\u96f7\u590d": 65,
    "\u5730\u98ce\u5347": 60, "\u5730\u6c34\u5e08": 10, "\u5730\u5c71\u8c26": 55, "\u5764\u4e3a\u5730": 40,
}

MOVING_LINE_MODIFIERS: dict[int, int] = {1: -8, 2: 12, 3: -12, 4: 8, 5: 20, 6: -18}

NINE_STAR_SCORES: dict[int, int] = {1: -40, 2: -55, 3: 55, 4: 60, 5: 0, 6: 50, 7: -30, 8: 45, 9: 15}
NINE_STAR_DESC: dict[int, str] = {
    1: "\u5929\u84ec\uff08\u4e3b\u9669\u963b\uff0c\u5b9c\u5b88\u4e0d\u5b9c\u8fdb\uff09",
    2: "\u5929\u8292\uff08\u4e3b\u75c5\u8017\uff0c\u4e0d\u5229\u6269\u5f20\uff09",
    3: "\u5929\u51b2\uff08\u4e3b\u8fdb\u53d6\uff0c\u5229\u4e8e\u7a81\u7834\uff09",
    4: "\u5929\u8f85\uff08\u4e3b\u6587\u660c\uff0c\u8c0b\u4e8b\u6613\u6210\uff09",
    5: "\u5929\u79bd\uff08\u4e3b\u4e2d\u548c\uff0c\u9700\u7efc\u5408\u7814\u5224\uff09",
    6: "\u5929\u5fc3\uff08\u4e3b\u51b3\u65ad\uff0c\u5229\u4e8e\u884c\u52a8\uff09",
    7: "\u5929\u67f1\uff08\u4e3b\u963b\u9694\uff0c\u5b9c\u6b62\u4e0d\u5b9c\u884c\uff09",
    8: "\u5929\u4efb\uff08\u4e3b\u7a33\u5065\uff0c\u5229\u4e8e\u5b88\u6210\uff09",
    9: "\u5929\u82f1\uff08\u4e3b\u663e\u8000\uff0c\u5c0f\u5229\u6709\u4e3a\uff09",
}
_CN_NUM: dict[str, int] = {
    "\u4e00": 1, "\u4e8c": 2, "\u4e09": 3, "\u56db": 4, "\u4e94": 5,
    "\u516d": 6, "\u4e03": 7, "\u516b": 8, "\u4e5d": 9,
}


def _calendar(context: Dict[str, Any]):
    observed_at = context.get("analysis_time") or datetime.now(SHANGHAI_TZ)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=SHANGHAI_TZ)
    local = observed_at.astimezone(SHANGHAI_TZ)
    lunar = Solar.fromYmdHms(
        local.year, local.month, local.day,
        local.hour, local.minute, local.second,
    ).getLunar()
    pillars = (
        lunar.getYearInGanZhiExact(),
        lunar.getMonthInGanZhiExact(),
        lunar.getDayInGanZhiExact(),
        lunar.getTimeInGanZhi(),
    )
    return local, lunar, pillars


def _time_hexagram(local: datetime) -> tuple[str, str, int]:
    day_total = local.year + local.month + local.day
    branch_number = ((local.hour + 1) // 2) % 12 + 1
    upper = (day_total - 1) % 8
    lower = (day_total + branch_number - 1) % 8
    moving = (day_total + branch_number - 1) % 6 + 1
    return HEXAGRAMS[upper][lower], f"{TRIGRAMS[upper]}\u4e0a{TRIGRAMS[lower]}\u4e0b", moving


def _make_cultural_result(
    dimension_name: str,
    dimension_key: str,
    score: float,
    confidence: float,
    summary: str,
    recommendation: str,
    observed_at: datetime,
    weight: float,
    key_metrics: dict | None = None,
    details: dict | None = None,
) -> PredictionResult:
    clamped = max(-100.0, min(100.0, score))
    direction = "BULLISH" if clamped >= 20.0 else "BEARISH" if clamped <= -20.0 else "NEUTRAL"
    return PredictionResult(
        dimension_name=dimension_name,
        dimension_key=dimension_key,
        score=clamped,
        confidence=max(0.0, min(1.0, confidence)),
        direction=direction,
        summary=summary,
        recommendation=f"非实证文化参考：{recommendation}",
        category="CULTURAL_REFERENCE",
        data_status="REFERENCE",
        included_in_score=True,
        weight=max(0.0, weight),
        source_name="\u771f\u5b9e\u65f6\u95f4\u4e0e\u4e2d\u56fd\u4f20\u7edf\u5386\u6cd5\u8ba1\u7b97\uff08lunar-python\uff09",
        source_url="https://github.com/6tail/lunar-python",
        observed_at=observed_at,
        sample_size=1,
        key_metrics=key_metrics or {},
        details=details or {},
        timestamp=datetime.now(timezone.utc),
    )


class LiuYaoCulturalReferenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("\u516d\u7b7c\u65f6\u5386\u53c2\u8003", "liuyao")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        local, lunar, pillars = _calendar(context)
        hexagram, trigrams, moving = _time_hexagram(local)
        base_score = HEXAGRAM_SCORES.get(hexagram, 0)
        modifier = MOVING_LINE_MODIFIERS.get(moving, 0)
        score = float(base_score + modifier)
        confidence = 0.45
        auspice = "\u5927\u5409" if score >= 55 else "\u5409" if score >= 20 else "\u5927\u51f6" if score <= -55 else "\u51f6" if score <= -20 else "\u5e73"
        summary = (
            f"【中华时历与数理起卦】依据农历历法（lunar-python）精确时空推算：北京时间 {local:%Y-%m-%d %H:%M}（四柱干支：{' '.join(pillars)}，日旬空：{lunar.getDayXunKongExact()}），依北宋邵康节《梅花易数》时空先天数理体系排盘，得本卦《{hexagram}》（{trigrams}），动爻为第 {moving} 爻（爻变修正 {modifier:+d} 分）。\n"
            f"【古籍易理与市况象意】《周易》卦象数理中，《{hexagram}》蕴含博弈双方气运消长律动。在中华全息周期哲学中，六十四卦反映天地物候演化节律，动爻（第 {moving} 爻）为时机动静关键窗口；当爻象偏于“{auspice}”时，象意对应市场交投心理处于顺畅和谐与进取状态，反之若值凶爻则昭示波折阻滞与蓄势防守。\n"
            f"【文化量化参考结论】卦象与动爻综合推衍评分为 {score:+.0f} 分（基础 {base_score:+d} → 爻变终值 {score:+.0f} 分，吉凶定性为“{auspice}”），赋予极低辅助参考权重（{settings.weights.liuyao * 100:.0f}%），纳入全息决策矩阵。"
        )
        recommendation = (
            f"【易道义理指引】时历卦象定性偏于“{auspice}”，可作为传统东方智慧在市场心理与择时氛围层面的哲学启迪；\n"
            "【科学决策底线】文化时历不具有现代物理学与经济学因果验证，严禁脱离量价趋势与现货供需单凭卦象做交易决策，所有开平仓指令必须严格以实证量化模型及硬止损规则为准。"
        )
        return _make_cultural_result(
            self.name, self.key, score, confidence,
            summary, recommendation, local,
            weight=settings.weights.liuyao,
            key_metrics={
                "时间卦": hexagram,
                "上下卦": trigrams,
                "动爻": f"第 {moving} 爻",
                "卦象吉凶": auspice,
                "基础评分": base_score,
                "动爻修正": f"{modifier:+d}",
                "综合评分": round(score, 1),
                "四柱": " ".join(pillars),
                "日旬空": lunar.getDayXunKongExact(),
            },
        )


class IChingCulturalReferenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("易经时序参考", "iching")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        local, lunar, pillars = _calendar(context)
        ordinal_index = (local.toordinal() - 1) % 64
        upper, lower = divmod(ordinal_index, 8)
        hexagram = HEXAGRAMS[upper][lower]
        score = float(HEXAGRAM_SCORES.get(hexagram, 0))
        confidence = 0.40
        previous_term = lunar.getPrevJieQi().getName()
        next_term = lunar.getNextJieQi().getName()
        auspice = "大吉" if score >= 55 else "吉" if score >= 20 else "大凶" if score <= -55 else "凶" if score <= -20 else "平"
        summary = (
            f"【中华时历与公历日序映射】公历 365 日序与周易六十四卦方圆全息图周期映射体系：今日公历序数映射卦象为《{hexagram}》（基础评分 {score:+.0f} 分，吉凶定性为“{auspice}”）；太阳黄经运行轨迹显示当前节气处在“{previous_term}”与“{next_term}”的物候更替交界期（农历：{lunar.toString()}）。\n"
            f"【节令物候与产业周期】传统二十四节气是古代先民总结太阳公转引起的物候、温差与降水变迁的最高智慧结晶。在大宗商品尤其是农产品期货中，二十四节气直接锚定产区春耕、夏管、秋收、冬储的物理时间表，精准映射了现货仓储温湿度管理、新粮上市集中期以及下游节令性消费潮汐的客观规律。\n"
            f"【文化量化参考结论】易经日序与节气转换综合评分 {score:+.0f} 分（权重 {settings.weights.iching * 100:.0f}%），为中长期季节性供需周期与产区物候提供传统文化视角的时空印证。"
        )
        recommendation = (
            f"【节令顺应要领】当前正处在“{previous_term}”至“{next_term}”转换期，重点顺应季节性物候对现货基本面的节奏影响；\n"
            "【科学决策底线】本维度为辅助文化研究参考（权重仅 3%），不可替代基本面供需报告与盘面主力订单流指标，务必坚持严密风控纪律。"
        )
        return _make_cultural_result(
            self.name, self.key, score, confidence,
            summary, recommendation, local,
            weight=settings.weights.iching,
            key_metrics={
                "日序卦": hexagram,
                "卦象吉凶": auspice,
                "卦象评分": round(score, 1),
                "前一节气": previous_term,
                "后一节气": next_term,
                "农历日期": lunar.toString(),
                "四柱": " ".join(pillars),
            },
        )


class QiMenCulturalReferenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("奇门时九星参考", "qimen")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        local, lunar, pillars = _calendar(context)
        star = lunar.getTimeNineStar()
        star_str = star.toString()
        star_number = _CN_NUM.get(star_str[0], 5)
        score = float(NINE_STAR_SCORES.get(star_number, 0))
        confidence = 0.42
        star_desc = NINE_STAR_DESC.get(star_number, star_str)
        auspice = "吉" if score >= 20 else "凶" if score <= -20 else "平"
        summary = (
            f"【中华时历与奇门遁甲盘面】基于真太阳时与阴阳遁历法精算：分析时点 {local:%Y-%m-%d %H:%M}（四柱：{' '.join(pillars)}），时家奇门盘面天盘时九星为“{star_str}”（奇门星名“{star.getNameInQiMen()}”，八门配属“{star.getBaMenInQiMen()}”，八卦方位“{star.getPosition()}·{star.getPositionDesc()}”，阴阳属性“{star.getYinYangInQiMen()}”）。\n"
            f"【兵法博弈与星象义理】古代奇门遁甲源于行军布阵的兵法数理模型，旨在通过时空方位推演天时、地利、人和与神助。九星吉凶寓意：“{star_desc}”。在博弈层面，奇门强调“动静有常，乘势而动”，时星吉凶反映了多空力量在时间节点上的气势顺逆与博弈心理倾向。\n"
            f"【文化量化参考结论】奇门九星时空格局评分 {score:+.0f} 分（时空定性“{auspice}”，权重 {settings.weights.qimen * 100:.0f}%），纳入东方时历参谋池。"
        )
        recommendation = (
            f"【兵家决策启示】奇门时星显示当前时空格局为“{auspice}”，宜遵循古代谋定而后动、见吉而发、见险而止的博弈智慧；\n"
            "【科学决策底线】传统兵家数理星象绝不可作为期货入场实操的独立依据，所有头寸必须严格建立在 ATR 波动止损与实证量价支撑之上。"
        )
        return _make_cultural_result(
            self.name, self.key, score, confidence,
            summary, recommendation, local,
            weight=settings.weights.qimen,
            key_metrics={
                "\u65f6\u4e5d\u661f": star_str,
                "\u5947\u95e8\u661f\u540d": star.getNameInQiMen(),
                "\u661f\u8c61\u5409\u51f6": auspice,
                "\u661f\u8c61\u8bc4\u5206": round(score, 1),
                "\u516b\u95e8": star.getBaMenInQiMen(),
                "\u65b9\u4f4d": f"{star.getPosition()}\uff08{star.getPositionDesc()}\uff09",
                "\u9634\u9633": star.getYinYangInQiMen(),
                "\u56db\u67f1": " ".join(pillars),
            },
        )

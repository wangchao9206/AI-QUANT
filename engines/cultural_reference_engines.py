"""Dynamic traditional-calendar references, strictly isolated from trading scores."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from lunar_python import Solar

from .base import BaseEngine, PredictionResult

SHANGHAI_TZ = timezone(timedelta(hours=8))
TRIGRAMS = ("乾", "兑", "离", "震", "巽", "坎", "艮", "坤")
HEXAGRAMS = (
    ("乾为天", "天泽履", "天火同人", "天雷无妄", "天风姤", "天水讼", "天山遁", "天地否"),
    ("泽天夬", "兑为泽", "泽火革", "泽雷随", "泽风大过", "泽水困", "泽山咸", "泽地萃"),
    ("火天大有", "火泽睽", "离为火", "火雷噬嗑", "火风鼎", "火水未济", "火山旅", "火地晋"),
    ("雷天大壮", "雷泽归妹", "雷火丰", "震为雷", "雷风恒", "雷水解", "雷山小过", "雷地豫"),
    ("风天小畜", "风泽中孚", "风火家人", "风雷益", "巽为风", "风水涣", "风山渐", "风地观"),
    ("水天需", "水泽节", "水火既济", "水雷屯", "水风井", "坎为水", "水山蹇", "水地比"),
    ("山天大畜", "山泽损", "山火贲", "山雷颐", "山风蛊", "山水蒙", "艮为山", "山地剥"),
    ("地天泰", "地泽临", "地火明夷", "地雷复", "地风升", "地水师", "地山谦", "坤为地"),
)


def _calendar(context: Dict[str, Any]):
    observed_at = context.get("analysis_time") or datetime.now(SHANGHAI_TZ)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=SHANGHAI_TZ)
    local = observed_at.astimezone(SHANGHAI_TZ)
    lunar = Solar.fromYmdHms(local.year, local.month, local.day, local.hour, local.minute, local.second).getLunar()
    pillars = (lunar.getYearInGanZhiExact(), lunar.getMonthInGanZhiExact(), lunar.getDayInGanZhiExact(), lunar.getTimeInGanZhi())
    return local, lunar, pillars


def _time_hexagram(local: datetime) -> tuple[str, str, int]:
    day_total = local.year + local.month + local.day
    branch_number = ((local.hour + 1) // 2) % 12 + 1
    upper = (day_total - 1) % 8
    lower = (day_total + branch_number - 1) % 8
    moving = (day_total + branch_number - 1) % 6 + 1
    return HEXAGRAMS[upper][lower], f"{TRIGRAMS[upper]}上{TRIGRAMS[lower]}下", moving


class LiuYaoCulturalReferenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("六爻时历参考", "liuyao")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        local, lunar, pillars = _calendar(context)
        hexagram, trigrams, moving = _time_hexagram(local)
        return PredictionResult.reference(
            self.name, self.key,
            f"按 {local:%Y-%m-%d %H:%M:%S}（Asia/Shanghai）时间数起卦，得《{hexagram}》，第 {moving} 爻为动爻。",
            "非实证文化参考：仅展示传统时历映射，不构成行情判断或交易依据。", local,
            {"时间卦": hexagram, "上下卦": trigrams, "动爻": f"第{moving}爻", "四柱": " ".join(pillars), "日旬空": lunar.getDayXunKongExact()},
        )


class IChingCulturalReferenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("易经时序参考", "iching")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        local, lunar, pillars = _calendar(context)
        upper, lower = divmod((local.toordinal() - 1) % 64, 8)
        hexagram = HEXAGRAMS[upper][lower]
        previous_term, next_term = lunar.getPrevJieQi().getName(), lunar.getNextJieQi().getName()
        return PredictionResult.reference(
            self.name, self.key,
            f"按公历日序循环映射六十四卦，当前为《{hexagram}》；节气位于“{previous_term}”与“{next_term}”之间。",
            "非实证文化参考：卦序和节气仅供文化阅读，不参与评分、信号、目标价或止损计算。", local,
            {"日序卦": hexagram, "前一节气": previous_term, "后一节气": next_term, "农历日期": lunar.toString(), "四柱": " ".join(pillars)},
        )


class QiMenCulturalReferenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("奇门时九星参考", "qimen")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        local, lunar, pillars = _calendar(context)
        star = lunar.getTimeNineStar()
        return PredictionResult.reference(
            self.name, self.key,
            f"真实时刻 {local:%Y-%m-%d %H:%M:%S} 的时九星为“{star.toString()}”，对应奇门星名“{star.getNameInQiMen()}”。",
            "非实证文化参考：这是历法库的时九星信息展示，不生成盘面多空结论。", local,
            {"时九星": star.toString(), "奇门星名": star.getNameInQiMen(), "八门": star.getBaMenInQiMen(), "方位": f"{star.getPosition()}（{star.getPositionDesc()}）", "阴阳": star.getYinYangInQiMen(), "四柱": " ".join(pillars)},
        )

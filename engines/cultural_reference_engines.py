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
        recommendation=recommendation,
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
            f"\u6309 {local:%Y-%m-%d %H:%M}\uff08Asia/Shanghai\uff09\u65f6\u95f4\u8d77\u5366\uff0c"
            f"\u5f97\u300a{hexagram}\u300b\uff0c\u7b2c {moving} \u7b7c\u4e3a\u52a8\u7b7c\uff08{MOVING_LINE_MODIFIERS[moving]:+d}\u4fee\u6b63\uff09\uff0c"
            f"\u7efc\u5408\u5366\u8c61\u5224\u5b9a\u4e3a\u201c{auspice}\u201d\uff08\u57fa\u7840 {base_score:+d} \u2192 \u7ec8\u503c {score:+.0f}\uff09\u3002"
        )
        recommendation = (
            f"\u65f6\u5386\u5366\u8c61\u504f{auspice}\uff0c\u53ef\u4f5c\u5e02\u573a\u6c1b\u56f4\u8f85\u52a9\u53c2\u8003\uff1b"
            "\u6587\u5316\u53c2\u8003\u4e0d\u66ff\u4ee3\u91cf\u4ef7\u548c\u6280\u672f\u4fe1\u53f7\uff0c\u6743\u91cd\u4ec5 3%\uff0c\u8bf7\u7ed3\u5408\u5b9e\u8bc1\u7ef4\u5ea6\u7efc\u5408\u7814\u5224\u3002"
        )
        return _make_cultural_result(
            self.name, self.key, score, confidence,
            summary, recommendation, local,
            weight=settings.weights.liuyao,
            key_metrics={
                "\u65f6\u95f4\u5366": hexagram,
                "\u4e0a\u4e0b\u5366": trigrams,
                "\u52a8\u7b7c": f"\u7b2c {moving} \u7b7c",
                "\u5366\u8c61\u5409\u51f6": auspice,
                "\u57fa\u7840\u8bc4\u5206": base_score,
                "\u52a8\u7b7c\u4fee\u6b63": f"{modifier:+d}",
                "\u7efc\u5408\u8bc4\u5206": round(score, 1),
                "\u56db\u67f1": " ".join(pillars),
                "\u65e5\u65ec\u7a7a": lunar.getDayXunKongExact(),
            },
        )


class IChingCulturalReferenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("\u6613\u7ecf\u65f6\u5e8f\u53c2\u8003", "iching")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        local, lunar, pillars = _calendar(context)
        ordinal_index = (local.toordinal() - 1) % 64
        upper, lower = divmod(ordinal_index, 8)
        hexagram = HEXAGRAMS[upper][lower]
        score = float(HEXAGRAM_SCORES.get(hexagram, 0))
        confidence = 0.40
        previous_term = lunar.getPrevJieQi().getName()
        next_term = lunar.getNextJieQi().getName()
        auspice = "\u5927\u5409" if score >= 55 else "\u5409" if score >= 20 else "\u5927\u51f6" if score <= -55 else "\u51f6" if score <= -20 else "\u5e73"
        summary = (
            f"\u516c\u5386\u65e5\u5e8f\u5faa\u73af\u6620\u5c04\u516d\u5341\u56db\u5366\uff0c\u4eca\u65e5\u4e3a\u300a{hexagram}\u300b\uff08{auspice}\uff0c{score:+.0f} \u5206\uff09\uff1b"
            f"\u8282\u6c14\u4f4d\u4e8e\u201c{previous_term}\u201d\u4e0e\u201c{next_term}\u201d\u4e4b\u95f4\uff0c\u5173\u6ce8\u519c\u4e1a\u4f9b\u9700\u5468\u671f\u3002"
        )
        recommendation = (
            "\u6613\u7ecf\u65e5\u5e8f\u4e3a\u6587\u5316\u53c2\u8003\uff083%\uff09\uff0c\u8282\u6c14\u4fe1\u606f\u53ef\u8f85\u52a9\u7814\u5224\u7ea2\u67a3\u4ea7\u533a\u7269\u5019\uff1b"
            "\u5366\u8c61\u5409\u51f6\u4e0d\u5355\u72ec\u4f5c\u4e3a\u64cd\u4f5c\u4f9d\u636e\uff0c\u8bf7\u7ed3\u5408\u6c14\u8c61\u548c\u91cf\u4ef7\u7ef4\u5ea6\u3002"
        )
        return _make_cultural_result(
            self.name, self.key, score, confidence,
            summary, recommendation, local,
            weight=settings.weights.iching,
            key_metrics={
                "\u65e5\u5e8f\u5366": hexagram,
                "\u5366\u8c61\u5409\u51f6": auspice,
                "\u5366\u8c61\u8bc4\u5206": round(score, 1),
                "\u524d\u4e00\u8282\u6c14": previous_term,
                "\u540e\u4e00\u8282\u6c14": next_term,
                "\u519c\u5386\u65e5\u671f": lunar.toString(),
                "\u56db\u67f1": " ".join(pillars),
            },
        )


class QiMenCulturalReferenceEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("\u5947\u95e8\u65f6\u4e5d\u661f\u53c2\u8003", "qimen")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        local, lunar, pillars = _calendar(context)
        star = lunar.getTimeNineStar()
        star_str = star.toString()
        star_number = _CN_NUM.get(star_str[0], 5)
        score = float(NINE_STAR_SCORES.get(star_number, 0))
        confidence = 0.42
        star_desc = NINE_STAR_DESC.get(star_number, star_str)
        auspice = "\u5409" if score >= 20 else "\u51f6" if score <= -20 else "\u5e73"
        summary = (
            f"\u771f\u5b9e\u65f6\u523b {local:%Y-%m-%d %H:%M}\uff0c\u65f6\u4e5d\u661f\u4e3a\u201c{star_str}\u201d\uff0c"
            f"\u5947\u95e8\u661f\u540d\u201c{star.getNameInQiMen()}\u201d\uff08{star_desc}\uff09\uff0c"
            f"\u4f20\u7edf\u5224\u5b9a\u4e3a\u201c{auspice}\u201d\uff08{score:+.0f} \u5206\uff09\u3002"
        )
        recommendation = (
            f"\u4e5d\u661f{auspice}\u8c61\uff0c\u53ef\u4f5c\u5f53\u524d\u5e02\u573a\u8fd0\u52bf\u8f85\u52a9\u53c2\u8003\uff083%\uff09\uff1b"
            "\u5947\u95e8\u661f\u8c61\u4e0d\u66ff\u4ee3\u91cf\u4ef7\u5224\u65ad\uff0c\u8bf7\u7ed3\u5408\u6267\u884c\u98ce\u9669\u548c\u6d41\u52a8\u6027\u7ef4\u5ea6\u7efc\u5408\u51b3\u7b56\u3002"
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

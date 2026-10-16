"""Nine empirical dimensions derived exclusively from observed evidence.

Bug fixes applied:
  B2 – contract sorting now uses chronological (year, month) order, not lexicographic
  B4 – positioning window aligned: price change uses same valid kline set as OI
  B5 – sentiment confidence set to low (0.25) when no keyword matches found
  B7 – DeliveryPolicy raises ValueError on zero/missing limit_pct (→ UNAVAILABLE);
       unit mismatch fixed: change_pct (decimal) converted to % before dividing limit_pct (%)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Dict

from config.settings import settings

from .base import BaseEngine, PredictionResult


# ──────────────────────────────────────────────
# Shared utilities
# ──────────────────────────────────────────────

def _clamp(value: float) -> float:
    return max(-100.0, min(100.0, value))


def _pct(current: float, previous: float) -> float:
    return (current / previous - 1.0) * 100.0 if previous else 0.0


def _atr(klines: list[Any], window: int = 14) -> float:
    """Average True Range over the last *window* bars."""
    ranges = []
    for index in range(max(1, len(klines) - window), len(klines)):
        bar = klines[index]
        previous = klines[index - 1].close
        ranges.append(max(bar.high - bar.low, abs(bar.high - previous), abs(bar.low - previous)))
    return mean(ranges) if ranges else 0.0


def _contract_month_key(code: str) -> tuple[int, int]:
    """Return (year, month) for chronological sorting of futures contract codes.

    Handles both 3-digit (CJ701 → 2027-01) and 4-digit (CJ2701 → 2027-01) forms.
    """
    m = re.fullmatch(r"[A-Z]{1,4}(\d{3,4})", code)
    if not m:
        return (9999, 99)
    digits = m.group(1)
    if len(digits) == 4:
        return (2000 + int(digits[:2]), int(digits[2:]))
    # 3-digit: decade inference from current year
    current_year = datetime.now(timezone.utc).year
    decade = (current_year // 10) * 10
    year = decade + int(digits[0])
    if year < current_year - 1:
        year += 10
    return (year, int(digits[1:]))


def _observed_contracts(curve: dict[str, Any]) -> list[tuple[str, Any]]:
    """Keep dated contracts only; continuous/main aliases are not deliverable months."""
    return [
        (code, item)
        for code, item in curve.items()
        if re.fullmatch(r"[A-Z]{1,4}\d{3,4}", code) and item.price > 0
    ]


# ──────────────────────────────────────────────
# Empirical engines
# ──────────────────────────────────────────────

class WeatherPhenologyEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(
            "产区气象与物候",
            "weather",
            "Open-Meteo 多模型气象数据",
            "https://open-meteo.com/en/docs",
        )

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        evidence = context.get("weather")
        if evidence is None or not evidence.records:
            raise ValueError("No observed production-region weather data")
        records = evidence.records
        temperature_range = mean(row["temperature_max"] - row["temperature_min"] for row in records)
        precipitation = mean(row["precipitation"] for row in records)
        humidity = mean(row["humidity"] for row in records)
        # 天气损伤风险：降水与高湿抬升供应风险，大温差有利于晾晒和糖分积累
        # 系数基于新疆红枣农艺经验（降水>5mm/日起显著影响晾晒，湿度>45%加重霉变风险）
        damage_risk = min(100.0,
            precipitation * 5.0
            + max(0.0, humidity - 45.0) * 1.4
            + max(0.0, 10.0 - temperature_range) * 3.0
        )
        score = _clamp((damage_risk - 35.0) * 1.8)
        status_desc = "干爽适宜，产地收获与晾晒顺利，供应端兑现顺畅" if damage_risk < 35 else "阴雨潮湿或反常偏冷，加剧霉烂/减产与质量劣变风险，供应端受到实质性扰动" if damage_risk > 50 else "气象指标基本处于农艺常态区间，对产量扰动中性"
        impact_desc = "利空现货挺价，利于仓单平稳生成" if score < -10 else "利多供应收紧，强力支撑产区看涨惜售情绪" if score > 10 else "气象多空影响总体均衡"
        summary = (
            f"【数据实证与观测基准】采集 {len(records)} 个核心产区网格气象站真实观测与多模型预报：平均昼夜温差为 {temperature_range:.1f}℃（优质农艺生理适宜温差为 10-15℃）、平均降水量 {precipitation:.1f}mm（露天晾晒与成熟期警戒线为 5.0mm/日）、平均空气相对湿度 {humidity:.0f}%（霉变与裂果临界警戒线为 45%），综合测算产区天气损伤风险指数为 {damage_risk:.1f}/100。\n"
            f"【传导机制与多空机理】当前产区微观气象呈现“{status_desc}”。在大宗农产品生长期与采摘成熟期，昼夜温差驱动果肉干物质累积与含糖量转化；若遭遇连续降水或极端高湿，不仅严重拖延采摘晾晒进度，更将导致裂果、霉变及品级下调，致使符合期货交割标准的基准品仓单短缺；反之，晴好少雨则保障高产高质，使得供给充裕度快速传导至现货交割环节。\n"
            f"【量化研判结论】综合判定当前气象条件为“{impact_desc}”，模型打分 {score:+.1f} 分（权重 {settings.weights.weather * 100:.0f}%）。"
        )
        recommendation = (
            "【实操交易要领】气象变动往往率先反映在远月合约的情绪溢价中，建议紧密跟踪主产区实际地头收购报价与客商订货意愿是否与天气预期产生共振，逢低寻找右侧验证机会。\n"
            "【风控防守底线】若未来 3 日连续气象预报显示降水归零且温差扩大至 12℃ 以上，说明天气炒作窗口关闭，应果断止盈天气多头头寸，防范供应兑现引发价格回踩。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            min(0.9, 0.55 + len(records) / 50.0),
            summary,
            recommendation,
            weight=settings.weights.weather,
            source_name=evidence.source_name,
            source_url=evidence.source_url,
            observed_at=evidence.observed_at,
            sample_size=evidence.sample_size,
            key_metrics={
                "平均昼夜温差": f"{temperature_range:.1f}℃",
                "平均降水": f"{precipitation:.1f}mm",
                "平均湿度": f"{humidity:.0f}%",
                "天气损伤风险": f"{damage_risk:.1f}/100",
                "产区状态评估": status_desc,
            },
        )



class NewsSentimentEngine(BaseEngine):
    POSITIVE = ("上涨", "走强", "减产", "短缺", "惜售", "霜冻", "利多", "反弹")
    NEGATIVE = ("下跌", "跌超", "走弱", "增产", "供应充足", "库存", "疲弱", "利空")

    def __init__(self) -> None:
        super().__init__(
            "新闻舆情",
            "sentiment",
            "东方财富期货资讯",
            "https://futures.eastmoney.com/",
        )

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        evidence = context.get("news")
        if evidence is None or not evidence.records:
            raise ValueError("No observed product-specific news")
        texts = [f"{item['title']} {item['summary']}" for item in evidence.records]
        positive = sum(text.count(word) for text in texts for word in self.POSITIVE)
        negative = sum(text.count(word) for text in texts for word in self.NEGATIVE)
        matched = positive + negative
        score = _clamp((positive - negative) / max(1, matched) * 100.0)
        # B5 fix: 无关键词命中时给出低置信度，避免虚假高置信中性信号
        if matched == 0:
            confidence = 0.25
        else:
            confidence = min(0.82, 0.42 + min(len(texts), 20) * 0.02)
        titles = "；".join(item["title"] for item in evidence.records[:3])
        tone = "舆情显著偏多，看涨情绪与利多催化占据主导" if score > 20 else "舆情显著偏空，负面资讯与下行压力集聚" if score < -20 else "多空资讯交织并存，市场情绪处于中性博弈期"
        summary = (
            f"【数据实证与观测基准】基于东方财富期货权威专栏对本品种行业要闻与深度快讯进行自然语言量化语义提取：有效样本集共收录 {len(texts)} 篇专业研报与行业资讯，累计命中利多特征词 {positive} 次、利空特征词 {negative} 次，有效多空词频比为 {positive}:{max(1, negative)}，文本语义极性净得分为 {score:+.1f} 分。\n"
            f"【传导机制与多空机理】当前市场情绪状态评定为“{tone}”。资讯高频词主要聚焦于行业上下游采销博弈、主产地库存去化、宏观进出口贸易预期及突发事件。当利多词频压倒性胜出时，产业投机情绪与跟风资金做多意愿强化，盘面往往呈现溢价脉冲；反之，当负面言论密集爆发时，市场避险与止损盘涌出，加剧探底惯性。核心代表资讯标题：{titles}。\n"
            f"【量化研判结论】模型给出置信度 {confidence * 100:.0f}% 的舆情趋势判定，得分 {score:+.1f} 分（权重 {settings.weights.sentiment * 100:.0f}%）。"
        )
        recommendation = (
            "【实操交易要领】新闻舆情反映市场短线情绪共振，但在极端高涨或极度恐慌时常出现“利好出尽成利空”或“逆向衰竭”现象，切勿单凭新闻报道追涨杀跌，必须等待盘面分时量价有效确认。\n"
            "【风控防守底线】若盘面价格连续 2 日与主流舆情发生显著背离（如利空不跌反涨），表明隐性主力资金正在逆向吸筹，应立即修正基于舆情的交易方向。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            confidence,
            summary,
            recommendation,
            weight=settings.weights.sentiment,
            source_name=evidence.source_name,
            source_url=evidence.source_url,
            observed_at=evidence.observed_at,
            sample_size=evidence.sample_size,
            key_metrics={"利多词频": positive, "利空词频": negative, "相关文章数": len(texts), "舆情倾向": tone},
            details={"文章": evidence.records[:10]},
        )



class SupplyDemandPressureEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("供需压力", "supply_demand", "新浪期货日K量仓数据", "https://finance.sina.com.cn/futures/")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        klines = context.get("klines", [])
        if len(klines) < 11:
            raise ValueError("Supply-demand model requires 11 observed bars")
        price_change = _pct(klines[-1].close, klines[-6].close)
        oi_change = _pct(klines[-1].open_interest, klines[-6].open_interest)
        recent_volume = mean(bar.volume for bar in klines[-5:])
        prior_volume = mean(bar.volume for bar in klines[-10:-5])
        volume_change = _pct(recent_volume, prior_volume)
        directional_oi = (1 if price_change >= 0 else -1) * abs(oi_change)
        score = _clamp(price_change * 4.0 + directional_oi * 2.0 + (1 if price_change >= 0 else -1) * min(20.0, abs(volume_change) * 0.3))

        if price_change >= 0 and oi_change >= 0:
            pattern_desc = "呈现量增仓增、价涨量升的典型主动增仓多头行情，增量资金跑步进场，买方意志占据绝对压倒优势"
            bias_desc = "强力多头主升"
            trade_guide = "建议依托分时均线择机顺势建立多单，享受增量资金推升的溢价红利。"
        elif price_change >= 0 and oi_change < 0:
            pattern_desc = "呈现价涨仓减的空头减仓被动离场反弹，虽价格抬升但伴随持仓量缩减，表明上涨源于空头止损踩踏而非主动多头建仓"
            bias_desc = "空头被动回补"
            trade_guide = "减仓反弹持续度存疑，切勿重仓追高，逢高反抽无力可分批获利了结。"
        elif price_change < 0 and oi_change >= 0:
            pattern_desc = "呈现价跌仓增的主动空头大举打压格局，现货套保与投机空单密集加仓，多头接盘资金承压严重"
            bias_desc = "主动增仓下挫"
            trade_guide = "空头势头凶猛，多头头寸应坚决止损或反手顺势跟空，切忌盲目抄底抢反弹。"
        else:
            pattern_desc = "呈现价跌仓减的多头多杀多踩踏出局，前期获利或被套多单主动斩仓，下行动能处于存量消耗阶段"
            bias_desc = "多头恐慌斩仓"
            trade_guide = "多杀多阶段流动性折价放大，待持仓量企稳止跌且出现缩量红K线时再行评估左侧价值。"

        summary = (
            f"【数据实证与观测基准】截取近 11 根真实日 K 线量仓动力学指标：5 日价格变动幅度 {price_change:+.2f}%，同期主力持仓变动 {oi_change:+.2f}%，近 5 日日均成交量较前 5 日环比变动 {volume_change:+.2f}%。\n"
            f"【传导机制与多空机理】根据期货市场经典量仓博弈动力学研判：当前盘面{pattern_desc}。持仓量是测度场外增量资本进出的唯一纯粹指标，当价格波动与持仓扩张形成同向共振时，代表主流产业与金融资本具有坚定的方向预期；而成交量的变动幅度（{volume_change:+.2f}%）则直接验证了该预期在微观市场中的换手热度。\n"
            f"【量化研判结论】综合测算量价与持仓供需博弈动能得分为 {score:+.1f} 分（权重 {settings.weights.supply_demand * 100:.0f}%），多空动能定性为“{bias_desc}”。"
        )
        recommendation = (
            f"【实操交易要领】{trade_guide}\n"
            f"【风控防守底线】若后续连续 2 个交易日出现“价格创新高/新低但持仓量大幅跳水”的背离信号，表明主力资金正在借势换手诱导散户接盘，应立刻收紧跟踪止盈保护本金。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.78,
            summary,
            recommendation,
            weight=settings.weights.supply_demand,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=klines[-1].timestamp,
            sample_size=len(klines),
            key_metrics={"5日价格变化": f"{price_change:+.2f}%", "5日持仓变化": f"{oi_change:+.2f}%", "成交量变化": f"{volume_change:+.2f}%", "量仓博弈定性": bias_desc},
        )


class DeliveryPolicyEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("交割与交易规则", "policy", "东方财富期货交易提示（交易所规则汇总）", "https://portal.eastmoneyfutures.com/pages/service/jyts.html")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        evidence = context.get("trading_rules")
        quote = context.get("quote")
        if evidence is None or not evidence.records or quote is None:
            raise ValueError("No current observed product trading rules")
        rule = evidence.records[0]
        limit_pct = rule["price_limit_pct"]
        margin_pct = rule["margin_pct"]
        # B7 fix: limit_pct=0 表示解析失败，应触发 UNAVAILABLE 而非静默返回中性
        if not limit_pct:
            raise ValueError("CJ price limit percentage could not be parsed or is zero")
        # B7 fix: 单位统一 —— quote.change_pct 为小数（-0.0272=-2.72%），limit_pct 为百分比（4.0=4%）
        # 实际使用比例 = (今日涨跌幅 / 涨跌停幅度)，两者换算到同一单位后计算
        limit_usage = (quote.change_pct * 100.0) / limit_pct * 100.0
        score = _clamp(limit_usage)

        if abs(limit_usage) >= 70.0:
            usage_desc = "价格极度逼近涨跌停板边界，单边流动性面临枯竭，交易所随时可能启动扩板或临时提高保证金程序"
            risk_level = "极高规则约束预警"
        elif abs(limit_usage) >= 40.0:
            usage_desc = "价格波幅占据涨跌停空间近半，日内多空交锋剧烈，保证金杜绝违约防线受到实质性考验"
            risk_level = "中度规则缓冲约束"
        else:
            usage_desc = "价格波幅处于交易所设定的常态平稳波动区间内，涨跌停与交割保证金安全垫十分充裕"
            risk_level = "安全规则运行区间"

        summary = (
            f"【数据实证与观测基准】依据交易所最新发布的主力合约（{rule['contract']}）风控与交割规则参数：每日价格最大波动限制为 ±{limit_pct:.1f}%，交易保证金要求为 {margin_pct:.1f}%；日内价格实际变动已消耗涨跌停限制空间的 {abs(limit_usage):.1f}%（方向偏向：{limit_usage:+.1f}%）。\n"
            f"【传导机制与多空机理】涨跌停限制与保证金制度是期货交易所维护履约信用、平抑异常投机的终极安全阀。{usage_desc}。当涨跌停利用率超过 70% 时，盘面往往触发市场微观结构异变：挂单队列严重单向堆积导致对手盘撮合困难，若连续封板还将迫使交易所实施强制减仓与协议平仓；而在常态区间内，合理的涨跌停缓冲空间则为跨期套利与期现套保提供了顺畅的流动性承接。\n"
            f"【量化研判结论】规则约束压力评分 {score:+.1f} 分（权重 {settings.weights.policy * 100:.0f}%），运行状态定级为“{risk_level}”。"
        )
        recommendation = (
            f"【实操交易要领】当前规则约束处于{risk_level}。若涨跌停使用率突破 60%，切忌顺势盲目追板，谨防封死或炸板带来的极端滑点损失；建议在板前分批减仓止盈。\n"
            f"【风控防守底线】严格按照合约最低保证金 {margin_pct:.1f}% 的 2.5 倍以上维持账户整体可用资金，防范单边极端行情下交易所临时调高保证金导致的被动追保或强平风险。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.72,
            summary,
            recommendation,
            weight=settings.weights.policy,
            source_name=evidence.source_name,
            source_url=evidence.source_url,
            observed_at=evidence.observed_at,
            sample_size=evidence.sample_size,
            key_metrics={
                "当前合约": rule["contract"],
                "涨跌停": f"±{limit_pct:.1f}%",
                "保证金": f"{margin_pct:.1f}%",
                "限制空间使用": f"{limit_usage:+.1f}%",
                "规则状态评估": risk_level,
            },
        )


class PositionCrowdingEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("持仓拥挤度", "positioning", "新浪期货日K持仓量", "https://finance.sina.com.cn/futures/")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        klines = context.get("klines", [])
        if len(klines) < 20:
            raise ValueError("Positioning model requires 20 observed bars")
        # B4 fix: 使用同一份过滤后的有效持仓 K 线，确保价格变化与持仓统计时间窗口一致
        valid_klines = [bar for bar in klines if bar.open_interest > 0]
        if len(valid_klines) < 10:
            raise ValueError("Observed open-interest history is incomplete")
        interests = [bar.open_interest for bar in valid_klines]
        current = interests[-1]
        oi_mean = mean(interests[-20:])
        oi_sigma = pstdev(interests[-20:]) or 1.0
        oi_z = (current - oi_mean) / oi_sigma
        # 价格变化使用同一组有效K线（与持仓对齐）
        price_change = _pct(valid_klines[-1].close, valid_klines[-6].close) if len(valid_klines) >= 6 else 0.0
        score = _clamp((1 if price_change >= 0 else -1) * min(100.0, abs(oi_z) * 35.0 + abs(price_change) * 4.0))

        if abs(oi_z) >= 1.8:
            crowd_desc = "持仓规模严重偏离历史均值，处于统计学极度拥挤状态，多空博弈筹码高度饱和，已进入反转或逼仓临界点"
            structure_desc = "极端高度拥挤"
        elif abs(oi_z) >= 0.8:
            crowd_desc = "持仓量稳步扩张且显著高于均线水平，主流机构资金深度介入，趋势正在良性展开"
            structure_desc = "健康趋势增仓"
        else:
            crowd_desc = "持仓处于历史常态均值区间，多空未现极端对峙，资金筹码分布相对松散中性"
            structure_desc = "常态持仓平衡"

        summary = (
            f"【数据实证与观测基准】采集近 20 个有效交易日持仓分布构建标准正态基准：当前最新持仓 {current:,} 手，近 20 日持仓基准均值为 {round(oi_mean):,} 手（标准差 {oi_sigma:.0f} 手），计算持仓偏离 Z 分数为 {oi_z:+.2f}σ，同期 5 日价格涨跌幅为 {price_change:+.2f}%。\n"
            f"【传导机制与多空机理】持仓拥挤度直接刻画了场内博弈筹码的积聚烈度。{crowd_desc}。在期货市场运行中，当持仓 Z-Score 偏离过大时，意味着市场充斥同向共识交易者，浮盈或浮亏盘均极其庞大，稍有风吹草动极易诱发‘踩踏式止损出局’；而持仓与价格同向放大时，则代表资金合力强劲，具有较强的趋势惯性延续性。\n"
            f"【量化研判结论】持仓拥挤与多空聚集度评分 {score:+.1f} 分（权重 {settings.weights.positioning * 100:.0f}%），结构判定为“{structure_desc}”。"
        )
        recommendation = (
            f"【实操交易要领】当前持仓状态判定为“{structure_desc}”。若持仓 Z 分数超过 +1.5σ 且价格处于高位，严禁盲目追多，应警惕主力获利盘借机涌出；可在持仓拐头缩量时轻仓顺势做波段防守。\n"
            f"【风控防守底线】若持仓 Z 分数突破 ±2.0σ 极端拥挤阈值，必须将单品种持仓头寸压缩至 20% 以下，杜绝在极端挤仓行情中暴露过度风险敞口。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.76,
            summary,
            recommendation,
            weight=settings.weights.positioning,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=valid_klines[-1].timestamp,
            sample_size=len(valid_klines[-20:]),
            key_metrics={
                "当前持仓": current,
                "20日平均持仓": round(oi_mean),
                "持仓Z分数": f"{oi_z:+.2f}σ",
                "5日价格变化（有效K线）": f"{price_change:+.2f}%",
                "拥挤度评定": structure_desc,
            },
        )


class ExecutionRiskEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("执行与风险", "execution", "真实K线波动与区间", "https://finance.sina.com.cn/futures/")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        klines = context.get("klines", [])
        quote = context.get("quote")
        if quote is None or len(klines) < 20:
            raise ValueError("Execution model requires 20 observed bars")
        atr = _atr(klines)
        support = min(bar.low for bar in klines[-20:])
        resistance = max(bar.high for bar in klines[-20:])
        range_width = max(1.0, resistance - support)
        location = (quote.price - support) / range_width
        score = _clamp((location - 0.5) * 120.0)

        if location >= 0.8:
            location_desc = "现价高度逼近近 20 日阻力上限（顶部 20% 区域），上方遭遇密集历史套牢盘反压，买入盈亏比显著恶化"
            eval_desc = "高位阻力承压 · 风险收益比欠佳"
        elif location <= 0.2:
            location_desc = "现价触及近 20 日绝对支撑底线（底部 20% 区域），空头继续打压动能衰减，下行有硬底托撑，反弹性价比极高"
            eval_desc = "低位强支撑托底 · 盈亏性价比优异"
        else:
            location_desc = "现价运行在 20 日盘整箱体中枢平衡带附近，多空势均力敌，处于技术突破前的蓄势震荡状态"
            eval_desc = "中枢中性平衡 · 等待突破方向"

        summary = (
            f"【数据实证与观测基准】基于近 20 根日 K 线精确测算波动与边界：14 日真实波幅 ATR(14) 为 {atr:.1f} 元/吨，近 20 日绝对支撑位为 {support:.1f}、绝对阻力位为 {resistance:.1f}，箱体区间跨度为 {range_width:.1f} 点；最新价位处在 20 日运行区间的 {location * 100:.1f}% 分位位置。\n"
            f"【传导机制与多空机理】执行风险模型量化了当前入场点位的不对称盈亏比与假突破摩擦成本。{location_desc}。在期货量化实战中，拒绝在阻力位下方盲目追多、拒绝在支撑位上方恐慌杀跌是资金曲线平稳增长的核心原则；利用客观 ATR 尺度设定止损，能有效过滤市场随机微观噪点并保护交易本金。\n"
            f"【量化研判结论】区间执行点位综合评分 {score:+.1f} 分（权重 {settings.weights.execution * 100:.0f}%），执行性价比评定为“{eval_desc}”。"
        )
        recommendation = (
            f"【实操交易要领】严格遵循“以 ATR 测算防守边际，以区间分位决定仓位系数”的纪律：单笔头寸硬止损建议设定为最新价 ±{atr * 1.5:.1f} 点（约 1.5 倍 ATR），避免采用主观侥幸心理扛单。\n"
            f"【风控防守底线】若日线收盘价有效击穿 20 日支撑位 {support:.1f} 或向上突破阻力位 {resistance:.1f}，原盘整区间逻辑被物理推翻，必须无条件执行止损或追随破位止盈。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.86,
            summary,
            recommendation,
            weight=settings.weights.execution,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=quote.timestamp,
            sample_size=len(klines),
            key_metrics={
                "ATR(14)": f"{atr:.1f}",
                "20日支撑": f"{support:.1f}",
                "20日阻力": f"{resistance:.1f}",
                "区间位置": f"{location * 100:.1f}%",
                "执行性价比": eval_desc,
            },
        )


class CrossContractSpreadEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("主力跨期价差", "spread", "新浪期货合约行情", "https://finance.sina.com.cn/futures/")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        quote = context.get("quote")
        curve = context.get("term_structure") or {}
        # B2 fix: 按合约到期月份（year, month）排序，替代字典序，避免跨年时近月/远月颠倒
        contracts = sorted(
            _observed_contracts(curve),
            key=lambda x: _contract_month_key(x[0]),
        )
        if quote is None or not contracts:
            raise ValueError("No observed cross-contract prices")
        near_code, near = contracts[0]
        spread = quote.price - near.price
        spread_pct = spread / near.price * 100.0
        score = _clamp(spread_pct * 20.0)
        observed_at = max([quote.timestamp, *(item.timestamp for _, item in contracts)])

        if spread_pct > 1.5:
            spread_mode = "主力相对近月显著升水（正向套利空间）"
            spread_analysis = "主力合约相对紧邻近月呈现大幅溢价，反映出市场对远期供应收紧或通胀复苏预期打得过满，存在一定远期估值过热风险"
        elif spread_pct < -1.5:
            spread_mode = "主力相对近月深度贴水（反向紧俏结构）"
            spread_analysis = "主力合约相对紧邻近月大幅折价，反映出现货端和近月交割端极其紧俏，而远端预期悲观，基差具有强烈的向上修复动能"
        else:
            spread_mode = "主力与近月价差平稳（常态平水收敛）"
            spread_analysis = "主力与近月价差基本持平在合理资金持有成本区间内，期差对单边行情扰动中性"

        summary = (
            f"【数据实证与观测基准】跨合约到期时间序列深度比对：主力活跃合约最新价 {quote.price:.1f} 元/吨，紧邻交割到期日的近月基准合约（{near_code}）现价 {near.price:.1f} 元/吨；二者绝对跨期价差为 {spread:+.1f} 元/吨，相对价差率为 {spread_pct:+.2f}%。\n"
            f"【传导机制与多空机理】主力与近月合约的跨期价差是期货市场衡量“即期交割现实”与“远期投机预期”差异的最敏锐风向标。{spread_analysis}。近月合约直接面对现货交割和仓单注销检验，价格紧咬现货实际货值；主力合约则是流动性最庞大的投机阵地，两者之间的价差裂口往往蕴含着期现回归与跨期套利的确定性机会。\n"
            f"【量化研判结论】跨期溢价动能评分 {score:+.1f} 分（权重 {settings.weights.spread * 100:.0f}%），期差形态判定为“{spread_mode}”。"
        )
        recommendation = (
            f"【实操交易要领】当前期差形态为“{spread_mode}”。在换月窗口期，紧密盯防主力资金移仓换月的节奏差异，若价差率超出常态边界，可考虑跨期套利组合锁定基差回归收益。\n"
            f"【风控防守底线】主力连续合约属于虚拟加权行情不可直接交割，若临近近月交割月发生逼仓异动，必须及时平仓主力单边头寸，避免卷入换月流动性踩踏。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.78,
            summary,
            recommendation,
            weight=settings.weights.spread,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=observed_at,
            sample_size=len(contracts) + 1,
            key_metrics={
                "主力价格": f"{quote.price:.1f}",
                "最近合约": near_code,
                "最近合约价格": f"{near.price:.1f}",
                "主力-近月": f"{spread:+.1f}",
                "价差率": f"{spread_pct:+.2f}%",
                "期差形态": spread_mode,
            },
        )


class TermStructureEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("期限结构", "term_structure", "新浪期货合约行情", "https://finance.sina.com.cn/futures/")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        curve = context.get("term_structure") or {}
        # B2 fix: 同 CrossContractSpreadEngine，按到期月份排序确保斜率符号正确
        contracts = sorted(
            _observed_contracts(curve),
            key=lambda x: _contract_month_key(x[0]),
        )
        if len(contracts) < 3:
            raise ValueError("Term structure requires at least three observed contracts")
        prices = [item.price for _, item in contracts]
        x_mean = (len(prices) - 1) / 2.0
        y_mean = mean(prices)
        slope = sum((index - x_mean) * (price - y_mean) for index, price in enumerate(prices)) / sum((index - x_mean) ** 2 for index in range(len(prices)))
        total_spread_pct = _pct(prices[-1], prices[0])
        score = _clamp(-total_spread_pct * 18.0)
        structure = "升水结构（Contango / 远月较高）" if slope > 0 else "贴水结构（Backwardation / 近月较高）" if slope < 0 else "平坦结构（Flat）"

        if slope < 0:
            mechanism_desc = "在近高远低的 Backwardation（贴水）构型下，现货与即期需求极度旺盛，便利收益（Convenience Yield）显著覆盖仓储成本，长线持有多头享有丰厚的正向展期收益（Roll Yield），是典型高确定性牛市的基石"
            grade_desc = "强现实供需偏紧 · 利多近端"
        elif slope > 0:
            mechanism_desc = "在近低远高的 Contango（升水）构型下，市场显性库存充足，持有成本（资金利息+仓储费）在远月合约中不断累加，多头每个移仓换月周期都将承受沉重的负展期磨损，往往昭示中长期弱势过剩"
            grade_desc = "弱现实高库存累库 · 压制远期"
        else:
            mechanism_desc = "期限曲线形态平坦，月间价差接近持仓成本平衡点，表明当前供需关系相对平稳，缺乏单边突变张力"
            grade_desc = "供求中性平衡"

        summary = (
            f"【数据实证与观测基准】贯穿 {len(contracts)} 个交割月份合约的完整远期价格曲线测算：曲线每档综合拟合斜率为 {slope:+.1f} 元/月档，首月至远月总跨期价差率为 {total_spread_pct:+.2f}%，当前曲线形态构型为“{structure}”。\n"
            f"【传导机制与多空机理】远期期限结构是产业商品研究皇冠上的明珠。{mechanism_desc}。商品期货不仅是金融衍生品，更是物理现货的跨期分配工具，期限曲线的倾角与形态是洞悉全行业产业链去库或累库周期的最硬核证据。\n"
            f"【量化研判结论】期限结构对远期基本面综合评分 {score:+.1f} 分（权重 {settings.weights.term_structure * 100:.0f}%），产业底色定性为“{grade_desc}”。"
        )
        recommendation = (
            f"【实操交易要领】当前期限结构定性为“{grade_desc}”。在贴水结构下建议坚持近月逢低做多策略并享受多头正展期红利；在大幅升水结构下多头切勿死扛，逢高沽空远月或布局跨期反套更为稳健。\n"
            f"【风控防守底线】密切监控远月升水是否突破无风险套利上边界（期现套利成本线）；一旦升水过大引发交割库仓单暴增，盘面多头将面临严重的交割抛压冲击。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.84,
            summary,
            recommendation,
            weight=settings.weights.term_structure,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=max(item.timestamp for _, item in contracts),
            sample_size=len(contracts),
            key_metrics={"结构构型": structure, "曲线斜率": f"{slope:+.1f}元/档", "首尾价差率": f"{total_spread_pct:+.2f}%", "观测合约数": len(contracts), "产业基本面定性": grade_desc},
        )


class LiquidityVolatilityEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("流动性与波动状态", "liquidity", "新浪期货实时行情与日K", "https://finance.sina.com.cn/futures/")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        quote = context.get("quote")
        klines = context.get("klines", [])
        if quote is None or len(klines) < 20:
            raise ValueError("Liquidity model requires quote and 20 observed bars")
        returns = [_pct(klines[index].close, klines[index - 1].close) for index in range(1, len(klines))]
        volatility = pstdev(returns[-20:])
        amplitude = (quote.high - quote.low) / quote.prev_settlement * 100.0 if quote.prev_settlement else 0.0
        volume_median_proxy = mean(bar.volume for bar in klines[-20:])
        volume_ratio = quote.volume / volume_median_proxy if volume_median_proxy else 0.0
        risk_adjusted_move = quote.change_pct / max(0.25, volatility)
        score = _clamp(risk_adjusted_move * 30.0)

        if volume_ratio >= 1.5 and volatility >= 1.8:
            activity_desc = "高流动性放量且高波动共振 · 活跃主升/主跌窗口"
            liquidity_desc = "盘面成交量呈倍数级放大，买卖盘口深度充沛，资金活跃度极高，滑点摩擦成本大幅下降，技术形态的突破往往具备极强的动量持续性"
        elif volume_ratio < 0.6:
            activity_desc = "低流动性缩量整理 · 谨防流动性陷阱与假突破"
            liquidity_desc = "成交量能大幅萎缩，买卖盘口深度偏薄，少量大单易引发盘面虚假毛刺与异动，盲目按常态滑点执行易招致额外冲击成本"
        else:
            activity_desc = "常态流动性与稳态波动 · 运行平稳"
            liquidity_desc = "换手率与波动率处于统计基准中枢区间，市场微观结构健康有序，适合按标准策略参数执行"

        summary = (
            f"【数据实证与观测基准】市场微观流动性与波动率实证测算：近 20 个交易日收益率波动率基准值为 {volatility:.2f}%，日内极值振幅达到 {amplitude:.2f}%；最新日内成交量为 20 日均量的 {volume_ratio:.2f} 倍，成交额达 {quote.turnover:,.0f} 元，经波动率标准化后的风险调整净位移为 {risk_adjusted_move:+.2f}。\n"
            f"【传导机制与多空机理】流动性与波动率直接决定了策略执行的容量边界与滑点损耗。{liquidity_desc}。在期货量化执行中，波动率是价格风险的度量衡，顺应高流动性环境建仓能确保策略以最低成本进出，避免陷入‘薄盘挤仓’的被动局面。\n"
            f"【量化研判结论】流动性充裕度与风险调整动能综合评分 {score:+.1f} 分（权重 {settings.weights.liquidity * 100:.0f}%），微观状态评定为“{activity_desc}”。"
        )
        recommendation = (
            f"【实操交易要领】当前微观状态为“{activity_desc}”。在高波动期间建仓建议分批挂限价单执行，并按波动率反比法则适当缩小单笔开仓规模；缩量时避免追逐突破。\n"
            f"【风控防守底线】若日内振幅超过常态均值的 2.5 倍或成交量出现断崖式下跌，表明市场流动性可能突发枯竭，应立即下调整体策略杠杆至 15% 以下保全本金。"
        )
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.8,
            summary,
            recommendation,
            weight=settings.weights.liquidity,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=quote.timestamp,
            sample_size=len(klines),
            key_metrics={"20日波动率": f"{volatility:.2f}%", "日内振幅": f"{amplitude:.2f}%", "成交量比": f"{volume_ratio:.2f}x", "成交额": f"{quote.turnover:.0f}", "微观状态": activity_desc},
        )

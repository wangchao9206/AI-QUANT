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
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            min(0.9, 0.55 + len(records) / 50.0),
            f"{len(records)} 个真实产区预报点显示平均温差 {temperature_range:.1f}℃、降水 {precipitation:.1f}mm、湿度 {humidity:.0f}%。",
            "降水与高湿抬升减产风险时偏多，干燥和大温差有利于供应兑现时偏空。",
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
            },
        )


class NewsSentimentEngine(BaseEngine):
    POSITIVE = ("上涨", "走强", "减产", "短缺", "惜售", "霜冻", "利多", "反弹")
    NEGATIVE = ("下跌", "跌超", "走弱", "增产", "供应充足", "库存", "疲弱", "利空")

    def __init__(self) -> None:
        super().__init__(
            "新闻舆情",
            "sentiment",
            "东方财富红枣资讯",
            "https://futures.eastmoney.com/a/acj.html",
        )

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        evidence = context.get("news")
        if evidence is None or not evidence.records:
            raise ValueError("No observed red-date news")
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
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            confidence,
            f"分析 {len(texts)} 条真实红枣资讯，利多词 {positive} 次、利空词 {negative} 次。最新标题：{titles}",
            "新闻样本较少或无关键词命中时降低置信度，不用舆情替代价格确认。",
            weight=settings.weights.sentiment,
            source_name=evidence.source_name,
            source_url=evidence.source_url,
            observed_at=evidence.observed_at,
            sample_size=evidence.sample_size,
            key_metrics={"利多词频": positive, "利空词频": negative, "相关文章数": len(texts)},
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
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.78,
            f"5日价格变化 {price_change:.2f}%，持仓变化 {oi_change:.2f}%，近5日均量较前5日变化 {volume_change:.2f}%。",
            "价格与持仓同向增加代表新增资金确认；缩量行情按较低置信度处理。",
            weight=settings.weights.supply_demand,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=klines[-1].timestamp,
            sample_size=len(klines),
            key_metrics={"5日价格变化": f"{price_change:.2f}%", "5日持仓变化": f"{oi_change:.2f}%", "成交量变化": f"{volume_change:.2f}%"},
        )


class DeliveryPolicyEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("交割与交易规则", "policy", "东方财富期货交易提示（交易所规则汇总）", "https://portal.eastmoneyfutures.com/pages/service/jyts.html")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        evidence = context.get("trading_rules")
        quote = context.get("quote")
        if evidence is None or not evidence.records or quote is None:
            raise ValueError("No current observed CJ trading rules")
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
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.72,
            f"当前合约涨跌停幅度 ±{limit_pct:.1f}%，保证金 {margin_pct:.1f}%；今日已使用限制空间 {limit_usage:.1f}%。",
            "越接近涨跌停，流动性和追加保证金风险越高；该维度只反映当前规则约束与价格压力。",
            weight=settings.weights.policy,
            source_name=evidence.source_name,
            source_url=evidence.source_url,
            observed_at=evidence.observed_at,
            sample_size=evidence.sample_size,
            key_metrics={
                "当前合约": rule["contract"],
                "涨跌停": f"±{limit_pct:.1f}%",
                "保证金": f"{margin_pct:.1f}%",
                "限制空间使用": f"{limit_usage:.1f}%",
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
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.76,
            f"当前持仓 {current:,} 手，相对近20日均值的标准分为 {oi_z:.2f}，同期价格变化 {price_change:.2f}%。",
            "拥挤方向与价格同向时趋势更强，但极端拥挤会提高反向平仓风险。",
            weight=settings.weights.positioning,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=valid_klines[-1].timestamp,
            sample_size=len(valid_klines[-20:]),
            key_metrics={
                "当前持仓": current,
                "20日平均持仓": round(oi_mean),
                "持仓Z分数": f"{oi_z:.2f}",
                "5日价格变化（有效K线）": f"{price_change:.2f}%",
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
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.86,
            f"ATR(14)={atr:.1f}，20日支撑 {support:.1f}、阻力 {resistance:.1f}，价格位于区间 {location * 100:.1f}% 位置。",
            "用 ATR 设置硬止损，以真实区间位置控制仓位，不以主观价格锚点下单。",
            weight=settings.weights.execution,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=quote.timestamp,
            sample_size=len(klines),
            key_metrics={"ATR(14)": f"{atr:.1f}", "20日支撑": f"{support:.1f}", "20日阻力": f"{resistance:.1f}", "区间位置": f"{location * 100:.1f}%"},
        )


class CrossContractSpreadEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("主力跨期价差", "spread", "东方财富红枣合约行情", "https://quote.eastmoney.com/center/gridlist.html#futures_czce")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        quote = context.get("quote")
        curve = context.get("term_structure") or {}
        # B2 fix: 按合约到期月份（year, month）排序，替代字典序，避免跨年时近月/远月颠倒
        contracts = sorted(
            ((code, item) for code, item in curve.items() if code not in {"CJM", "CJ0"} and item.price > 0),
            key=lambda x: _contract_month_key(x[0]),
        )
        if quote is None or not contracts:
            raise ValueError("No observed cross-contract prices")
        near_code, near = contracts[0]
        spread = quote.price - near.price
        spread_pct = spread / near.price * 100.0
        score = _clamp(spread_pct * 20.0)
        observed_at = max([quote.timestamp, *(item.timestamp for _, item in contracts)])
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.78,
            f"主力连续 {quote.price:.1f}，最近合约（到期日排序）{near_code} 为 {near.price:.1f}，价差 {spread:+.1f} 元/吨。",
            "主力相对近月溢价为正时偏强，折价时偏弱；连续合约不可直接用于交割。",
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
            },
        )


class TermStructureEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("期限结构", "term_structure", "东方财富红枣合约行情", "https://quote.eastmoney.com/center/gridlist.html#futures_czce")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        curve = context.get("term_structure") or {}
        # B2 fix: 同 CrossContractSpreadEngine，按到期月份排序确保斜率符号正确
        contracts = sorted(
            ((code, item) for code, item in curve.items() if code not in {"CJM", "CJ0"} and item.price > 0),
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
        structure = "升水结构（远月较高）" if slope > 0 else "贴水结构（近月较高）" if slope < 0 else "平坦结构"
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.84,
            f"{len(contracts)} 个真实合约（按到期日排序）形成{structure}，每档斜率 {slope:+.1f} 元，首尾价差率 {total_spread_pct:+.2f}%。",
            "远月升水通常反映持有成本或远期预期，近月升水通常反映近期偏紧；结合仓量确认。",
            weight=settings.weights.term_structure,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=max(item.timestamp for _, item in contracts),
            sample_size=len(contracts),
            key_metrics={"结构": structure, "曲线斜率": f"{slope:+.1f}元/档", "首尾价差率": f"{total_spread_pct:+.2f}%", "合约数": len(contracts)},
        )


class LiquidityVolatilityEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__("流动性与波动状态", "liquidity", "东方财富实时行情 + 新浪期货日K", "https://quote.eastmoney.com/qihuo/CJM.html")

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
        return PredictionResult.create(
            self.name,
            self.key,
            score,
            0.8,
            f"20日收益波动率 {volatility:.2f}%，日内振幅 {amplitude:.2f}%，实时成交量为20日均量 {volume_ratio:.2f} 倍。",
            "低流动性或高波动状态下降低仓位，避免按常态滑点假设执行。",
            weight=settings.weights.liquidity,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=quote.timestamp,
            sample_size=len(klines),
            key_metrics={"20日波动率": f"{volatility:.2f}%", "日内振幅": f"{amplitude:.2f}%", "成交量比": f"{volume_ratio:.2f}x", "成交额": f"{quote.turnover:.0f}"},
        )

"""
AI-QUANT 实时行情与历史数据接入模块 (Data Feed)
支持郑商所红枣期货 (CJ) 及国内主流期货实时行情拉取、订单流数据与历史K线
"""
import json
import logging
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger("AI-QUANT.DataFeed")


class MarketDataUnavailable(RuntimeError):
    """Raised when a trusted upstream cannot provide market data."""

@dataclass
class MarketQuote:
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    prev_close: float
    prev_settlement: float
    volume: int
    turnover: float
    open_interest: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_live: bool = False

@dataclass
class KLineBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: int
    # The actual tradable delivery contract represented by this bar. Main/
    # continuous series must populate this before a roll-aware backtest.
    contract_symbol: str | None = None

class FuturesDataFeed:
    """期货实时与历史数据接入器"""

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    @staticmethod
    def _map_symbol_to_eastmoney(symbol: str) -> str:
        """映射期货合约代码至东方财富代码格式 (如 CJ2701 -> 115.CJ701)"""
        sym = symbol.upper().strip()
        if sym.startswith("115."):
            return sym
        if sym in ("CJM", "CJ0"):
            return "115.CJM"
        if sym.startswith("CJ"):
            # CJ2701 -> CJ701
            num_part = sym[2:]
            if len(num_part) == 4:
                num_part = num_part[1:]  # '2701' -> '701'
            return f"115.CJ{num_part}"
        if sym.startswith("AP"):
            num_part = sym[2:]
            if len(num_part) == 4:
                num_part = num_part[1:]
            return f"115.AP{num_part}"
        if sym.startswith("CF"):
            num_part = sym[2:]
            if len(num_part) == 4:
                num_part = num_part[1:]
            return f"115.CF{num_part}"
        return f"115.{sym}"

    def get_realtime_quote(self, symbol: str = "CJ2701") -> MarketQuote:
        """获取单个期货合约实时快照数据"""
        secid = self._map_symbol_to_eastmoney(symbol)
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/get?"
            f"secid={secid}&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f86,f133,f169,f170"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                d = data.get("data")
                if d and d.get("f43") and d.get("f43") != "-":
                    price = float(d.get("f43", 0.0))
                    change = float(d.get("f169", 0.0))
                    change_pct = float(d.get("f170", 0.0)) / 100.0  # e.g. -272 -> -2.72%
                    high = float(d.get("f44", price))
                    low = float(d.get("f45", price))
                    open_p = float(d.get("f46", price))
                    prev_close = float(d.get("f60", price))
                    prev_settlement = round(price - change, 2)
                    volume = int(d.get("f47", 0))
                    turnover = float(d.get("f48", 0.0))
                    open_interest = int(d.get("f133", 0))
                    name = str(d.get("f58", symbol))
                    provider_timestamp = int(d.get("f86") or 0)
                    observed_at = (
                        datetime.fromtimestamp(provider_timestamp, tz=timezone.utc)
                        if provider_timestamp > 0
                        else datetime.now(timezone.utc)
                    )
                    return MarketQuote(
                        symbol=symbol,
                        name=name,
                        price=price,
                        change=change,
                        change_pct=change_pct,
                        open=open_p,
                        high=high,
                        low=low,
                        prev_close=prev_close,
                        prev_settlement=prev_settlement,
                        volume=volume,
                        turnover=turnover,
                        open_interest=open_interest,
                        timestamp=observed_at,
                        is_live=True
                    )
        except Exception as e:
            logger.warning("获取 %s 实时网络行情失败: %s", symbol, e)
            raise MarketDataUnavailable(f"No trusted real-time quote for {symbol}") from e

        raise MarketDataUnavailable(f"No trusted real-time quote for {symbol}")

    def get_term_structure(self) -> Dict[str, MarketQuote]:
        """获取红枣期货全月合约期限结构"""
        symbols = ["CJ612", "CJ701", "CJ703", "CJ705", "CJM"]
        secids = ",".join(self._map_symbol_to_eastmoney(s) for s in symbols)
        url = (
            f"https://push2.eastmoney.com/api/qt/ulist.np/get?"
            f"secids={secids}&fields=f12,f14,f2,f3,f4,f15,f16,f17,f18,f5,f6,f133"
        )
        result: Dict[str, MarketQuote] = {}
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                diff = data.get("data", {}).get("diff", [])
                for item in diff:
                    code = item.get("f12")
                    price = float(item.get("f2", 0))
                    chg_pct = float(item.get("f3", 0)) / 100.0
                    chg = float(item.get("f4", 0))
                    vol = int(item.get("f5", 0))
                    turnover = float(item.get("f6", 0))
                    high = float(item.get("f15", price))
                    low = float(item.get("f16", price))
                    open_p = float(item.get("f17", price))
                    prev_c = float(item.get("f18", price))
                    name = str(item.get("f14", code))
                    result[code] = MarketQuote(
                        symbol=code,
                        name=name,
                        price=price,
                        change=chg,
                        change_pct=chg_pct,
                        open=open_p,
                        high=high,
                        low=low,
                        prev_close=prev_c,
                        prev_settlement=round(price - chg, 2),
                        volume=vol,
                        turnover=turnover,
                        open_interest=0,
                        timestamp=datetime.now(timezone.utc),
                        is_live=True
                    )
                if result:
                    return result
        except Exception as e:
            logger.warning("获取期限结构失败: %s", e)
            raise MarketDataUnavailable("No trusted term structure available") from e

        raise MarketDataUnavailable("No trusted term structure available")

    def get_historical_klines(self, symbol: str = "CJ2701", days: int = 60) -> List[KLineBar]:
        """从新浪财经获取真实日 K 线，不生成任何合成序列。"""
        sina_symbol = self._map_symbol_to_sina(symbol)
        url = (
            "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
            f"var%20_{sina_symbol}=/InnerFuturesNewService.getDailyKLine?symbol={sina_symbol}"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Referer": "https://finance.sina.com.cn/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode("utf-8")
            match = re.search(r"=\((\[.*\])\);\s*$", payload, flags=re.DOTALL)
            if not match:
                raise ValueError("upstream returned no K-line array")
            rows = json.loads(match.group(1))
            bars = [
                KLineBar(
                    timestamp=datetime.strptime(row["d"], "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    open=float(row["o"]),
                    high=float(row["h"]),
                    low=float(row["l"]),
                    close=float(row["c"]),
                    volume=int(float(row["v"])),
                    open_interest=int(float(row["p"])),
                )
                for row in rows[-max(1, days):]
            ]
            if not bars:
                raise ValueError("upstream returned an empty K-line array")
            return bars
        except Exception as e:
            logger.warning("获取 %s 历史 K 线失败: %s", symbol, e)
            raise MarketDataUnavailable(f"No trusted historical data for {symbol}") from e

    @staticmethod
    def _map_symbol_to_sina(symbol: str) -> str:
        sym = symbol.upper().strip()
        if sym.endswith("M"):
            return f"{sym[:-1]}0"
        match = re.fullmatch(r"([A-Z]{1,4})(\d{3})", sym)
        if match:
            product, digits = match.groups()
            return f"{product}2{digits}"
        return sym

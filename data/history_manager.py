# -*- coding: utf-8 -*-
"""
AI-QUANT 历史行情数据管理模块 (History Manager)
管理已配置品种的日线连续合约数据、本地缓存与基础质量校验。
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from data.data_feed import KLineBar

logger = logging.getLogger("AI-QUANT.HistoryManager")

# 核心主流跟踪品种列表（覆盖农产品、黑色系、有色能源、化工、金融股指与国债）
CORE_FUTURES_SYMBOLS = {
    # 农产品与软商品
    "CJ0": {"name": "红枣主连", "exchange": "CZCE", "sector": "农产品"},
    "AP0": {"name": "苹果主连", "exchange": "CZCE", "sector": "农产品"},
    "CF0": {"name": "棉花主连", "exchange": "CZCE", "sector": "农产品"},
    "SR0": {"name": "白糖主连", "exchange": "CZCE", "sector": "农产品"},
    "M0":  {"name": "豆粕主连", "exchange": "DCE",  "sector": "农产品"},
    "C0":  {"name": "玉米主连", "exchange": "DCE",  "sector": "农产品"},
    "OI0": {"name": "菜油主连", "exchange": "CZCE", "sector": "农产品"},
    "P0":  {"name": "棕榈油主连", "exchange": "DCE", "sector": "农产品"},
    "Y0":  {"name": "豆油主连", "exchange": "DCE",  "sector": "农产品"},
    # 黑色金属与建材
    "RB0": {"name": "螺纹钢主连", "exchange": "SHFE", "sector": "黑色金属"},
    "HC0": {"name": "热卷主连", "exchange": "SHFE", "sector": "黑色金属"},
    "I0":  {"name": "铁矿石主连", "exchange": "DCE",  "sector": "黑色金属"},
    "J0":  {"name": "焦炭主连", "exchange": "DCE",  "sector": "黑色金属"},
    "JM0": {"name": "焦煤主连", "exchange": "DCE",  "sector": "黑色金属"},
    "FG0": {"name": "玻璃主连", "exchange": "CZCE", "sector": "建材"},
    "SA0": {"name": "纯碱主连", "exchange": "CZCE", "sector": "化工建材"},
    # 有色金属与新能源
    "CU0": {"name": "沪铜主连", "exchange": "SHFE", "sector": "有色金属"},
    "AL0": {"name": "沪铝主连", "exchange": "SHFE", "sector": "有色金属"},
    "ZN0": {"name": "沪锌主连", "exchange": "SHFE", "sector": "有色金属"},
    "NI0": {"name": "沪镍主连", "exchange": "SHFE", "sector": "有色金属"},
    "LC0": {"name": "碳酸锂主连", "exchange": "GFEX", "sector": "新能源"},
    "SI0": {"name": "工业硅主连", "exchange": "GFEX", "sector": "新能源"},
    # 贵金属
    "AU0": {"name": "黄金主连", "exchange": "SHFE", "sector": "贵金属"},
    "AG0": {"name": "白银主连", "exchange": "SHFE", "sector": "贵金属"},
    # 能源化工
    "TA0": {"name": "PTA主连", "exchange": "CZCE", "sector": "能源化工"},
    "MA0": {"name": "甲醇主连", "exchange": "CZCE", "sector": "能源化工"},
    "PP0": {"name": "聚丙烯主连", "exchange": "DCE",  "sector": "能源化工"},
    "EG0": {"name": "乙二醇主连", "exchange": "DCE",  "sector": "能源化工"},
    "SC0": {"name": "原油主连", "exchange": "INE",  "sector": "能源化工"},
    # 金融期货
    "IF0": {"name": "沪深300主连", "exchange": "CFFEX", "sector": "股指期货"},
    "IC0": {"name": "中证500主连", "exchange": "CFFEX", "sector": "股指期货"},
    "IM0": {"name": "中证1000主连", "exchange": "CFFEX", "sector": "股指期货"},
    "IH0": {"name": "上证50主连", "exchange": "CFFEX", "sector": "股指期货"},
    "T0":  {"name": "10年期国债主连", "exchange": "CFFEX", "sector": "国债期货"},
    # 其余当前交易所目录品种（目录共 87 个主力连续品种）
    "A0": {"name": "豆一主连", "exchange": "DCE", "sector": "农产品"},
    "AD0": {"name": "铝合金主连", "exchange": "SHFE", "sector": "有色金属"},
    "AO0": {"name": "氧化铝主连", "exchange": "SHFE", "sector": "有色金属"},
    "B0": {"name": "豆二主连", "exchange": "DCE", "sector": "农产品"},
    "BB0": {"name": "胶合板主连", "exchange": "DCE", "sector": "建材"},
    "BC0": {"name": "国际铜主连", "exchange": "INE", "sector": "有色金属"},
    "BR0": {"name": "丁二烯橡胶主连", "exchange": "SHFE", "sector": "能源化工"},
    "BU0": {"name": "沥青主连", "exchange": "SHFE", "sector": "能源化工"},
    "BZ0": {"name": "纯苯主连", "exchange": "DCE", "sector": "能源化工"},
    "CS0": {"name": "玉米淀粉主连", "exchange": "DCE", "sector": "农产品"},
    "CY0": {"name": "棉纱主连", "exchange": "CZCE", "sector": "纺织"},
    "EB0": {"name": "苯乙烯主连", "exchange": "DCE", "sector": "能源化工"},
    "EC0": {"name": "集运指数欧线主连", "exchange": "INE", "sector": "航运"},
    "FB0": {"name": "纤维板主连", "exchange": "DCE", "sector": "建材"},
    "FU0": {"name": "燃料油主连", "exchange": "SHFE", "sector": "能源化工"},
    "JD0": {"name": "鸡蛋主连", "exchange": "DCE", "sector": "农产品"},
    "JR0": {"name": "粳稻主连", "exchange": "CZCE", "sector": "农产品"},
    "L0": {"name": "塑料主连", "exchange": "DCE", "sector": "能源化工"},
    "LG0": {"name": "原木主连", "exchange": "DCE", "sector": "建材"},
    "LH0": {"name": "生猪主连", "exchange": "DCE", "sector": "农产品"},
    "LU0": {"name": "低硫燃料油主连", "exchange": "INE", "sector": "能源化工"},
    "NR0": {"name": "20号胶主连", "exchange": "INE", "sector": "能源化工"},
    "OP0": {"name": "胶版印刷纸主连", "exchange": "SHFE", "sector": "轻工"},
    "PB0": {"name": "沪铅主连", "exchange": "SHFE", "sector": "有色金属"},
    "PD0": {"name": "钯主连", "exchange": "GFEX", "sector": "贵金属"},
    "PF0": {"name": "短纤主连", "exchange": "CZCE", "sector": "纺织"},
    "PG0": {"name": "液化石油气主连", "exchange": "DCE", "sector": "能源化工"},
    "PK0": {"name": "花生主连", "exchange": "CZCE", "sector": "农产品"},
    "PL0": {"name": "丙烯主连", "exchange": "CZCE", "sector": "能源化工"},
    "PM0": {"name": "普麦主连", "exchange": "CZCE", "sector": "农产品"},
    "PR0": {"name": "瓶片主连", "exchange": "CZCE", "sector": "能源化工"},
    "PS0": {"name": "多晶硅主连", "exchange": "GFEX", "sector": "新能源"},
    "PT0": {"name": "铂主连", "exchange": "GFEX", "sector": "贵金属"},
    "PX0": {"name": "对二甲苯主连", "exchange": "CZCE", "sector": "能源化工"},
    "RI0": {"name": "早籼稻主连", "exchange": "CZCE", "sector": "农产品"},
    "RM0": {"name": "菜粕主连", "exchange": "CZCE", "sector": "农产品"},
    "RR0": {"name": "粳米主连", "exchange": "DCE", "sector": "农产品"},
    "RS0": {"name": "油菜籽主连", "exchange": "CZCE", "sector": "农产品"},
    "RU0": {"name": "天然橡胶主连", "exchange": "SHFE", "sector": "能源化工"},
    "SF0": {"name": "硅铁主连", "exchange": "CZCE", "sector": "黑色金属"},
    "SH0": {"name": "烧碱主连", "exchange": "CZCE", "sector": "能源化工"},
    "SM0": {"name": "锰硅主连", "exchange": "CZCE", "sector": "黑色金属"},
    "SN0": {"name": "沪锡主连", "exchange": "SHFE", "sector": "有色金属"},
    "SP0": {"name": "纸浆主连", "exchange": "SHFE", "sector": "轻工"},
    "SS0": {"name": "不锈钢主连", "exchange": "SHFE", "sector": "黑色金属"},
    "TF0": {"name": "5年期国债主连", "exchange": "CFFEX", "sector": "国债期货"},
    "TL0": {"name": "30年期国债主连", "exchange": "CFFEX", "sector": "国债期货"},
    "TS0": {"name": "2年期国债主连", "exchange": "CFFEX", "sector": "国债期货"},
    "UR0": {"name": "尿素主连", "exchange": "CZCE", "sector": "能源化工"},
    "V0": {"name": "PVC主连", "exchange": "DCE", "sector": "能源化工"},
    "WH0": {"name": "强麦主连", "exchange": "CZCE", "sector": "农产品"},
    "WR0": {"name": "线材主连", "exchange": "SHFE", "sector": "黑色金属"},
    "ZC0": {"name": "动力煤主连", "exchange": "CZCE", "sector": "能源"},
}

DEFAULT_CACHE_DIR = Path(os.getenv("HISTORY_CACHE_DIR", "data/history"))


class HistoryManager:
    """历史行情数据管理器"""

    def __init__(self, cache_dir: Optional[Path] = None, timeout: int = 8):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        sym = symbol.upper().strip()
        if sym.endswith("M"):
            return f"{sym[:-1]}0"
        return sym

    @staticmethod
    def _validate_bars(bars: List[KLineBar]) -> tuple[List[KLineBar], int]:
        """Return sorted, de-duplicated bars that satisfy basic OHLCV invariants."""
        valid_by_timestamp: Dict[datetime, KLineBar] = {}
        rejected = 0
        for bar in bars:
            finite_prices = all(
                isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0
                for value in (bar.open, bar.high, bar.low, bar.close)
            )
            valid_ohlc = (
                finite_prices
                and bar.high >= max(bar.open, bar.close, bar.low)
                and bar.low <= min(bar.open, bar.close, bar.high)
            )
            valid_volume = bar.volume >= 0 and bar.open_interest >= 0
            if not valid_ohlc or not valid_volume:
                rejected += 1
                continue
            if bar.timestamp in valid_by_timestamp:
                rejected += 1
            valid_by_timestamp[bar.timestamp] = bar
        return [valid_by_timestamp[key] for key in sorted(valid_by_timestamp)], rejected

    def fetch_from_sina(self, symbol: str) -> List[KLineBar]:
        """从新浪财经获取全量日K线（覆盖自上市以来的所有交易日）"""
        clean_sym = self._normalize_symbol(symbol)
        url = (
            "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
            f"var%20_{clean_sym}=/InnerFuturesNewService.getDailyKLine?symbol={clean_sym}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Referer": "https://finance.sina.com.cn/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            content = resp.read().decode("utf-8")

        match = re.search(r"=\((\[.*\])\);\s*$", content, flags=re.DOTALL)
        if not match:
            raise ValueError(f"No valid JSON array returned from Sina for {clean_sym}")

        rows = json.loads(match.group(1))
        bars: List[KLineBar] = []
        for r in rows:
            try:
                # 兼容部分带时间戳或日期的格式
                dt_str = r.get("d") or r.get("date")
                ts = datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                bar = KLineBar(
                    timestamp=ts,
                    open=float(r.get("o", 0.0)),
                    high=float(r.get("h", 0.0)),
                    low=float(r.get("l", 0.0)),
                    close=float(r.get("c", 0.0)),
                    volume=int(float(r.get("v", 0.0))),
                    open_interest=int(float(r.get("p", 0.0))),
                )
                bars.append(bar)
            except Exception as e:
                logger.debug("Failed parsing bar %s: %s", r, e)
                continue

        return bars

    def fetch_from_akshare(self, symbol: str) -> List[KLineBar]:
        """通过 AkShare 获取全量日K线备选通道"""
        import akshare as ak
        clean_sym = self._normalize_symbol(symbol)
        df = ak.futures_zh_daily_sina(symbol=clean_sym)
        if df is None or df.empty:
            raise ValueError(f"AkShare returned empty dataframe for {clean_sym}")

        bars: List[KLineBar] = []
        for _, row in df.iterrows():
            ts = datetime.strptime(str(row["date"]), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            bar = KLineBar(
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(float(row["volume"])),
                open_interest=int(float(row.get("hold", 0.0))),
            )
            bars.append(bar)
        return bars

    def get_historical_bars(self, symbol: str, force_download: bool = False, *, allow_download: bool = True) -> List[KLineBar]:
        """获取指定合约的历史K线（优先读取本地离线持久化缓存，缺失则自动在线下载）"""
        clean_sym = self._normalize_symbol(symbol)
        cache_file = self.cache_dir / f"{clean_sym}_daily.json"

        if not force_download and cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                bars = [
                    KLineBar(
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=int(item["volume"]),
                        open_interest=int(item.get("open_interest", 0)),
                    )
                    for item in data.get("bars", [])
                ]
                bars, rejected = self._validate_bars(bars)
                if rejected:
                    logger.warning("Rejected %d invalid cached bars for %s", rejected, clean_sym)
                if bars:
                    return bars
            except Exception as e:
                logger.warning("Failed reading cache for %s: %s, re-fetching...", clean_sym, e)

        if not allow_download:
            return []

        # Online refresh uses the declared source directly. Do not advertise an
        # optional fallback that is not installed in the production image.
        try:
            bars = self.fetch_from_sina(clean_sym)
        except Exception as e:
            logger.error("Sina history fetch failed for %s: %s", clean_sym, e)
            raise RuntimeError(f"Failed to fetch historical data for {clean_sym}") from e

        if bars:
            bars, rejected = self._validate_bars(bars)
            if rejected:
                logger.warning("Rejected %d invalid fetched bars for %s", rejected, clean_sym)
            self.save_cache(clean_sym, bars, rejected_bars=rejected)
        return bars

    def save_cache(self, symbol: str, bars: List[KLineBar], rejected_bars: int = 0) -> None:
        """保存历史K线至本地持久化 JSON 与 CSV"""
        clean_sym = self._normalize_symbol(symbol)
        json_file = self.cache_dir / f"{clean_sym}_daily.json"
        csv_file = self.cache_dir / f"{clean_sym}_daily.csv"

        bars, rejected = self._validate_bars(bars)
        rejected += rejected_bars
        if not bars:
            raise ValueError(f"No valid bars available for {clean_sym}")
        meta = CORE_FUTURES_SYMBOLS.get(clean_sym, {"name": clean_sym, "exchange": "UNKNOWN", "sector": "UNKNOWN"})

        # 保存为结构化 JSON
        payload = {
            "symbol": clean_sym,
            "display_name": meta.get("name"),
            "exchange": meta.get("exchange"),
            "sector": meta.get("sector"),
            "source": "SINA_FUTURES_DAILY",
            "series_type": "CONTINUOUS",
            "validation_rejected_bars": rejected,
            "total_bars": len(bars),
            "start_date": bars[0].timestamp.strftime("%Y-%m-%d") if bars else None,
            "end_date": bars[-1].timestamp.strftime("%Y-%m-%d") if bars else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "bars": [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "date": bar.timestamp.strftime("%Y-%m-%d"),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "open_interest": bar.open_interest,
                }
                for bar in bars
            ],
        }
        json_temp: Path | None = None
        csv_temp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cache_dir,
                prefix=f".{clean_sym}_",
                suffix=".json.tmp",
                delete=False,
            ) as f:
                json_temp = Path(f.name)
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # 同时保存为极速 CSV 便于外部工具与 pandas 读取
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cache_dir,
                prefix=f".{clean_sym}_",
                suffix=".csv.tmp",
                delete=False,
            ) as f:
                csv_temp = Path(f.name)
                f.write("date,open,high,low,close,volume,open_interest\n")
                for bar in bars:
                    f.write(
                        f"{bar.timestamp.strftime('%Y-%m-%d')},{bar.open:.2f},{bar.high:.2f},"
                        f"{bar.low:.2f},{bar.close:.2f},{bar.volume},{bar.open_interest}\n"
                    )
                f.flush()
                os.fsync(f.fileno())

            os.replace(json_temp, json_file)
            json_temp = None
            os.replace(csv_temp, csv_file)
            csv_temp = None
        except OSError as e:
            logger.warning("Filesystem is read-only or unwritable, skipping cache write: %s", e)
        finally:
            for temp_path in (json_temp, csv_temp):
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Failed cleaning temporary history file: %s", temp_path)

    def get_metadata(self, symbol: str) -> Dict[str, Any]:
        """Read cache provenance without treating file presence as live freshness."""
        clean_sym = self._normalize_symbol(symbol)
        cache_file = self.cache_dir / f"{clean_sym}_daily.json"
        if not cache_file.exists():
            return {}
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "symbol": data.get("symbol", clean_sym),
                "source": data.get("source", "SINA_FUTURES_DAILY"),
                "series_type": data.get("series_type", "CONTINUOUS"),
                "updated_at": data.get("updated_at"),
                "end_date": data.get("end_date"),
                "validation_rejected_bars": data.get("validation_rejected_bars", 0),
            }
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Failed reading metadata for %s: %s", clean_sym, exc)
            return {}

    def download_all(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """批量同步并持久化所有标的的历史数据"""
        target_symbols = symbols or list(CORE_FUTURES_SYMBOLS.keys())
        summary: Dict[str, Dict[str, Any]] = {}

        for sym in target_symbols:
            meta = CORE_FUTURES_SYMBOLS.get(sym, {"name": sym, "exchange": "UNKNOWN", "sector": "UNKNOWN"})
            try:
                bars = self.get_historical_bars(sym, force_download=True)
                summary[sym] = {
                    "name": meta["name"],
                    "exchange": meta["exchange"],
                    "sector": meta["sector"],
                    "bars_count": len(bars),
                    "start_date": bars[0].timestamp.strftime("%Y-%m-%d") if bars else None,
                    "end_date": bars[-1].timestamp.strftime("%Y-%m-%d") if bars else None,
                    "status": "SUCCESS",
                }
                logger.info("Successfully synced %s (%s): %d bars", sym, meta["name"], len(bars))
            except Exception as e:
                summary[sym] = {
                    "name": meta["name"],
                    "status": "FAILED",
                    "error": str(e),
                }
                logger.warning("Failed syncing %s: %s", sym, e)

        return summary

    def get_status(self) -> Dict[str, Any]:
        """获取本地已持久化的历史数据状态摘要"""
        items = []
        for file in self.cache_dir.glob("*_daily.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                symbol = data.get("symbol")
                validated_bars = self.get_historical_bars(symbol) if symbol else []
                raw_count = len(data.get("bars", []))
                items.append({
                    "symbol": symbol,
                    "displayName": data.get("display_name"),
                    "exchange": data.get("exchange"),
                    "sector": data.get("sector"),
                    "totalBars": len(validated_bars),
                    "startDate": validated_bars[0].timestamp.strftime("%Y-%m-%d") if validated_bars else None,
                    "endDate": validated_bars[-1].timestamp.strftime("%Y-%m-%d") if validated_bars else None,
                    "updatedAt": data.get("updated_at"),
                    "source": data.get("source", "SINA_FUTURES_DAILY"),
                    "seriesType": data.get("series_type", "CONTINUOUS"),
                    "rejectedBars": (
                        max(0, int(data.get("validation_rejected_bars", 0)))
                        + max(0, raw_count - len(validated_bars))
                    ),
                })
            except Exception as e:
                logger.warning("Error reading metadata from %s: %s", file, e)
        items.sort(key=lambda x: x.get("symbol") or "")
        return {
            "totalSymbols": len(items),
            "totalBars": sum(item.get("totalBars", 0) for item in items),
            "cacheDir": str(self.cache_dir),
            "symbols": items,
        }


history_manager = HistoryManager()

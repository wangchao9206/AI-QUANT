import logging
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import date, datetime
from dataclasses import replace
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from data.data_feed import KLineBar, MarketDataUnavailable, MarketQuote
from data.evidence_feed import EvidenceFeed, SHANGHAI_TZ
from data.live_feed import normalize_product_root, root_symbol
from data.trading_day import merge_daily_quote
from data.tqsdk_feed import create_market_feed
from data.tqsdk_backtest import TqSdkBacktestDataProvider, TqSdkBacktestUnavailable
from data.history_manager import history_manager, CORE_FUTURES_SYMBOLS
from backtesting.backtester import backtester, QuantitativeBacktester
from .workflows import CheckRequest as WorkflowCheckRequest, DebugRequest as WorkflowDebugRequest
from .workflows import check as check_workflow, debug as debug_workflow
from engines.fusion_engine import HolisticFusionEngine

from .models import (
    BacktestRequest,
    BacktestResponse,
    HealthResponse,
    HistoryResponse,
    InstrumentCatalogResponse,
    LeadsResponse,
    OpportunityLeadResponse,
    PredictionResponse,
    ProviderStatusResponse,
    QuoteResponse,
    TermStructureResponse,
)
from .research import PlanRequest, ResearchService, risk_scenario, validation_snapshot
from .radar import OverviewRadar
from .research_library import router as research_library_router
from .mentor_ledger import LedgerRequest, analyze_ledger
from .paper_strategy import StrategyRequest, evaluate as evaluate_paper_strategy, live_context


logger = logging.getLogger("AI-QUANT.AlgorithmAPI")
SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,4}[A-Z0-9]{0,8}$")
BACKTEST_CAPACITY = threading.BoundedSemaphore(
    max(1, int(os.getenv("BACKTEST_MAX_CONCURRENCY", "2")))
)


class PredictionService:
    def __init__(self) -> None:
        self.market_feed = create_market_feed()
        self.evidence_feed = EvidenceFeed(timeout=int(os.getenv("EVIDENCE_TIMEOUT", "3")))
        self.engine = HolisticFusionEngine()
        self._leads_cache: dict[str, Any] | None = None
        self._leads_cache_time: datetime | None = None
        self._leads_cache_ttl_seconds = max(5, int(os.getenv("LEADS_CACHE_TTL_SECONDS", "60")))
        self._leads_lock = threading.Lock()


    def predict(self, symbol: str, trace_id: str) -> dict[str, Any]:
        analysis_time = datetime.now(SHANGHAI_TZ)
        try:
            quote, klines, market_status = self.market_feed.prediction_inputs(symbol)
        except ValueError as exc:
            raise MarketDataUnavailable(str(exc)) from exc
        product = self.market_feed.product(symbol)
        product_name = product["name"] if product else re.sub(r"\d+|连续$", "", quote.name)
        product_root = root_symbol(symbol)
        loaders = {
            "term_structure": lambda: self._term_structure_quotes(symbol),
            "weather": lambda: self.evidence_feed.get_weather(product_root),
            "news": lambda: self.evidence_feed.get_news(product_root, product_name),
            "trading_rules": lambda: self.evidence_feed.get_trading_rules(product_root, product_name),
        }
        collected: dict[str, Any] = {"quote": quote, "klines": klines}
        with ThreadPoolExecutor(max_workers=len(loaders), thread_name_prefix="evidence") as pool:
            futures = {pool.submit(loader): key for key, loader in loaders.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    collected[key] = future.result()
                except Exception as exc:
                    logger.warning("optional_evidence_unavailable", extra={"key": key, "error": str(exc), "trace_id": trace_id})

        resolve_day = getattr(self.market_feed, "trading_date_for", None)
        trading_date = resolve_day(quote.timestamp) if resolve_day else None
        klines = merge_daily_quote(klines, quote, trading_date)
        collected.update({"symbol": symbol, "quote": quote, "klines": klines, "analysis_time": analysis_time})
        decision = self.engine.evaluate_all(collected)

        def serialize_dimensions(items):
            return [
            {
                "key": key,
                "name": value.dimension_name,
                "score": value.score,
                "direction": value.direction,
                "confidence": value.confidence,
                "summary": value.summary,
                "recommendation": value.recommendation,
                "category": value.category,
                "data_status": value.data_status,
                "included_in_score": value.included_in_score,
                "weight": value.weight,
                "source_name": value.source_name,
                "source_url": value.source_url,
                "observed_at": value.observed_at,
                "sample_size": value.sample_size,
                "key_metrics": value.key_metrics,
            }
            for key, value in items.items()
            ]

        dimensions = serialize_dimensions(decision.dimension_results)
        return {
            "symbol": decision.symbol,
            "display_name": quote.name,
            "price": quote.price,
            "change": quote.change,
            "change_pct": quote.change_pct,
            "composite_score": decision.composite_score,
            "resonance": decision.directional_resonance,
            "confidence": decision.composite_confidence,
            "signal": decision.primary_signal,
            "action_directive": decision.action_directive,
            "recommended_position_pct": decision.recommended_position_pct,
            "target_price": decision.target_price_tp1,
            "stop_loss_price": decision.stop_loss_price,
            "data_status": market_status,
            "data_timestamp": quote.timestamp.astimezone().isoformat(),
            "model_version": settings.version,
            "trace_id": trace_id,
            "dimensions": dimensions,
            "cultural_references": serialize_dimensions(decision.cultural_references),
            "event_windows": decision.key_event_windows,
        }

    def market_snapshot(self, symbol: str) -> dict[str, Any]:
        """Return the latest persisted observed-data snapshot without upstream I/O."""
        snapshot = self.market_feed.snapshot(symbol)
        if not snapshot["quote"] or not snapshot["history"]:
            raise MarketDataUnavailable(f"Observed market snapshot for {symbol} is still warming up")
        return snapshot

    def _term_structure_quotes(self, symbol: str) -> dict[str, MarketQuote]:
        snapshot = self.market_feed.term_snapshot(root_symbol(symbol))
        result: dict[str, MarketQuote] = {}
        for item in snapshot["contracts"]:
            observed_at = datetime.fromisoformat(item["dataTimestamp"])
            price = float(item["price"])
            code = item["contract"]
            result[code] = MarketQuote(
                symbol=code,
                name=code,
                price=price,
                change=0.0,
                change_pct=0.0,
                open=price,
                high=price,
                low=price,
                prev_close=price,
                prev_settlement=price,
                volume=0,
                turnover=0.0,
                open_interest=0,
                timestamp=observed_at,
                is_live=snapshot["dataStatus"] == "FRESH",
            )
        if not result:
            raise MarketDataUnavailable("No observed term structure is available")
        return result

    def discover_leads(self, trace_id: str = "lead-scan") -> dict[str, Any]:
        """Return a recent scan and serialize cold refreshes to prevent cache stampedes."""
        now = datetime.now(SHANGHAI_TZ)
        if self._leads_cache is not None and self._leads_cache_time is not None:
            if (now - self._leads_cache_time).total_seconds() < self._leads_cache_ttl_seconds:
                return self._leads_cache

        with self._leads_lock:
            now = datetime.now(SHANGHAI_TZ)
            if self._leads_cache is not None and self._leads_cache_time is not None:
                if (now - self._leads_cache_time).total_seconds() < self._leads_cache_ttl_seconds:
                    return self._leads_cache
            return self._discover_leads_uncached(trace_id)

    def _discover_leads_uncached(self, trace_id: str = "lead-scan") -> dict[str, Any]:
        """Scan active futures instruments, apply multi-algorithm rules with real-time market data & news,
        and generate high-conviction opportunity leads complete with detailed analysis and operations."""
        candidates = [
            ("CJM", "CZCE", "红枣主力", "农产品林果"),
            ("LCM", "GFEX", "碳酸锂主力", "新能源有色"),
            ("IFM", "CFFEX", "沪深300主力", "金融股指"),
            ("RBM", "SHFE", "螺纹钢主力", "黑色建材"),
            ("MM", "DCE", "豆粕主力", "油脂油料"),
            ("SIM", "GFEX", "工业硅主力", "光伏原材料"),
            ("AUM", "SHFE", "沪金主力", "贵金属避险"),
            ("JMM", "DCE", "焦煤主力", "黑色炉料"),
            ("TM", "CFFEX", "十债主力", "利率债基准"),
        ]

        now = datetime.now(SHANGHAI_TZ)

        leads: list[dict[str, Any]] = []

        def eval_candidate(candidate_tuple):
            sym, exch, default_name, sector = candidate_tuple
            try:
                pred = self.predict(sym, f"{trace_id}-{sym.lower()}")
                return (candidate_tuple, pred, None)
            except Exception as e:
                return (candidate_tuple, None, e)

        scan_workers = max(1, min(int(os.getenv("LEADS_SCAN_WORKERS", "4")), len(candidates)))
        with ThreadPoolExecutor(max_workers=scan_workers, thread_name_prefix="leads_scan") as pool:
            scan_results = list(pool.map(eval_candidate, candidates))

        for (sym, exch, default_name, sector), pred, err in scan_results:
            if not pred:
                logger.debug(f"lead_scan_skip symbol={sym} err={err}")
                continue


            price = float(pred["price"])
            change = float(pred["change"])
            change_pct = float(pred["change_pct"])
            comp_score = float(pred["composite_score"])
            confidence = float(pred["confidence"])
            resonance = float(pred["resonance"])
            dim_map = {d["key"]: d for d in pred.get("dimensions", [])}
            name = pred.get("display_name") or default_name

            all_dims = list(pred.get("dimensions", [])) + list(pred.get("cultural_references", []))
            scored_dims = [d for d in all_dims if d.get("score") is not None]
            pos_count = sum(float(d["score"]) > 0 for d in scored_dims)
            neg_count = sum(float(d["score"]) < 0 for d in scored_dims)
            sorted_dims = sorted(
                scored_dims,
                key=lambda x: abs(float(x["score"])),
                reverse=True
            )[:3]

            key_evidence = [
                {
                    "name": d["name"],
                    "score": float(d["score"]),
                    "direction": d["direction"],
                    "summary": d["summary"][:120] if d.get("summary") else "",
                }
                for d in sorted_dims
            ]

            is_bull = comp_score > 0
            lead_count_before = len(leads)

            def get_score(dim_key: str, default: float = 0.0) -> float:
                d = dim_map.get(dim_key)
                if d and d.get("score") is not None:
                    try:
                        return float(d["score"])
                    except (ValueError, TypeError):
                        pass
                return default

            # 算法 1：十四维全息多空共振算法 (S 级最高确定性)
            if (comp_score >= 60 or comp_score <= -30) and resonance >= 0.70:
                direction = "BULLISH" if is_bull else "BEARISH"
                signal_desc = "十四维高确信度同向共振 · 强烈看多" if is_bull else "十四维高确信度同向共振 · 强烈看空"
                spread_val = max(price * 0.008, 10.0)
                entry_min = round(price - spread_val / 2, 1)
                entry_max = round(price + spread_val / 2, 1)
                leads.append({
                    "id": f"lead-{sym.lower()}-resonance",
                    "symbol": sym,
                    "display_name": name,
                    "exchange": exch,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "direction": direction,
                    "signal": signal_desc,
                    "urgency": "S",
                    "composite_score": comp_score,
                    "confidence": confidence,
                    "algorithm_type": "DIMENSION_RESONANCE",
                    "algorithm_name": "十四维全息多空共振算法",
                    "algorithm_badge": "十四维大共振",
                    "analysis": {
                        "core_anomaly": "线索分类由综合评分和方向共振阈值触发，详细数值以统一证据层为准。",
                        "market_context": "盘面说明只使用当前行情与返回的维度摘要。",
                        "news_driver": "新闻归因仅在新闻或政策维度返回可验证摘要时展示。",
                        "key_evidence": key_evidence,
                    },
                    "execution": {
                        "action_directive": f"【S级核心共振机会】建议以重点仓位分批介入，顺应十四维大共振主浪趋势，依托分时均价线回调即是逢低建仓良机。" if is_bull else f"【S级核心共振机会】建议顺势做空或快速止损减保，勿逆大势接下坠飞刀，盘面反弹遇阻均线即为空点。",
                        "entry_zone": f"{entry_min} ~ {entry_max}",
                        "target_price": pred.get("target_price") or round(price * (1.06 if is_bull else 0.94), 1),
                        "stop_loss_price": pred.get("stop_loss_price") or round(price * (0.97 if is_bull else 1.03), 1),
                        "recommended_position_pct": 28.0,
                        "risk_reward_ratio": "3.8:1",
                        "invalidation_condition": f"若日线有效收盘跌破防守止损线 {pred.get('stop_loss_price') or round(price * 0.97, 1)} 或多空共振度衰退至 50% 以下，确认为多头动能耗尽，线索失效立即坚决离场。" if is_bull else f"若日线收盘放量突破上方阻力止损线 {pred.get('stop_loss_price') or round(price * 1.03, 1)} 或突发重磅利好政策，则空头逻辑失效平仓。",
                    },
                    "discovered_at": now.isoformat(),
                })

            # 算法 2：量价动能突破算法 (A 级机会)
            elif abs(change_pct) >= 0.8 or abs(get_score("momentum")) >= 25:
                direction = "BULLISH" if change_pct >= 0 else "BEARISH"
                signal_desc = "放量突破前期阻力平台 · 顺势看多" if direction == "BULLISH" else "跌破近20日低位支撑 · 破位看空"
                spread_val = max(price * 0.006, 8.0)
                leads.append({
                    "id": f"lead-{sym.lower()}-momentum",
                    "symbol": sym,
                    "display_name": name,
                    "exchange": exch,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "direction": direction,
                    "signal": signal_desc,
                    "urgency": "A",
                    "composite_score": comp_score,
                    "confidence": confidence,
                    "algorithm_type": "MOMENTUM_BREAKOUT",
                    "algorithm_name": "量价动能突破算法",
                    "algorithm_badge": "突破放量",
                    "analysis": {
                        "core_anomaly": "线索分类由量价维度分数或已观测涨跌幅阈值触发。",
                        "market_context": "盘面说明只使用当前行情与返回的维度摘要。",
                        "news_driver": "未获得可验证新闻摘要时不作新闻归因。",
                        "key_evidence": key_evidence,
                    },
                    "execution": {
                        "action_directive": f"顺应动能突破右侧跟进，逢分时回踩均线分批建立多单，享受突破后的主升浪溢价。" if direction == "BULLISH" else f"顺应破位势能轻仓沽空，逢反弹乏力时逢高加空，吃足下行惯性空间。",
                        "entry_zone": f"{round(price - spread_val/2, 1)} ~ {round(price + spread_val/2, 1)}",
                        "target_price": pred.get("target_price") or round(price * (1.05 if direction == "BULLISH" else 0.95), 1),
                        "stop_loss_price": pred.get("stop_loss_price") or round(price * (0.975 if direction == "BULLISH" else 1.025), 1),
                        "recommended_position_pct": 20.0,
                        "risk_reward_ratio": "2.8:1",
                        "invalidation_condition": f"若价格重回箱体内部并跌破关键止损位，确认为假突破诱多洗盘，应迅速止损保护本金。" if direction == "BULLISH" else f"若价格放量反包重回关键支撑上方，破位逻辑被证伪，应立即平空止损。",
                    },
                    "discovered_at": now.isoformat(),
                })

            # 算法 3：供需基本面矛盾错配算法 (A 级机会)
            elif abs(get_score("supply_demand")) >= 18:
                sd_score = get_score("supply_demand")
                direction = "BULLISH" if sd_score > 0 else "BEARISH"
                signal_desc = "显性低库存与刚性交割支撑 · 逢低看多" if direction == "BULLISH" else "高库存累库与下游压制 · 逢高看空"
                spread_val = max(price * 0.01, 12.0)
                leads.append({
                    "id": f"lead-{sym.lower()}-supply",
                    "symbol": sym,
                    "display_name": name,
                    "exchange": exch,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "direction": direction,
                    "signal": signal_desc,
                    "urgency": "A",
                    "composite_score": comp_score,
                    "confidence": confidence,
                    "algorithm_type": "SUPPLY_DEMAND",
                    "algorithm_name": "供需矛盾与基本面错配算法",
                    "algorithm_badge": "供需错配",
                    "analysis": {
                        "core_anomaly": "线索分类由供需维度返回的实际分数触发。",
                        "market_context": "不在缺少库存、仓单或现货输入时推断供需事实。",
                        "news_driver": "未获得可验证新闻摘要时不作新闻归因。",
                        "key_evidence": key_evidence,
                    },
                    "execution": {
                        "action_directive": f"建议左侧分批布局多头底仓，以现货仓单成本为底线锚点，耐心等待基本面矛盾引爆期现回归行情。" if direction == "BULLISH" else f"建议逢盘面反弹遇阻分批做空，中线持有赚取供需过剩折价利润。",
                        "entry_zone": f"{round(price - spread_val/2, 1)} ~ {round(price + spread_val/2, 1)}",
                        "target_price": pred.get("target_price") or round(price * (1.07 if direction == "BULLISH" else 0.93), 1),
                        "stop_loss_price": pred.get("stop_loss_price") or round(price * (0.97 if direction == "BULLISH" else 1.03), 1),
                        "recommended_position_pct": 22.0,
                        "risk_reward_ratio": "3.2:1",
                        "invalidation_condition": f"若主产区大面积超预期复产或仓单集中大量注销，则基本面支撑逻辑失效，立即止损。" if direction == "BULLISH" else f"若上游突发大面积不可抗力减产停产导致库存快速去化，则做空逻辑失效平仓。",
                    },
                    "discovered_at": now.isoformat(),
                })

            # 算法 4：突发消息与舆情驱动算法 (B 级机会)
            elif abs(get_score("sentiment")) >= 15 or abs(get_score("policy")) >= 15:
                sent_score = get_score("sentiment") + get_score("policy")
                direction = "BULLISH" if sent_score >= 0 else "BEARISH"
                signal_desc = "突发行业政策舆情催化 · 脉冲试多" if direction == "BULLISH" else "政策监管或行业利空发酵 · 规避下行"
                spread_val = max(price * 0.007, 10.0)
                leads.append({
                    "id": f"lead-{sym.lower()}-sentiment",
                    "symbol": sym,
                    "display_name": name,
                    "exchange": exch,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "direction": direction,
                    "signal": signal_desc,
                    "urgency": "B",
                    "composite_score": comp_score,
                    "confidence": confidence,
                    "algorithm_type": "SENTIMENT_NEWS",
                    "algorithm_name": "突发消息与舆情驱动算法",
                    "algorithm_badge": "突发消息催化",
                    "analysis": {
                        "core_anomaly": f"线索分类由已返回的舆情和政策维度合计分数 {sent_score:+.1f} 触发。",
                        "market_context": "盘面说明只使用当前行情与返回的维度摘要。",
                        "news_driver": "新闻内容直接引用已返回的可验证摘要，不补写事件。",
                        "key_evidence": key_evidence,
                    },
                    "execution": {
                        "action_directive": f"消息驱动行情波动剧烈，建议以轻仓波段参与为主，快进快出严守止盈，切勿单凭情绪高潮盲目追高。" if direction == "BULLISH" else f"短期利空消息发酵期保持观望或轻仓顺势做空，避免盲目逆势接飞刀。",
                        "entry_zone": f"{round(price - spread_val/2, 1)} ~ {round(price + spread_val/2, 1)}",
                        "target_price": pred.get("target_price") or round(price * (1.04 if direction == "BULLISH" else 0.96), 1),
                        "stop_loss_price": pred.get("stop_loss_price") or round(price * (0.98 if direction == "BULLISH" else 1.02), 1),
                        "recommended_position_pct": 15.0,
                        "risk_reward_ratio": "2.5:1",
                        "invalidation_condition": f"若官方发布澄清声明、消息证实被过度夸大或盘面价格在利好下放量滞涨，应在第一时间离场。" if direction == "BULLISH" else f"若利空出尽盘面出现放量止跌长下影线，则利空消化完毕，应立即平仓。",
                    },
                    "discovered_at": now.isoformat(),
                })

            # 算法 5：期限结构反套与基差收敛算法 (B 级机会)
            elif abs(get_score("term_structure")) >= 15 or abs(get_score("basis")) >= 15:
                ts_score = get_score("term_structure") or get_score("basis")
                direction = "BULLISH" if ts_score > 0 else "BEARISH"
                signal_desc = "期限结构深度贴水修复 · 跨期/基差做多" if direction == "BULLISH" else "远期结构大幅升水承压 · 反套沽空"
                spread_val = max(price * 0.007, 10.0)
                leads.append({
                    "id": f"lead-{sym.lower()}-term",
                    "symbol": sym,
                    "display_name": name,
                    "exchange": exch,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "direction": direction,
                    "signal": signal_desc,
                    "urgency": "B",
                    "composite_score": comp_score,
                    "confidence": confidence,
                    "algorithm_type": "TERM_STRUCTURE",
                    "algorithm_name": "期限结构反套与基差收敛算法",
                    "algorithm_badge": "期限基差反套",
                    "analysis": {
                        "core_anomaly": "线索分类由期限结构或基差维度的实际返回分数触发。",
                        "market_context": "不在缺少真实远近月曲线时推断升贴水或逼仓事实。",
                        "news_driver": "未获得可验证新闻摘要时不作新闻归因。",
                        "key_evidence": key_evidence,
                    },
                    "execution": {
                        "action_directive": f"买入近月同时关注现货基差走阔，亦可配置买近月卖远月跨期正套，稳稳博取期现回归与展期收益红利。" if direction == "BULLISH" else f"远月升水虚高，建议逢高沽空远月或建立买近卖远反套头寸，赚取期限结构走平收益。",
                        "entry_zone": f"{round(price - spread_val/2, 1)} ~ {round(price + spread_val/2, 1)}",
                        "target_price": pred.get("target_price") or round(price * (1.05 if direction == "BULLISH" else 0.95), 1),
                        "stop_loss_price": pred.get("stop_loss_price") or round(price * (0.98 if direction == "BULLISH" else 1.02), 1),
                        "recommended_position_pct": 18.0,
                        "risk_reward_ratio": "3.0:1",
                        "invalidation_condition": f"若月差不收敛反而反向击穿历史极值，表明产业供需逻辑发生结构性突变，应平仓退出。" if direction == "BULLISH" else f"若远月升水进一步由于投机炒作非理性扩大，应触发保护性止损。",
                    },
                    "discovered_at": now.isoformat(),
                })

            # 默认作为时空周期拐点算法 (B 级机会)
            elif abs(comp_score) >= 20 and confidence >= 0.55:
                direction = "BULLISH" if comp_score >= 0 else "BEARISH"
                signal_desc = "中华时历变盘临界点 · 临界试探" if direction == "BULLISH" else "时空周期转折空头施压 · 观望警惕"
                spread_val = max(price * 0.006, 8.0)
                leads.append({
                    "id": f"lead-{sym.lower()}-cycle",
                    "symbol": sym,
                    "display_name": name,
                    "exchange": exch,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "direction": direction,
                    "signal": signal_desc,
                    "urgency": "B",
                    "composite_score": comp_score,
                    "confidence": confidence,
                    "algorithm_type": "CYCLE_PIVOT",
                    "algorithm_name": "时空周期与拐点时历算法",
                    "algorithm_badge": "时空拐点变盘",
                    "analysis": {
                        "core_anomaly": "文化维度只作为非实证时间参考，不单独证明价格拐点。",
                        "market_context": "未计算样本外突破概率时不展示概率结论。",
                        "news_driver": "文化参考不替代新闻、库存、仓单或产业数据。",
                        "key_evidence": key_evidence,
                    },
                    "execution": {
                        "action_directive": f"以极窄的 ATR 止损尝试突破方向布局，博取大级别新一轮趋势主浪的起爆点，盈亏比极具吸引力。",
                        "entry_zone": f"{round(price - spread_val/2, 1)} ~ {round(price + spread_val/2, 1)}",
                        "target_price": pred.get("target_price") or round(price * (1.06 if direction == "BULLISH" else 0.94), 1),
                        "stop_loss_price": pred.get("stop_loss_price") or round(price * (0.98 if direction == "BULLISH" else 1.02), 1),
                        "recommended_position_pct": 18.0,
                        "risk_reward_ratio": "4.0:1",
                        "invalidation_condition": f"若盘面突破后未能放量延续，反而反向跌破变盘箱体下沿，判定为假突破洗盘，立即坚决止损。",
                    },
                    "discovered_at": now.isoformat(),
                })

            # Replace promotional prose with facts that are present in the prediction payload.
            # The classifier above only chooses a label; it is not allowed to invent inventory,
            # order-flow, news, probability, or statistical-significance claims.
            if len(leads) > lead_count_before:
                lead = leads[-1]
                direction = lead["direction"]
                direction_label = "多头" if direction == "BULLISH" else "空头"
                dominant_count = pos_count if direction == "BULLISH" else neg_count
                evidence_text = "；".join(
                    evidence["summary"] for evidence in key_evidence if evidence.get("summary")
                ) or "暂无可展示的维度摘要"
                evidence_names = "、".join(evidence["name"] for evidence in key_evidence) or "无"
                news_evidence = next(
                    (
                        d for d in scored_dims
                        if d.get("key") in {"sentiment", "policy"}
                        and d.get("data_status") in {"FRESH", "CACHED"}
                        and d.get("summary")
                    ),
                    None,
                )
                target = float(lead["execution"]["target_price"])
                stop = float(lead["execution"]["stop_loss_price"])
                reward = abs(target - price)
                risk = abs(price - stop)
                risk_reward = reward / risk if risk > 0 else 0.0
                model_position = abs(float(pred.get("recommended_position_pct") or 0.0))
                if model_position <= 1:
                    model_position *= 100
                observed_at = pred.get("data_timestamp") or now.isoformat()

                lead["analysis"] = {
                    "core_anomaly": (
                        f"综合评分 {comp_score:+.1f}，方向共振度 {resonance:.0%}；"
                        f"已返回的 {len(scored_dims)} 个有分数维度中，{dominant_count} 个指向{direction_label}。"
                    ),
                    "market_context": (
                        f"最新观测价 {price:.2f}，当日变动 {change_pct:+.2f}%。"
                        f"主要证据来自 {evidence_names}：{evidence_text}"
                    ),
                    "news_driver": (
                        str(news_evidence["summary"])
                        if news_evidence
                        else "未获得可验证的独立新闻或政策驱动证据，本线索不作新闻归因。"
                    ),
                    "key_evidence": key_evidence,
                }
                lead["execution"] = {
                    "action_directive": str(pred.get("action_directive") or "仅供研究观察，不构成交易指令"),
                    "entry_zone": f"参考观测价 {price:.2f}",
                    "target_price": target,
                    "stop_loss_price": stop,
                    "recommended_position_pct": min(model_position, 30.0),
                    "risk_reward_ratio": f"{risk_reward:.2f}:1" if risk_reward > 0 else "不可计算",
                    "invalidation_condition": f"模型止损参考价 {stop:.2f} 被触及，或综合信号方向反转。",
                }
                lead["data_status"] = pred.get("data_status", "DEGRADED")
                lead["data_timestamp"] = observed_at

        urgency_weight = {"S": 3, "A": 2, "B": 1}
        leads.sort(key=lambda x: (urgency_weight.get(x["urgency"], 0), abs(x["composite_score"])), reverse=True)

        status_rank = {"FRESH": 0, "CACHED": 1, "DEGRADED": 2}
        aggregate_status = max(
            (lead.get("data_status", "DEGRADED") for lead in leads),
            key=lambda status: status_rank.get(status, 2),
            default="DEGRADED",
        )
        result = {
            "source": "AI-QUANT 智能线索雷达扫描引擎",
            "data_status": aggregate_status,
            "scanned_count": len(candidates),
            "leads_count": len(leads),
            "data_timestamp": now.isoformat(),
            "leads": leads,
        }
        self._leads_cache = result
        self._leads_cache_time = now
        return result




prediction_service = PredictionService()
research_service = ResearchService(prediction_service)
overview_radar = OverviewRadar(prediction_service, history_manager)
backtest_data_provider = TqSdkBacktestDataProvider()


def normalize_symbol(symbol: str) -> str:
    normalized_symbol = symbol.upper().strip()
    if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
        raise HTTPException(status_code=422, detail="Invalid futures symbol")
    return normalized_symbol


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("algorithm_service_started", extra={"model_version": settings.version})
    prediction_service.market_feed.start()
    try:
        yield
    finally:
        prediction_service.market_feed.stop()


app = FastAPI(
    title="AI-QUANT Algorithm Service",
    version=settings.version,
    docs_url="/docs" if os.getenv("ENABLE_API_DOCS", "true").lower() == "true" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-Trace-Id", "Content-Type"],
    expose_headers=["X-Trace-Id"],
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
    request.state.trace_id = trace_id[:128]
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="UP", service="algorithm-service", model_version=settings.version)


app.include_router(research_library_router)


@app.get('/api/v1/research/context/{symbol}')
async def research_context(symbol: str, request: Request):
    try:
        return await run_in_threadpool(research_service.context, normalize_symbol(symbol), request.state.trace_id)
    except (MarketDataUnavailable, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post('/api/v1/research/plan')
async def research_plan(req: PlanRequest, request: Request):
    try:
        context = await run_in_threadpool(research_service.context, normalize_symbol(req.symbol), request.state.trace_id, True)
        return risk_scenario(context, req)
    except (MarketDataUnavailable, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get('/api/v1/research/validation')
async def research_validation():
    return await run_in_threadpool(validation_snapshot)


@app.get('/api/v1/research/events/study')
async def historical_event_study():
    from .event_study import event_study
    return await run_in_threadpool(overview_radar.cache.get, 'event-study', 300, lambda: event_study(history_manager))


@app.get('/api/v1/research/mentors')
async def trading_mentors():
    from .mentor_research import mentor_catalog
    return await run_in_threadpool(mentor_catalog)




@app.post('/api/v1/research/mentors/analyze-ledger')
async def analyze_mentor_ledger(req: LedgerRequest):
    try:
        return await run_in_threadpool(analyze_ledger, req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/v1/research/radar/{module}')
async def market_radar(module: str):
    if module not in {'market','news','signals','overseas'}:
        raise HTTPException(404,'Unknown radar module')
    return await run_in_threadpool(overview_radar.read,module)


@app.get("/api/v1/market/{symbol}/snapshot")
async def market_snapshot(symbol: str = Path(min_length=2, max_length=12)) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    try:
        return await run_in_threadpool(prediction_service.market_snapshot, normalized_symbol)
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/market/instruments", response_model=InstrumentCatalogResponse)
async def instruments() -> InstrumentCatalogResponse:
    snapshot = await run_in_threadpool(prediction_service.market_feed.catalog_snapshot)
    if not snapshot["dataTimestamp"] or not any(group["instruments"] for group in snapshot["exchanges"]):
        raise HTTPException(status_code=503, detail="Observed instrument catalog is still warming up")
    return InstrumentCatalogResponse.model_validate(snapshot)


@app.get("/api/v1/market/provider", response_model=ProviderStatusResponse)
async def provider_status() -> ProviderStatusResponse:
    status_reader = getattr(prediction_service.market_feed, "provider_status", None)
    if status_reader:
        status = await run_in_threadpool(status_reader)
    else:
        status = {
            "provider": "PUBLIC_HTTP",
            "configured": True,
            "connected": True,
            "lastEventAt": None,
            "fallbackActive": False,
            "message": "Public HTTP market source selected",
        }
    return ProviderStatusResponse.model_validate(status)


@app.get("/api/v1/market/{symbol}/microstructure")
async def market_microstructure(
    symbol: str = Path(min_length=2, max_length=12),
) -> dict[str, Any]:
    """Return TqSdk five-level depth and exchange ticks without synthetic fallback."""
    normalized_symbol = normalize_symbol(symbol)
    reader = getattr(prediction_service.market_feed, "microstructure_snapshot", None)
    if reader is None:
        raise HTTPException(status_code=503, detail="Real-time depth provider is unavailable")
    try:
        return await run_in_threadpool(reader, normalized_symbol)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/predictions/{symbol}", response_model=PredictionResponse)
async def predict(
    request: Request,
    symbol: str = Path(min_length=2, max_length=12),
    x_trace_id: str | None = Header(default=None),
) -> PredictionResponse:
    normalized_symbol = normalize_symbol(symbol)

    trace_id = (x_trace_id or request.state.trace_id)[:128]
    try:
        result = await run_in_threadpool(prediction_service.predict, normalized_symbol, trace_id)
        return PredictionResponse.model_validate(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("prediction_failed", extra={"symbol": normalized_symbol, "trace_id": trace_id})
        raise HTTPException(status_code=503, detail="Prediction service temporarily unavailable") from exc


@app.get("/api/v1/market/{symbol}/quote", response_model=QuoteResponse)
async def quote(symbol: str = Path(min_length=2, max_length=12)) -> QuoteResponse:
    normalized_symbol = normalize_symbol(symbol)
    try:
        snapshot = await run_in_threadpool(prediction_service.market_feed.snapshot, normalized_symbol)
        item = snapshot["quote"]
        if not item:
            raise MarketDataUnavailable(f"No observed quote for {normalized_symbol}")
        return QuoteResponse(
            symbol=normalized_symbol,
            display_name=item["displayName"],
            price=item["price"],
            change=item["change"],
            change_pct=item["changePct"],
            source=item["source"],
            data_status=item["dataStatus"],
            data_timestamp=item["dataTimestamp"],
        )
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/market/{symbol}/history", response_model=HistoryResponse)
async def history(
    symbol: str = Path(min_length=2, max_length=12),
    limit: int = 5000,
) -> HistoryResponse:
    normalized_symbol = normalize_symbol(symbol)
    safe_limit = min(max(limit, 1), 10000)
    try:
        # Only main/continuous symbols may use the local continuous cache. A
        # delivery contract must never be silently relabelled as a continuous series.
        clean_root: str | None = None
        if re.fullmatch(r"[A-Z]{1,4}M", normalized_symbol):
            clean_root = f"{normalized_symbol[:-1]}0"
        elif re.fullmatch(r"[A-Z]{1,4}0", normalized_symbol):
            clean_root = normalized_symbol

        hist_bars = history_manager.get_historical_bars(clean_root) if clean_root else []
        if clean_root and hist_bars and len(hist_bars) >= 20:
            selected_bars = hist_bars[-safe_limit:]
            metadata = history_manager.get_metadata(clean_root)
            points = []
            for idx, bar in enumerate(selected_bars):
                prev_bar = selected_bars[idx - 1] if idx > 0 else bar
                chg_pct = round(((bar.close / prev_bar.close) - 1.0) * 100.0, 2) if prev_bar.close > 0 else 0.0
                points.append({
                    "timestamp": bar.timestamp,
                    "price": bar.close,
                    "change_pct": chg_pct,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "volume": bar.volume,
                    "open_interest": bar.open_interest,
                })
            return HistoryResponse(
                symbol=normalized_symbol,
                series_symbol=clean_root,
                series_type="CONTINUOUS",
                source=metadata.get("source", "SINA_FUTURES_DAILY"),
                data_status="CACHED",
                data_timestamp=selected_bars[-1].timestamp,
                points=points,
            )

        # 降级读取实盘快照缓存
        snapshot = await run_in_threadpool(prediction_service.market_feed.snapshot, normalized_symbol)
        bars = snapshot["history"][-safe_limit:]
        if not bars:
            raise MarketDataUnavailable(f"No observed history for {normalized_symbol}")
        points = [
            {
                "timestamp": bar["timestamp"],
                "price": bar["price"],
                "change_pct": bar["changePct"],
                "open": bar.get("open"),
                "high": bar.get("high"),
                "low": bar.get("low"),
                "volume": bar.get("volume"),
                "open_interest": bar.get("openInterest"),
            }
            for bar in bars
        ]
        return HistoryResponse(
            symbol=normalized_symbol,
            series_symbol=normalized_symbol,
            series_type="CONTRACT" if re.search(r"\d{3,4}$", normalized_symbol) else "LIVE_SNAPSHOT",
            source=(snapshot.get("quote") or {}).get("source", "MARKET_FEED"),
            data_status="DEGRADED" if snapshot["quote"] and snapshot["quote"]["dataStatus"] == "DEGRADED" else "CACHED",
            data_timestamp=bars[-1]["timestamp"],
            points=points,
        )
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/market/{root_symbol}/term-structure", response_model=TermStructureResponse)
async def term_structure(root_symbol: str = Path(min_length=1, max_length=12)) -> TermStructureResponse:
    try:
        normalized_root = normalize_product_root(root_symbol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        snapshot = await run_in_threadpool(prediction_service.market_feed.term_snapshot, normalized_root)
        if not snapshot["contracts"] or not snapshot["dataTimestamp"]:
            raise MarketDataUnavailable("No trusted term structure contracts available")
        return TermStructureResponse(
            root_symbol=snapshot["rootSymbol"],
            data_status=snapshot["dataStatus"],
            data_timestamp=snapshot["dataTimestamp"],
            contracts=[
                {"contract": item["contract"], "maturity_date": item["maturityDate"], "price": item["price"]}
                for item in snapshot["contracts"]
            ],
        )
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/market/leads", response_model=LeadsResponse)
async def market_leads(
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> LeadsResponse:
    trace_id = (x_trace_id or getattr(request.state, "trace_id", "lead-scan"))[:128]
    try:
        result = await run_in_threadpool(prediction_service.discover_leads, trace_id)
        return LeadsResponse.model_validate(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("leads_discovery_failed", extra={"trace_id": trace_id})
        raise HTTPException(status_code=503, detail="Opportunity leads discovery failed") from exc


def load_execution_history(symbol: str, start_date: date | None = None,
                           end_date: date | None = None):
    """Shared historical execution evidence for backtests and paper replay."""
    dataset = backtest_data_provider.cached_replay(symbol, start_date, end_date)
    if dataset is not None:
        return dataset
    provider_resolver = getattr(prediction_service.market_feed, "provider_symbol", None)
    provider_symbol = provider_resolver(symbol) if provider_resolver else None
    if not provider_symbol:
        raise TqSdkBacktestUnavailable(
            f"{symbol} 所选区间暂无可用的真实交割合约历史数据，且天勤通道未就绪。"
            "请选择已备齐数据的品种和日期，或连接天勤后拉取数据。"
        )
    return backtest_data_provider.load(
        symbol, provider_symbol,
        n=max(25, int(os.getenv("TQSDK_BACKTEST_BARS", "2000"))),
        start_date=start_date, end_date=end_date,
    )


@app.post("/api/v1/backtest/run", response_model=BacktestResponse)
async def run_backtest_endpoint(req: BacktestRequest) -> BacktestResponse:
    normalized_symbol = normalize_symbol(req.symbol)
    if not BACKTEST_CAPACITY.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Backtest capacity is busy; retry after the current jobs finish",
            headers={"Retry-After": "5"},
        )

    def _execute():
        dataset = load_execution_history(normalized_symbol, req.start_date, req.end_date)
        bars = dataset.bars

        # 过滤起止日期
        filtered_bars = bars
        if req.start_date:
            filtered_bars = [b for b in filtered_bars if b.timestamp.date() >= req.start_date]
        if req.end_date:
            filtered_bars = [b for b in filtered_bars if b.timestamp.date() <= req.end_date]

        if len(filtered_bars) < 25:
            raise HTTPException(
                status_code=400,
                detail=f"有效回测K线不足25根 (当前筛选区间共 {len(filtered_bars)} 根)，请扩大回测时间范围",
            )

        first_date = filtered_bars[0].timestamp.date()
        last_date = filtered_bars[-1].timestamp.date()
        filtered_rolls = [
            event for event in dataset.roll_events
            if first_date <= event.execution_date <= last_date
        ]

        bt = QuantitativeBacktester(initial_capital=req.initial_capital, margin_rate=req.margin_rate)
        result = bt.run_backtest(
            klines=filtered_bars,
            signal_klines=[b for b in getattr(dataset, "signal_bars", dataset.bars)
                           if first_date <= b.timestamp.date() <= last_date],
            strategy=req.strategy,
            workflow=req.workflow_definition,
            symbol=normalized_symbol,
            fee_rate=req.fee_rate * req.cost_multiplier,
            slippage=req.slippage * req.cost_multiplier,
            max_pos_ratio=req.position_pct / 100.0 if req.position_pct > 1.0 else req.position_pct,
            stop_loss_atr=req.stop_loss_atr,
            take_profit_atr=req.take_profit_atr,
            margin_rate=req.margin_rate,
            leverage=req.leverage,
            include_roll_cost=True,
            roll_events=filtered_rolls,
            contract_specs={key: replace(spec, commission_per_lot=spec.commission_per_lot * req.cost_multiplier)
                            for key, spec in dataset.contract_specs.items()},
        )
        payload = result.to_dict()
        payload.update({
            "dataSource": dataset.source,
            "dataTimestamp": dataset.generated_at,
            "providerSymbol": dataset.provider_symbol,
            "costMultiplier": req.cost_multiplier,
        })
        return payload

    try:
        data = await run_in_threadpool(_execute)
        return BacktestResponse.model_validate(data)
    except HTTPException:
        raise
    except (MarketDataUnavailable, TqSdkBacktestUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("backtest_failed", extra={"symbol": normalized_symbol, "strategy": req.strategy})
        raise HTTPException(status_code=500, detail="Backtest execution failed") from exc
    finally:
        BACKTEST_CAPACITY.release()


@app.post('/internal/v1/simulation/strategy/evaluate')
async def simulation_strategy(request: StrategyRequest):
    return await run_in_threadpool(evaluate_paper_strategy, request)


@app.get('/internal/v1/simulation/live/{symbol}')
async def simulation_live_context(symbol: str):
    return await run_in_threadpool(live_context, prediction_service.market_feed, normalize_symbol(symbol))


@app.post("/internal/v1/workflows/validate")
async def validate_workflow_endpoint(request: WorkflowCheckRequest):
    return check_workflow(request.definition)


@app.post("/internal/v1/workflows/debug")
async def debug_workflow_endpoint(request: WorkflowDebugRequest):
    return await run_in_threadpool(debug_workflow,request,backtest_data_provider,normalize_symbol(request.symbol))


@app.get("/internal/v1/simulation/chart/{symbol}")
async def simulation_chart_context(symbol: str, as_of: datetime, limit: int = Query(240, ge=1, le=1000)):
    from .paper_chart import visible_bars
    if as_of.tzinfo is None:
        raise HTTPException(status_code=400, detail="回放时点必须包含时区")
    # Chart reads validated archives only; it must never fetch today's quotes
    # and masquerade them as information available in the past.
    dataset = await run_in_threadpool(backtest_data_provider.cached_replay, normalize_symbol(symbol))
    if dataset is None:
        raise HTTPException(status_code=503, detail="暂无已核验的日线背景档案")
    return {"source": dataset.source, "asOf": as_of,
            "bars": visible_bars(dataset.bars, as_of, limit)}


@app.get("/internal/v1/simulation/history/{symbol}")
async def simulation_history_dataset(
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Real, contract-tagged data used by the Java paper-trading ledger."""
    normalized_symbol = normalize_symbol(symbol)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    try:
        dataset = await run_in_threadpool(load_execution_history, normalized_symbol, start_date, end_date)
    except TqSdkBacktestUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    bars = [
        bar for bar in dataset.bars
        if (start_date is None or bar.timestamp.date() >= start_date)
        and (end_date is None or bar.timestamp.date() <= end_date)
    ]
    if len(bars) < 2:
        raise HTTPException(status_code=400, detail="Historical replay requires at least two real bars")
    first_date = bars[0].timestamp.date()
    last_date = bars[-1].timestamp.date()
    rolls = [
        event for event in dataset.roll_events
        if first_date <= event.execution_date <= last_date
    ]
    contracts = {bar.contract_symbol for bar in bars if bar.contract_symbol}
    contracts.update(event.from_contract for event in rolls)
    contracts.update(event.to_contract for event in rolls)
    return {
        "symbol": normalized_symbol,
        "providerSymbol": dataset.provider_symbol,
        "source": dataset.source,
        "generatedAt": dataset.generated_at,
        "signalBars": [
            {"timestamp": bar.timestamp, "contract": bar.contract_symbol,
             "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
             "volume": bar.volume, "openInterest": bar.open_interest}
            for bar in getattr(dataset, 'signal_bars', None) or dataset.bars
            if bar.timestamp.date() <= last_date
        ],
        "contextBars": [
            {"timestamp": bar.timestamp, "contract": bar.contract_symbol,
             "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
             "volume": bar.volume, "openInterest": bar.open_interest}
            for bar in dataset.bars if bar.timestamp.date() <= last_date
        ],
        "bars": [
            {
                "timestamp": bar.timestamp,
                "contract": bar.contract_symbol,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "openInterest": bar.open_interest,
            }
            for bar in bars
        ],
        "rollEvents": [
            {
                "executionDate": event.execution_date,
                "fromContract": event.from_contract,
                "toContract": event.to_contract,
                "oldOpen": event.old_open,
                "newOpen": event.new_open,
                "oldHigh": event.old_high,
                "oldLow": event.old_low,
                "newHigh": event.new_high,
                "newLow": event.new_low,
                "priceGap": event.price_gap,
                "priceGapPct": event.price_gap_pct,
            }
            for event in rolls
        ],
        "contractSpecs": {
            contract: {
                "contract": spec.contract,
                "volumeMultiple": spec.volume_multiple,
                "priceTick": spec.price_tick,
                "marginPerLot": spec.margin_per_lot,
                "commissionPerLot": spec.commission_per_lot,
            }
            for contract, spec in dataset.contract_specs.items()
            if contract in contracts
        },
    }


@app.get("/api/v1/backtest/presets")
async def backtest_presets() -> dict[str, Any]:
    strategies = [
        {
            "id": "BOLLINGER_REVERSAL",
            "name": "布林带自适应均值回归 (Bollinger Reversal)",
            "description": "布林带边界均值回归模型，配合中轨退出与 ATR 风险控制。历史表现必须按所选品种、区间和成本重新计算。",
            "recommendedParams": {
                "positionPct": 25.0,
                "stopLossAtr": 2.0,
                "takeProfitAtr": 2.5,
                "leverage": 1.8,
            },
            "bestFor": ["CJ0", "IF0", "M0", "SR0"],
        },
        {
            "id": "MOMENTUM_BREAKOUT",
            "name": "唐奇安通道放量动量突破 (Donchian Momentum)",
            "description": "20 日通道突破与成交量确认模型，使用 MA60 趋势过滤和 MA20 退出规则。结果对滑点与趋势行情敏感。",
            "recommendedParams": {
                "positionPct": 30.0,
                "stopLossAtr": 2.0,
                "takeProfitAtr": 4.0,
                "leverage": 2.0,
            },
            "bestFor": ["RB0", "CU0", "AL0", "ZN0"],
        },
        {
            "id": "HOLISTIC_14D",
            "name": "十四维全息融合策略 (Holistic 14D Fusion)",
            "description": "融合当前已提供数据的十四维评分与趋势过滤。文化维度按既定权重参与，但属于非实证参考，需与纯实证版本做样本外对照。",
            "recommendedParams": {
                "positionPct": 30.0,
                "stopLossAtr": 2.0,
                "takeProfitAtr": 4.0,
                "leverage": 2.2,
            },
            "bestFor": ["RB0", "CU0", "AU0", "AG0"],
        },
        {
            "id": "DUAL_THRUST",
            "name": "经典 Dual Thrust 趋势区间突破",
            "description": "使用前序区间计算上下轨并结合长期趋势过滤。信号在收盘确认，最早于下一交易日开盘成交。",
            "recommendedParams": {
                "positionPct": 30.0,
                "stopLossAtr": 2.0,
                "takeProfitAtr": 4.0,
                "leverage": 2.0,
            },
            "bestFor": ["CU0", "RB0", "SC0", "RU0"],
        },
        {
            "id": "ADAPTIVE_CTA",
            "name": "全天候自适应趋势CTA策略 (Adaptive CTA)",
            "description": "EMA、肯特纳通道与 ATR 吊灯退出组成的趋势模型。需关注长周期回撤、成本敏感性和分年度稳定性。",
            "recommendedParams": {
                "positionPct": 30.0,
                "stopLossAtr": 2.5,
                "takeProfitAtr": 4.5,
                "leverage": 2.2,
            },
            "bestFor": ["CU0", "RB0", "TA0", "MA0"],
        },
        {
            "id": "BUY_AND_HOLD",
            "name": "标的买入持有基准 (Buy & Hold Benchmark)",
            "description": "以无杠杆方式在回测起点全仓买入标的并持有至期末，用于评估量化策略相较于被动持有的超额收益阿尔法(Alpha)。",
            "recommendedParams": {
                "positionPct": 100.0,
                "stopLossAtr": 0.0,
                "takeProfitAtr": 0.0,
                "leverage": 1.0,
            },
        },
    ]

    symbols = [
        {"symbol": sym, "name": meta["name"], "exchange": meta["exchange"], "sector": meta["sector"]}
        for sym, meta in CORE_FUTURES_SYMBOLS.items()
    ]

    return {
        "strategies": strategies,
        "symbols": symbols,
        "defaultParams": {
            "initialCapital": 1000000.0,
            "positionPct": 30.0,
            "feeRate": 0.0001,
            "slippage": 1.0,
            "stopLossAtr": 2.0,
            "takeProfitAtr": 4.0,
            "marginRate": 0.12,
            "leverage": 2.0,
            "includeRollCost": True,
        },
    }


@app.get("/api/v1/data/history/status")
async def history_status() -> dict[str, Any]:
    return await run_in_threadpool(history_manager.get_status)


@app.get("/api/v1/data/replay/status")
async def replay_status() -> dict[str, Any]:
    items = await run_in_threadpool(backtest_data_provider.replay_catalog)
    for item in items:
        meta = CORE_FUTURES_SYMBOLS.get(item['symbol'], {})
        item['displayName'] = meta.get('name', item['symbol'])
    return {'symbols': items, 'totalSymbols': len(items),
            'source': 'OBSERVED_DELIVERY_CONTRACT',
            'message': '仅列出具有真实合约、规格和换月双腿的历史回放数据；公共主连历史不等于可成交回放数据。'}

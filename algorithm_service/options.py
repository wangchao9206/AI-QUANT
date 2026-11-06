"""Research-only option valuation. Prices are per underlying unit; no trading hooks."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

YEAR_SECONDS = 365 * 86400
SQRT_2PI = math.sqrt(2 * math.pi)


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def model_values(spot: float, strike: float, years: float, sigma: float, rate: float,
                 dividend: float, kind: str, underlying_type: str) -> dict:
    """Black-76 (future) / BSM (index), Greeks per unit, theta/day and vega/1 vol point."""
    sign = 1 if kind == "CALL" else -1
    carry = 0 if underlying_type == "FUTURE" else rate - dividend
    discount = math.exp(-rate * years)
    forward = spot * math.exp(carry * years)
    scale = math.exp((carry - rate) * years)
    vol_time = sigma * math.sqrt(years)
    d1 = (math.log(forward / strike) + 0.5 * vol_time * vol_time) / vol_time
    d2 = d1 - vol_time
    density = math.exp(-d1 * d1 / 2) / SQRT_2PI
    price = discount * sign * (forward * norm_cdf(sign * d1) - strike * norm_cdf(sign * d2))
    theta_year = (-spot * scale * density * sigma / (2 * math.sqrt(years))
                  - sign * (carry - rate) * spot * scale * norm_cdf(sign * d1)
                  - sign * rate * strike * discount * norm_cdf(sign * d2))
    return {"price": max(0.0, price), "delta": sign * scale * norm_cdf(sign * d1),
            "gamma": scale * density / (spot * vol_time),
            "theta": theta_year / 365, "vega": spot * scale * density * math.sqrt(years) / 100}


def implied_volatility(premium: float, spot: float, strike: float, years: float,
                       rate: float, dividend: float, kind: str, underlying_type: str) -> tuple[float | None, str | None]:
    carry = 0 if underlying_type == "FUTURE" else rate - dividend
    discount = math.exp(-rate * years)
    forward = spot * math.exp(carry * years)
    lower = discount * max((forward - strike) if kind == "CALL" else (strike - forward), 0)
    upper = discount * (forward if kind == "CALL" else strike)
    tolerance = max(1e-8, upper * 1e-10)
    if premium <= lower + tolerance or premium >= upper - tolerance:
        return None, "参考权利金不在欧式模型可求解的价格区间内。"
    low, high = 0.000001, 8.0
    if model_values(spot, strike, years, high, rate, dividend, kind, underlying_type)["price"] < premium:
        return None, "隐含波动率超过模型求解上限 800%。"
    for _ in range(90):
        mid = (low + high) / 2
        value = model_values(spot, strike, years, mid, rate, dividend, kind, underlying_type)["price"]
        if value > premium:
            high = mid
        else:
            low = mid
    return (low + high) / 2, None


def reference_price(row: dict) -> tuple[float | None, str | None, str | None]:
    if not row.get("dataTimestamp"):
        return None, None, "未取得真实报价时点。"
    bid, ask = row.get("bidPrice"), row.get("askPrice")
    if bid is not None and ask is not None:
        if bid > ask:
            return None, None, "买价高于卖价，报价交叉；暂不计算风险指标。"
        if row.get("bidVolume", 0) and row.get("askVolume", 0):
            return (bid + ask) / 2, "MID", None
    last = row.get("lastPrice")
    if last is not None and last > 0 and row.get("dataTimestamp"):
        return last, "LAST", "缺少有效双边盘口，使用最新成交价参考；可能并非当前可成交价格。"
    return None, None, "缺少可用的权利金报价。"


def analyze_contract(row: dict, chain: dict, underlying: dict, rate: float, dividend: float,
                     now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    premium, basis, note = reference_price(row)
    result = {"referencePrice": premium, "priceBasis": basis, "priceNote": note,
              "spread": None, "intrinsicValue": None, "timeValue": None,
              "iv": None, "delta": None, "gamma": None, "theta": None, "vega": None,
              "model": "BLACK_76" if chain["underlyingType"] == "FUTURE" else "BSM",
              "approximation": row.get("exerciseType") == "A", "valuationTimestamp": None,
              "riskStatus": "UNAVAILABLE", "riskReason": ""}
    if row.get("bidPrice") is not None and row.get("askPrice") is not None:
        result["spread"] = row["askPrice"] - row["bidPrice"]
    def unavailable(reason):
        result["riskReason"] = reason
        return result
    if premium is None:
        return unavailable(note)
    if row.get("exerciseType") not in ("A", "E"):
        return unavailable("未取得真实行权方式，暂不选择定价模型。")
    spot = underlying.get("lastPrice")
    if spot is None or spot <= 0 or not underlying.get("dataTimestamp") or not row.get("dataTimestamp"):
        return unavailable("缺少真实标的价格或报价时点。")
    option_time = datetime.fromisoformat(row["dataTimestamp"])
    underlying_time = datetime.fromisoformat(underlying["dataTimestamp"])
    if max(option_time, underlying_time) > now:
        return unavailable("报价时点晚于当前时间，暂不计算。")
    if abs((option_time - underlying_time).total_seconds()) > 300:
        return unavailable("期权与标的报价时点相差超过 5 分钟，暂不混合计算。")
    expiry = datetime.fromisoformat(row["expiry"])
    if expiry <= now:
        return unavailable("合约已到期，停止计算隐含波动率与 Greeks。")
    as_of = max(option_time, underlying_time)
    years = (expiry - as_of).total_seconds() / YEAR_SECONDS
    result["valuationTimestamp"] = as_of.isoformat()
    sign = 1 if row["optionClass"] == "CALL" else -1
    result["intrinsicValue"] = max(0.0, sign * (spot - row["strike"]))
    result["timeValue"] = premium - result["intrinsicValue"]
    iv, reason = implied_volatility(premium, spot, row["strike"], years, rate, dividend,
                                    row["optionClass"], chain["underlyingType"])
    if iv is None:
        return unavailable(reason)
    values = model_values(spot, row["strike"], years, iv, rate, dividend, row["optionClass"], chain["underlyingType"])
    result.update({k: values[k] for k in ("delta", "gamma", "theta", "vega")})
    result["iv"] = iv
    result["riskStatus"] = "EUROPEAN_APPROXIMATION" if row["exerciseType"] == "A" else "AVAILABLE"
    result["riskReason"] = ("美式期权的欧式模型参考，未计提前行权价值。" if row["exerciseType"] == "A" else "")
    return result


class ScenarioRequest(BaseModel):
    chain_id: str = Field(alias="chainId", min_length=1, max_length=250)
    symbol: str = Field(min_length=1, max_length=100)
    side: Literal["BUY", "SELL"] = "BUY"
    lots: int = Field(default=1, ge=1, le=10000, strict=True)


def expiry_scenario(row: dict, underlying: dict, request: ScenarioRequest) -> dict:
    premium, basis, note = reference_price(row)
    multiplier = row.get("volumeMultiple")
    spot = underlying.get("lastPrice")
    if premium is None or multiplier is None or multiplier <= 0 or spot is None or spot <= 0:
        raise HTTPException(409, "缺少真实参考权利金、标的价格或合约乘数，无法计算到期情景。")
    if datetime.fromisoformat(row["expiry"]) <= datetime.now(timezone.utc):
        raise HTTPException(409, "合约已到期，请选择未到期合约。")
    sign = 1 if request.side == "BUY" else -1
    call = row["optionClass"] == "CALL"
    strike = row["strike"]
    units = multiplier * request.lots
    breakeven = strike + premium if call else strike - premium
    # Include strike and breakeven, not only coarse equally spaced scenarios.
    high = max(spot * 1.5, strike * 1.2, max(0, breakeven) * 1.1)
    prices = sorted({0.0, strike, spot, *([breakeven] if breakeven >= 0 else []),
                     *[high * i / 60 for i in range(61)]})
    points = [{"underlyingPrice": p, "pnl": sign * (max(p - strike if call else strike - p, 0) - premium) * units} for p in prices]
    max_loss = premium * units if sign == 1 else (None if call else max(0, strike - premium) * units)
    max_profit = (None if call else (strike - premium) * units) if sign == 1 else premium * units
    return {"symbol": row["symbol"], "side": request.side, "lots": request.lots,
            "referencePrice": premium, "priceBasis": basis, "priceNote": note,
            "volumeMultiple": multiplier, "premiumAmount": premium * units,
            "breakeven": breakeven if breakeven >= 0 else None,
            "maxLoss": max_loss, "maxProfit": max_profit, "unlimitedLoss": sign == -1 and call,
            "unlimitedProfit": sign == 1 and call, "points": points,
            "dataTimestamp": row.get("dataTimestamp"), "underlyingTimestamp": underlying.get("dataTimestamp"),
            "note": "单腿到期内在价值情景；不含手续费、滑点、卖方保证金、提前行权或到期交割资金需求。曲线不是行情预测。"}


def router_for(feed):
    router = APIRouter(prefix="/api/v1/options", tags=["options"])

    def state():
        options = getattr(feed, "options", None)
        if options is None:
            raise HTTPException(503, "期权需要启用天勤行情源并配置相应数据权限。")
        return options

    def snapshot(chain_id):
        try:
            return state().chain_snapshot(chain_id, feed.connected, feed.freshness_seconds)
        except KeyError:
            raise HTTPException(404, "期权链不在真实目录中，请刷新目录后选择。")

    @router.get("/catalog")
    async def catalog():
        return await run_in_threadpool(state().catalog_snapshot, feed.connected, feed.configured)

    @router.get("/chain")
    async def chain(chainId: str = Query(min_length=1, max_length=250),
                    rate: float = Query(default=0.02, ge=-0.1, le=0.5),
                    dividend: float = Query(default=0.0, ge=0, le=0.5)):
        def read():
            data = snapshot(chainId)
            for row in data["contracts"]:
                row["risk"] = analyze_contract(row, data["chain"], data["underlying"], rate, dividend)
            data["assumptions"] = {"rate": rate, "dividend": dividend, "yearBasis": "ACT/365",
                                   "rateSource": "USER_ASSUMPTION", "greekUnits": "Delta/Gamma 每单位标的；Theta 每自然日；Vega 每 1 个波动率百分点"}
            return data
        return await run_in_threadpool(read)

    @router.get('/contracts')
    async def contracts(chainId: str = Query(min_length=1, max_length=250)):
        return await run_in_threadpool(snapshot, chainId)

    @router.get('/linked')
    async def linked(future: str = Query(min_length=2, max_length=12)):
        try:
            return await run_in_threadpool(feed.linked_options, future.strip().upper())
        except (AttributeError, ValueError) as error:
            raise HTTPException(503, str(error)) from error

    @router.get('/depth')
    async def depth(symbol: str = Query(min_length=3, max_length=100)):
        try:
            return await run_in_threadpool(feed.option_depth_snapshot, symbol)
        except (AttributeError, ValueError) as error:
            raise HTTPException(503, str(error)) from error

    @router.get('/chart')
    async def chart(symbol: str = Query(min_length=3, max_length=100), seconds: int = Query(60),
                    period: str | None = Query(None, max_length=10), limit: int = Query(600, ge=1, le=600)):
        from data.intraday_feed import period_key
        frequency = period if period is not None else seconds
        try:
            period_key(frequency)
        except ValueError as error:
            raise HTTPException(400, '不支持的 K 线周期。') from error
        try:
            return await run_in_threadpool(feed.option_chart_snapshot, symbol, frequency, limit)
        except (AttributeError, ValueError) as error:
            raise HTTPException(503, str(error)) from error

    @router.post("/scenario")
    async def scenario(body: ScenarioRequest):
        def read():
            data = snapshot(body.chain_id)
            row = next((r for r in data["contracts"] if r["symbol"] == body.symbol), None)
            if row is None:
                raise HTTPException(404, "合约不属于所选期权链。")
            result = expiry_scenario(row, data["underlying"], body)
            result["dataStatus"] = row["dataStatus"]
            result["underlyingStatus"] = data["underlying"]["dataStatus"]
            return result
        return await run_in_threadpool(read)

    return router

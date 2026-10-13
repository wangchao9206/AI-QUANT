"""
AI-QUANT 独立轻量级 Web 可视化服务 (Web App)
基于原生 Python http.server 构建，开箱即用，提供交互式看板与 REST API
"""
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from data.data_feed import FuturesDataFeed
from engines.fusion_engine import HolisticFusionEngine

logger = logging.getLogger("AI-QUANT.Web")

class QuantDashboardHandler(BaseHTTPRequestHandler):
    data_feed = FuturesDataFeed()
    engine = HolisticFusionEngine()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/dashboard":
            self._serve_html_dashboard()
        elif path == "/api/predict":
            self._serve_api_predict(query)
        elif path == "/api/quote":
            self._serve_api_quote(query)
        elif path == "/api/term-structure":
            self._serve_api_term_structure()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def _serve_api_predict(self, query):
        symbol = query.get("symbol", ["CJ2701"])[0]
        quote = self.data_feed.get_realtime_quote(symbol)
        klines = self.data_feed.get_historical_klines(symbol, days=45)
        decision = self.engine.evaluate_all({"symbol": symbol, "quote": quote, "klines": klines})

        payload = {
            "symbol": decision.symbol,
            "price": quote.price,
            "change_pct": quote.change_pct,
            "composite_score": decision.composite_score,
            "directional_resonance": decision.directional_resonance,
            "primary_signal": decision.primary_signal,
            "action_directive": decision.action_directive,
            "recommended_position_pct": decision.recommended_position_pct,
            "target_price_tp1": decision.target_price_tp1,
            "stop_loss_price": decision.stop_loss_price,
            "key_event_windows": decision.key_event_windows,
            "dimensions": {
                k: {
                    "name": v.dimension_name,
                    "score": v.score,
                    "direction": v.direction,
                    "confidence": v.confidence,
                    "summary": v.summary,
                    "recommendation": v.recommendation,
                    "key_metrics": v.key_metrics
                }
                for k, v in decision.dimension_results.items()
            }
        }
        self._send_json(payload)

    def _serve_api_quote(self, query):
        symbol = query.get("symbol", ["CJ2701"])[0]
        quote = self.data_feed.get_realtime_quote(symbol)
        self._send_json({
            "symbol": quote.symbol,
            "name": quote.name,
            "price": quote.price,
            "change": quote.change,
            "change_pct": quote.change_pct,
            "volume": quote.volume,
            "open_interest": quote.open_interest,
            "is_live": quote.is_live
        })

    def _serve_api_term_structure(self):
        data = self.data_feed.get_term_structure()
        res = {k: {"price": v.price, "change": v.change, "change_pct": v.change_pct, "volume": v.volume} for k, v in data.items()}
        self._send_json(res)

    def _serve_html_dashboard(self):
        quote = self.data_feed.get_realtime_quote("CJ2701")
        klines = self.data_feed.get_historical_klines("CJ2701", days=45)
        decision = self.engine.evaluate_all({"symbol": "CJ2701", "quote": quote, "klines": klines})

        cards = ""
        for k, v in decision.dimension_results.items():
            badge_color = "#ef4444" if v.direction == "BEARISH" else "#10b981" if v.direction == "BULLISH" else "#eab308"
            metrics_li = "".join(f"<li><b>{mk}:</b> {mv}</li>" for mk, mv in list(v.key_metrics.items())[:3])
            cards += f"""
            <div style="background:#1e293b; border:1px solid #334155; border-radius:8px; padding:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <h3 style="margin:0; font-size:16px;">{v.dimension_name}</h3>
                    <span style="background:{badge_color}33; color:{badge_color}; border:1px solid {badge_color}; padding:2px 8px; border-radius:4px; font-weight:bold;">{v.score:+.1f}</span>
                </div>
                <p style="font-size:13px; color:#94a3b8; line-height:1.4;">{v.summary}</p>
                <ul style="font-size:12px; color:#cbd5e1; padding-left:18px;">{metrics_li}</ul>
                <div style="background:#0f172a; padding:8px; border-radius:4px; font-size:12px; color:#f8fafc;">💡 <b>建议:</b> {v.recommendation}</div>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI-QUANT 十一维全息预测看板</title>
    <style>
        body {{ background:#0f172a; color:#f8fafc; font-family:system-ui, -apple-system, sans-serif; margin:0; padding:24px; }}
        .header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:16px; margin-bottom:20px; }}
        .badge-box {{ font-size:26px; font-weight:bold; color:#ef4444; }}
        .banner {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin-bottom:20px; }}
        .banner-item {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:12px; text-align:center; }}
        .banner-val {{ font-size:22px; font-weight:bold; color:#3b82f6; margin-top:6px; }}
        .grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:16px; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1 style="margin:0 0 6px 0;">AI-QUANT 十一维全息量化预测系统</h1>
            <span style="color:#94a3b8;">标的: {quote.name} (CJ2701) | 实时行情</span>
        </div>
        <div class="badge-box">
            {quote.price} 元/吨 ({quote.change_pct:+.2f}%)
        </div>
    </div>
    <div class="banner">
        <div class="banner-item"><div>主导交易信号</div><div class="banner-val" style="color:#ef4444;">{decision.primary_signal}</div></div>
        <div class="banner-item"><div>加权全息得分</div><div class="banner-val">{decision.composite_score:+.1f} / 100</div></div>
        <div class="banner-item"><div>多维共振度</div><div class="banner-val">{decision.directional_resonance*100:.1f}%</div></div>
        <div class="banner-item"><div>建议头寸比例</div><div class="banner-val">{decision.recommended_position_pct*100:+.1f}%</div></div>
        <div class="banner-item"><div>目标位 / 止损位</div><div class="banner-val" style="font-size:18px;">{decision.target_price_tp1:.0f} / {decision.stop_loss_price:.0f}</div></div>
    </div>
    <div class="grid">
        {cards}
    </div>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_json(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

def launch_web_server(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), QuantDashboardHandler)
    print(f"\n[AI-QUANT] Web 可视化看板服务已启动: http://localhost:{port}/")
    print(f"[AI-QUANT] REST API 接口: http://localhost:{port}/api/predict?symbol=CJ2701")
    print("[AI-QUANT] 按 Ctrl+C 可停止服务...\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[AI-QUANT] Web 服务已平稳停止。")

if __name__ == "__main__":
    launch_web_server(8080)

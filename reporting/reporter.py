"""
AI-QUANT 全景研报与可视化生成器 (Reporting & Visualization)
支持终端色彩看板、Markdown 深度研报、交互式 HTML Dashboard 与 JSON 序列化导出
"""
import os
import json
from datetime import datetime
from typing import Dict, Any

from config.settings import settings
from data.data_feed import MarketQuote
from engines.fusion_engine import FusionDecision

class ReportGenerator:
    """全景研报生成器"""

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or settings.reports_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def print_terminal_dashboard(self, decision: FusionDecision, quote: MarketQuote):
        """在终端输出精致的量化研报仪表盘"""
        sep = "=" * 80
        thin_sep = "-" * 80
        print("\n" + sep)
        print(f"  AI-QUANT 十一维全息预测量化系统 | 标的: {quote.name} ({decision.symbol})")
        print(f"  分析时间: {decision.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | 实时行情: {quote.price} 元/吨 ({quote.change_pct:+.2f}%)")
        print(sep)

        # 核心决策看板
        sig_color = "\033[91m" if "SELL" in decision.primary_signal else "\033[92m" if "BUY" in decision.primary_signal else "\033[93m"
        reset_color = "\033[0m"

        print(f"  【全息合成信号】: {sig_color}{decision.primary_signal}{reset_color} ({decision.action_directive})")
        print(f"  【加权综合得分】: {decision.composite_score:+.1f} / 100.0  |  【多维共振度】: {decision.directional_resonance*100:.1f}%")
        print(f"  【综合置信度】  : {decision.composite_confidence*100:.1f}%        |  【建议头寸】  : {decision.recommended_position_pct*100:+.1f}%")
        print(f"  【第一目标TP1】 : {decision.target_price_tp1:.0f} 元/吨       |  【防守止损位】: {decision.stop_loss_price:.0f} 元/吨")
        print(thin_sep)

        # 十一维度矩阵详情
        print(f"  {'维度名称':<18} | {'得分':<7} | {'方向':<8} | {'置信度':<7} | 核心结论与指标")
        print(thin_sep)

        for key, res in decision.dimension_results.items():
            dir_str = "看空" if res.direction == "BEARISH" else "看多" if res.direction == "BULLISH" else "中性"
            short_summary = res.summary[:38] + "..." if len(res.summary) > 38 else res.summary
            print(f"  {res.dimension_name:<16} | {res.score:>+6.1f} | {dir_str:<6} | {res.confidence*100:>5.1f}% | {short_summary}")

        print(thin_sep)
        print("  【关键时空演进窗口】:")
        for w in decision.key_event_windows:
            print(f"    - {w}")
        print(sep + "\n")

    def export_markdown_report(self, decision: FusionDecision, quote: MarketQuote) -> str:
        """导出详尽的 Markdown 研报"""
        filename = f"forecast_{decision.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = os.path.join(self.output_dir, filename)

        lines = [
            f"# {quote.name}（{decision.symbol}）十一维全息量化预测研报",
            f"",
            f"- **生成时间**：{decision.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **当前基准价**：{quote.price} 元/吨（{quote.change_pct:+.2f}%）",
            f"- **全息综合得分**：`{decision.composite_score:+.1f}` / 100.0",
            f"- **多空共振度**：`{decision.directional_resonance*100:.1f}%`",
            f"- **主导交易信号**：`{decision.primary_signal}`（{decision.action_directive}）",
            f"- **建议仓位**：`{decision.recommended_position_pct*100:+.1f}%`",
            f"- **风控参考**：第一目标位 `{decision.target_price_tp1:.0f}` | 终极目标位 `{decision.target_price_tp2:.0f}` | 移动防守止损 `{decision.stop_loss_price:.0f}`",
            f"",
            f"---",
            f"",
            f"## 一、十一维度量化评分汇总表",
            f"",
            f"| 维度序号 | 预测维度名称 | 得分 (-100~+100) | 方向 | 置信度 | 核心量化指标摘要 |",
            f"| :---: | :--- | :---: | :---: | :---: | :--- |",
        ]

        idx = 1
        for key, res in decision.dimension_results.items():
            metrics_str = "，".join(f"{k}: {v}" for k, v in list(res.key_metrics.items())[:3])
            dir_str = "**看空 (Bearish)**" if res.direction == "BEARISH" else "**看多 (Bullish)**" if res.direction == "BULLISH" else "中性"
            lines.append(f"| {idx} | {res.dimension_name} | `{res.score:+.1f}` | {dir_str} | {res.confidence*100:.1f}% | {metrics_str} |")
            idx += 1

        lines.extend([
            f"",
            f"---",
            f"",
            f"## 二、各维度深度研判解析",
            f""
        ])

        for key, res in decision.dimension_results.items():
            lines.extend([
                f"### {res.dimension_name}",
                f"- **研判摘要**：{res.summary}",
                f"- **实操建议**：{res.recommendation}",
                f"- **关键指标**：",
            ])
            for mk, mv in res.key_metrics.items():
                lines.append(f"  - `{mk}`: {mv}")
            if res.details:
                lines.append(f"- **模型明细**：")
                for dk, dv in res.details.items():
                    lines.append(f"  - `{dk}`: {dv}")
            lines.append("")

        lines.extend([
            f"---",
            f"",
            f"## 三、关键时空演进日历",
            f""
        ])
        for w in decision.key_event_windows:
            lines.append(f"- **{w}**")

        lines.extend([
            f"",
            f"---",
            f"*免责声明：本报告由 AI-QUANT 多维量化系统自动生成，模型涵盖气象、动能、量化指标及传统数术哲学模型，数据仅供研究参考，不构成直接投资买卖建议。市场有风险，投资需谨慎。*"
        ])

        content = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def export_json(self, decision: FusionDecision) -> str:
        """导出结构化 JSON 数据"""
        filename = f"forecast_{decision.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.output_dir, filename)

        data = {
            "symbol": decision.symbol,
            "timestamp": decision.timestamp.isoformat(),
            "composite_score": decision.composite_score,
            "directional_resonance": decision.directional_resonance,
            "composite_confidence": decision.composite_confidence,
            "primary_signal": decision.primary_signal,
            "action_directive": decision.action_directive,
            "recommended_position_pct": decision.recommended_position_pct,
            "target_price_tp1": decision.target_price_tp1,
            "target_price_tp2": decision.target_price_tp2,
            "stop_loss_price": decision.stop_loss_price,
            "key_event_windows": decision.key_event_windows,
            "dimension_scores": {
                k: {
                    "name": v.dimension_name,
                    "score": v.score,
                    "direction": v.direction,
                    "confidence": v.confidence,
                    "summary": v.summary,
                    "key_metrics": v.key_metrics
                }
                for k, v in decision.dimension_results.items()
            }
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath

    def export_html_dashboard(self, decision: FusionDecision, quote: MarketQuote) -> str:
        """导出美观的交互式 HTML 仪表盘"""
        filename = f"forecast_{decision.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(self.output_dir, filename)

        cards_html = ""
        for k, res in decision.dimension_results.items():
            badge_class = "badge-bearish" if res.direction == "BEARISH" else "badge-bullish" if res.direction == "BULLISH" else "badge-neutral"
            metrics_html = "".join(f"<li><strong>{mk}:</strong> {mv}</li>" for mk, mv in list(res.key_metrics.items())[:4])
            cards_html += f"""
            <div class="card">
                <div class="card-header">
                    <h3>{res.dimension_name}</h3>
                    <span class="badge {badge_class}">{res.score:+.1f}</span>
                </div>
                <p class="summary">{res.summary}</p>
                <ul class="metrics">{metrics_html}</ul>
                <div class="recommendation"><strong>建议:</strong> {res.recommendation}</div>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI-QUANT 十一维全息预测仪表盘 - {quote.name}</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --danger: #ef4444;
            --success: #10b981;
            --accent: #3b82f6;
            --border: #334155;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        .price-badge {{
            font-size: 28px;
            font-weight: bold;
            color: var(--danger);
        }}
        .banner {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .banner-item {{
            background: var(--card-bg);
            padding: 16px;
            border-radius: 8px;
            border: 1px solid var(--border);
            text-align: center;
        }}
        .banner-value {{
            font-size: 24px;
            font-weight: bold;
            color: var(--accent);
            margin-top: 8px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 16px;
        }}
        .card {{
            background: var(--card-bg);
            border-radius: 8px;
            padding: 16px;
            border: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 8px;
            margin-bottom: 12px;
        }}
        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 14px;
        }}
        .badge-bearish {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); }}
        .badge-bullish {{ background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid var(--success); }}
        .summary {{ font-size: 14px; color: var(--text-muted); line-height: 1.5; }}
        .metrics {{ font-size: 13px; color: #cbd5e1; padding-left: 20px; margin: 10px 0; }}
        .recommendation {{ background: rgba(0,0,0,0.25); padding: 8px; border-radius: 4px; font-size: 12px; color: #f1f5f9; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>AI-QUANT 十一维全息预测系统</h1>
            <p style="color: var(--text-muted)">标的: {quote.name} ({decision.symbol}) | 时间: {decision.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <div class="price-badge">
            {quote.price} 元/吨 ({quote.change_pct:+.2f}%)
        </div>
    </div>

    <div class="banner">
        <div class="banner-item">
            <div>综合决策信号</div>
            <div class="banner-value" style="color: var(--danger)">{decision.primary_signal}</div>
        </div>
        <div class="banner-item">
            <div>加权全息得分</div>
            <div class="banner-value">{decision.composite_score:+.1f} / 100</div>
        </div>
        <div class="banner-item">
            <div>多维共振度</div>
            <div class="banner-value">{decision.directional_resonance*100:.1f}%</div>
        </div>
        <div class="banner-item">
            <div>建议头寸比例</div>
            <div class="banner-value">{decision.recommended_position_pct*100:+.1f}%</div>
        </div>
        <div class="banner-item">
            <div>第一目标位 / 止损位</div>
            <div class="banner-value" style="font-size: 18px">{decision.target_price_tp1:.0f} / {decision.stop_loss_price:.0f}</div>
        </div>
    </div>

    <div class="grid">
        {cards_html}
    </div>
</body>
</html>"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        return filepath

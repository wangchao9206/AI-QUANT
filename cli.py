"""
AI-QUANT 交互式命令行控制台 (CLI)
支持行情查询、十一维全息预测、全品种期限结构、历史回测与多格式研报生成
"""
import sys
import argparse
from datetime import datetime

from data.data_feed import FuturesDataFeed
from engines.fusion_engine import HolisticFusionEngine
from reporting.reporter import ReportGenerator
from backtesting.backtester import QuantitativeBacktester

def parse_args():
    parser = argparse.ArgumentParser(description="AI-QUANT 十一维全息量化预测与交易系统")
    parser.add_argument("--symbol", type=str, default="CJ2701", help="目标期货合约代码 (默认: CJ2701)")
    parser.add_argument("--term-structure", action="store_true", help="分析红枣期货全月期限结构")
    parser.add_argument("--backtest", action="store_true", help="执行策略历史多维回测")
    parser.add_argument("--no-export", action="store_true", help="不自动导出本地 Markdown/HTML/JSON 研报")
    parser.add_argument("--web", action="store_true", help="启动交互式 Web 可视化看板服务")
    parser.add_argument("--port", type=int, default=8080, help="Web 看板端口 (默认: 8080)")
    return parser.parse_args()

def run_cli():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = parse_args()

    if args.web:
        from web_app import launch_web_server
        launch_web_server(port=args.port)
        return

    data_feed = FuturesDataFeed()
    fusion_engine = HolisticFusionEngine()
    reporter = ReportGenerator()

    # 1. 期限结构模式
    if args.term_structure:
        print("\n=== 正在获取红枣期货全月合约期限结构 ===")
        term_data = data_feed.get_term_structure()
        print(f"{'合约代码':<10} | {'最新价 (元/吨)':<14} | {'涨跌额':<8} | {'涨跌幅':<8} | {'成交量 (手)':<10}")
        print("-" * 65)
        for code, q in term_data.items():
            print(f"{code:<10} | {q.price:<14.1f} | {q.change:>+7.1f} | {q.change_pct:>+7.2f}% | {q.volume:>10,}")
        print("-" * 65 + "\n")
        return

    # 2. 回测模式
    if args.backtest:
        print(f"\n=== 正在执行标的 {args.symbol} 的十一维策略历史回测 ===")
        klines = data_feed.get_historical_klines(args.symbol, days=90)
        backtester = QuantitativeBacktester()
        res = backtester.run_backtest(klines)
        print("-" * 50)
        print(f"  总交易次数   : {res.total_trades}")
        print(f"  胜率 (Win Rate): {res.win_rate}%")
        print(f"  盈亏比 (P/L) : {res.profit_loss_ratio}")
        print(f"  累计收益率   : {res.total_return_pct:+0.2f}%")
        print(f"  最大回撤     : {res.max_drawdown_pct:.2f}%")
        print(f"  夏普比率估算 : {res.sharpe_ratio}")
        print("-" * 50 + "\n")
        return

    # 3. 标准十一维全息预测分析
    print(f"\n>>> 正在接入 {args.symbol} 实时盘面与产区微气象、六爻奇门时空数据...")
    quote = data_feed.get_realtime_quote(args.symbol)
    klines = data_feed.get_historical_klines(args.symbol, days=45)

    context = {
        "symbol": args.symbol,
        "quote": quote,
        "klines": klines,
        "analysis_time": datetime.now()
    }

    # 执行全景合成
    decision = fusion_engine.evaluate_all(context)

    # 终端看板展示
    reporter.print_terminal_dashboard(decision, quote)

    # 导出研报与看板
    if not args.no_export:
        md_path = reporter.export_markdown_report(decision, quote)
        html_path = reporter.export_html_dashboard(decision, quote)
        json_path = reporter.export_json(decision)
        print(f" [OK] Markdown 研报已生成: {md_path}")
        print(f" [OK] 交互式 HTML 看板已生成: {html_path}")
        print(f" [OK] JSON 数据接口已生成: {json_path}\n")

if __name__ == "__main__":
    run_cli()

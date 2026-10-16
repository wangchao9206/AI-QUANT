# -*- coding: utf-8 -*-
"""
AI-QUANT 全量历史行情数据同步与持久化脚本
使用方式:
  python scripts/download_history.py --all
  python scripts/download_history.py --symbols CJ0,AP0,RB0,LC0,IF0
  python scripts/download_history.py --status
"""
import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.history_manager import HistoryManager, CORE_FUTURES_SYMBOLS


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="AI-QUANT 期货全量历史数据下载器")
    parser.add_argument("--all", action="store_true", help="下载并同步全部核心主力期货品种的历史数据")
    parser.add_argument("--symbols", type=str, default="", help="指定逗号分隔的品种代码，如 CJ0,AP0,RB0")
    parser.add_argument("--status", action="store_true", help="查看本地历史数据持久化现状")
    args = parser.parse_args()

    manager = HistoryManager()

    if args.status:
        print("\n" + "=" * 80)
        print("  AI-QUANT 本地历史数据仓库存储概览 (data/history)")
        print("=" * 80)
        total_bars = 0
        existing_count = 0
        print(f"{'代码':<8} | {'品种名称':<14} | {'板块':<10} | {'历史K线数':<10} | {'起止日期区间':<25} | {'文件大小'}")
        print("-" * 80)
        for sym, meta in CORE_FUTURES_SYMBOLS.items():
            json_file = manager.cache_dir / f"{sym}_daily.json"
            csv_file = manager.cache_dir / f"{sym}_daily.csv"
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    count = data.get("total_bars", 0)
                    start = data.get("start_date") or "-"
                    end = data.get("end_date") or "-"
                    date_range = f"{start} ~ {end}"
                    size_kb = f"{csv_file.stat().st_size / 1024:.1f} KB" if csv_file.exists() else "-"
                    print(f"{sym:<8} | {meta['name']:<14} | {meta['sector']:<10} | {count:<10} | {date_range:<25} | {size_kb}")
                    total_bars += count
                    existing_count += 1
                except Exception:
                    print(f"{sym:<8} | {meta['name']:<14} | {meta['sector']:<10} | [读取异常]")
            else:
                print(f"{sym:<8} | {meta['name']:<14} | {meta['sector']:<10} | {'[未下载]':<10} | {'-':<25} | -")

        print("-" * 80)
        print(f"统计：已就绪品种: {existing_count}/{len(CORE_FUTURES_SYMBOLS)} | 总历史 K 线记录: {total_bars:,} 条\n")
        return

    # 确定目标品种
    if args.all:
        target_list = list(CORE_FUTURES_SYMBOLS.keys())
    elif args.symbols:
        target_list = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        # 默认同步首批代表性主力品种
        target_list = ["CJ0", "AP0", "RB0", "LC0", "IF0", "AU0", "TA0", "M0", "CU0", "I0"]

    print("\n" + "=" * 80)
    print(f"  正在启动 AI-QUANT 历史数据采集与持久化程序 (目标品种数: {len(target_list)})")
    print("=" * 80)

    results = manager.download_all(target_list)

    success_count = sum(1 for r in results.values() if r.get("status") == "SUCCESS")
    total_bars = sum(r.get("bars_count", 0) for r in results.values() if r.get("status") == "SUCCESS")

    print("\n" + "-" * 80)
    print(f"  同步结果汇报: 成功 {success_count}/{len(target_list)} 个品种 | 累计持久化 {total_bars:,} 根日K线")
    print(f"  存储目录: {manager.cache_dir.resolve()}")
    print("-" * 80 + "\n")


if __name__ == "__main__":
    main()

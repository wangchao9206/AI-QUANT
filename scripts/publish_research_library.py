"""Publish existing research evidence; never run a strategy or modify frozen inputs."""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIES = [
    dict(id="fu-regime", folder="fu-regime-2026-10-27", title="燃油 · 第二轮状态修正", badge="事后探索", subtitle="把失败变成下一轮的问题", count=116, report="fu-focused-2026-10-27.md", protocol="2026-10-27-fu-regime-iteration.md", conclusion="加入状态退出后仍未通过后续窗口。固定 RANGE_REVERSION / REGIME_EXIT，仅作新数据诊断观察。", scope="SHFE.FU · 2019—2026 · 18 个修正配置", defaultFamily="RANGE_REVERSION"),
    dict(id="fu-mechanisms", folder="fu-focused-2026-10-27-r2", title="燃油 · 第一轮机制对照", badge="历史检验", subtitle="16 类机制，留下全部失败", count=398, report="fu-focused-2026-10-27.md", protocol="2026-10-27-fu-focused-research.md", conclusion="三个开发期固定的候选均未通过全部门槛。邻近参数、成本压力和亏损记录全部保留。", scope="SHFE.FU · 1894 根日线 · 144 个配置", defaultFamily="GAP_FADE"),
    dict(id="daily-screen", folder="independent-daily-2026-10-27", title="多品种 · 真实日线初筛", badge="历史初筛", subtitle="先验证，再谈资金规模", count=876, report="independent-daily-2026-10-27.md", protocol="2026-10-27-independent-daily-research.md", conclusion="开发期成交数门槛未通过，2026 留出窗口未打开。39 个独立账户的结果不能当作一个组合。", scope="39 个合格品种 · 3 类机制 · 3 档资金", defaultFamily="PULLBACK"),
]


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def packed(value):
    return zlib.compress(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(), 6)


def metadata(study, key):
    fields = (["stage", "family", "symbol", "capital", "cost", "period", "stop"] if study == "daily-screen" else
              ["stage", "family", "repair", "scale", "capital", "cost", "direction", "delay"] if study == "fu-mechanisms" else
              ["stage", "family", "mode", "scale", "capital", "cost"])
    return dict(zip(fields, key))


def publish(root: Path = ROOT, output: Path | None = None):
    output = output or root / "docs/research/published"
    inputs = [Path(__file__)]
    for spec in STUDIES:
        inputs.extend(sorted(p for p in (root / "docs/research/data" / spec["folder"]).iterdir()
                             if p.is_file() and p.name != "shadow-state.json" and not p.name.endswith(".lock")))
        inputs.extend([root / "docs/research" / spec["report"], root / "docs/plans" / spec["protocol"]])
    digest = hashlib.sha256()
    for path in inputs:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    revision = digest.hexdigest()[:20]
    generation = output / "generations" / revision
    catalog = dict(revision=revision, date="2026-10-27", qualifiedCount=0, totalRuns=sum(s["count"] for s in STUDIES), studies=[])
    def publish_catalog(value):
        output.mkdir(parents=True, exist_ok=True)
        temp = output / ("catalog-" + uuid.uuid4().hex + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temp.replace(output / "catalog.json")
    final_generation = generation
    if (final_generation / "catalog.json").is_file():
        existing = read(final_generation / "catalog.json")
        publish_catalog(existing)
        return existing
    generation = output / "generations" / (".building-" + revision + "-" + uuid.uuid4().hex)
    for spec in STUDIES:
        source = root / "docs/research/data" / spec["folder"]
        target = generation / spec["id"]
        target.mkdir(parents=True, exist_ok=True)
        assets = []
        candidates = [(p, p.name) for p in sorted(source.iterdir()) if p.is_file() and p.suffix in {".json", ".csv", ".png", ".gz"}
                      and p.name != "shadow-state.json"]
        candidates += [(root / "docs/research" / spec["report"], "report.md"), (root / "docs/plans" / spec["protocol"], "protocol.md")]
        if spec["id"] == "fu-regime":
            candidates.append((root / "docs/research/fu-research-journal.md", "research-journal.md"))
        import re
        report_path = root / "docs/research" / spec["report"]
        report = report_path.read_text(encoding="utf-8")
        raw_links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", report)
        known = {p.resolve() for other in STUDIES for p in (root / "docs/research/data" / other["folder"]).iterdir() if p.is_file() and p.suffix in {".json", ".csv", ".png", ".gz"} and p.name != "shadow-state.json"}
        for raw in raw_links:
            resolved = (report_path.parent / raw).resolve()
            if resolved in known and resolved not in {p.resolve() for p, _ in candidates}:
                candidates.append((resolved, "related-" + resolved.parent.name + "-" + resolved.name))
        for path, name in candidates:
            body = path.read_bytes()
            (target / name).write_bytes(body)
            assets.append(dict(name=name, size=len(body), sha256=hashlib.sha256(body).hexdigest()))
        results = read(source / "results.json")
        comparisons = []
        db = target / "runs.sqlite"
        if db.exists():
            db.unlink()
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, stage TEXT, family TEXT, symbol TEXT, capital INTEGER, cost REAL, meta TEXT, metrics TEXT, payload BLOB)")
        runs = json.loads(gzip.decompress((source / "full-ledgers.json.gz").read_bytes()))
        if len(runs) != spec["count"]:
            raise ValueError(f"{spec['id']}: unexpected scenario count")
        for index, item in enumerate(runs, 1):
            meta = metadata(spec["id"], item["key"])
            result = item.get("result", item)
            include = False
            if spec["id"] == "fu-regime":
                include = meta["family"] == "RANGE_REVERSION" and meta["scale"] == 1 and meta["capital"] == 1000000 and meta["cost"] in (1, 2)
            elif spec["id"] == "fu-mechanisms":
                include = any(meta["family"] == x["family"] and meta["repair"] == x["repair"] for x in results["selected"]) and meta["scale"] == 1 and meta["capital"] == 1000000 and meta["cost"] in (1, 2) and meta["direction"] == "BOTH" and not meta["delay"]
            if include:
                comparisons.append(dict(id=index, **meta, metrics=result["metrics"]))
            conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?)", (index, meta["stage"], meta["family"], meta.get("symbol", "FU0"), meta["capital"], meta["cost"], json.dumps(meta), json.dumps(result["metrics"], allow_nan=False), packed({k: result.get(k, []) for k in ("curve", "trades", "decisions")})))
        conn.execute("CREATE INDEX filters ON runs(stage,family,capital,cost,symbol)")
        conn.commit()
        filters = {field: [r[0] for r in conn.execute(f"SELECT DISTINCT {field} FROM runs ORDER BY {field}")] for field in ("stage", "family", "symbol", "capital", "cost")}
        conn.close()
        # Resolve only known published files; the browser never opens local paths.
        links = {}
        import re
        report_path = root / "docs/research" / spec["report"]
        for raw in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", report):
            if raw.startswith(("https://", "http://", "#")):
                continue
            resolved = (report_path.parent / raw).resolve()
            if resolved == (root / "docs/research/data/fu-regime-2026-10-27/shadow-state.json").resolve():
                links[raw] = "@observation"
            for path, name in candidates:
                if path.resolve() == resolved:
                    links[raw] = name
        summary = {k: v for k, v in spec.items() if k not in {"folder", "report", "protocol"}}
        detail = dict(**summary, revision=revision, results=results, comparisons=comparisons, assets=assets, filters=filters, report=report, reportLinks=links,
                      journal=read(source / "failure-journal.json") if (source / "failure-journal.json").exists() else [],
                      observation=spec["id"] == "fu-regime")
        (target / "study.json").write_text(json.dumps(detail, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        catalog["studies"].append(summary)
    (generation / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    generation.rename(final_generation)
    publish_catalog(catalog)
    return catalog


if __name__ == "__main__":
    result = publish()
    print(json.dumps(dict(revision=result["revision"], studies=len(result["studies"]), runs=result["totalRuns"])))

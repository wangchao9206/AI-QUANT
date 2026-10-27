"""Read-only publication API. No market queries, strategy runs or account writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import zlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = Path(os.getenv("RESEARCH_PUBLISHED_ROOT", str(ROOT / "docs/research/published")))
OBSERVATION_PATH = Path(os.getenv("RESEARCH_OBSERVATION_PATH", str(ROOT / "docs/research/data/fu-regime-2026-10-27/shadow-state.json")))
router = APIRouter(prefix="/api/v1/research/studies", tags=["Research library"])


def read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "研究资料暂不可用，请稍后重试") from exc


def study_path(study_id, revision):
    catalog = read(PUBLISHED_ROOT / "catalog.json")
    if study_id not in {s["id"] for s in catalog["studies"]}:
        raise HTTPException(404, "研究批次不存在")
    version = revision or catalog["revision"]
    if not re.fullmatch(r"[0-9a-f]{20}", version):
        raise HTTPException(404, "研究版本不存在")
    path = PUBLISHED_ROOT / "generations" / version / study_id
    if not (path / "study.json").is_file():
        raise HTTPException(404, "研究版本不存在")
    return path


def connect(path):
    conn = sqlite3.connect((path / "runs.sqlite").resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("")
def catalog():
    return read(PUBLISHED_ROOT / "catalog.json")


@router.get("/{study_id}")
def detail(study_id: str, revision: str | None = None):
    return read(study_path(study_id, revision) / "study.json")


@router.get("/{study_id}/runs")
def runs(study_id: str, revision: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
         stage: str | None = None, family: str | None = None, symbol: str | None = None, capital: int | None = None, cost: float | None = None):
    path = study_path(study_id, revision)
    filters = {"stage": stage, "family": family, "symbol": symbol, "capital": capital, "cost": cost}
    active = {key: value for key, value in filters.items() if value is not None}
    where = " WHERE " + " AND ".join(f"{key}=?" for key in active) if active else ""
    conn = connect(path)
    try:
        total = conn.execute("SELECT count(*) FROM runs" + where, list(active.values())).fetchone()[0]
        rows = conn.execute("SELECT id,meta,metrics FROM runs" + where + " ORDER BY id LIMIT ? OFFSET ?", [*active.values(), page_size, (page - 1) * page_size]).fetchall()
        return dict(total=total, page=page, pageSize=page_size, items=[dict(id=row["id"], **json.loads(row["meta"]), metrics=json.loads(row["metrics"])) for row in rows])
    finally:
        conn.close()


@router.get("/{study_id}/runs/{run_id}")
def run(study_id: str, run_id: int, revision: str | None = None):
    conn = connect(study_path(study_id, revision))
    try:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "场景不存在")
        return dict(id=row["id"], **json.loads(row["meta"]), metrics=json.loads(row["metrics"]), **json.loads(zlib.decompress(row["payload"])))
    finally:
        conn.close()


@router.get("/{study_id}/assets/{name}")
def asset(study_id: str, name: str, revision: str | None = None, download: bool = True):
    path = study_path(study_id, revision)
    allowed = {a["name"] for a in read(path / "study.json")["assets"]}
    if name not in allowed or Path(name).name != name:
        raise HTTPException(404, "文件不存在")
    return FileResponse(path / name, filename=name if download else None, headers={"X-Content-Type-Options": "nosniff"})


@router.get("/{study_id}/observation")
def observation(study_id: str, download: bool = False):
    if study_id != "fu-regime":
        raise HTTPException(404, "此批次没有新数据观察账本")
    state = read(OBSERVATION_PATH)
    digest = hashlib.sha256(json.dumps(state["config"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if digest != state["configHash"] or state.get("ordersSubmittedToBroker") != 0:
        raise HTTPException(503, "观察账本完整性检查未通过")
    if download:
        return JSONResponse(state, headers={"Content-Disposition": 'attachment; filename="fu-observation.json"', "Cache-Control": "no-store"})
    return dict(state=state, automaticUpdates=False, tradingEnabled=False, message="按需推进的完成日线诊断账本；刷新只读取已保存记录，不查询行情或下单。")

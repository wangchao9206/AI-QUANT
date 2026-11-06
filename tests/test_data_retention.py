from datetime import datetime,timezone
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('data_retention',ROOT/'scripts/data_retention.py')
retention=importlib.util.module_from_spec(spec);spec.loader.exec_module(retention)


def test_retention_scope_cannot_touch_accounts_or_frozen_business_evidence():
    assert set(retention.POLICIES)=={'quotes','terms','operations','audit'}
    for key in retention.POLICIES:
        table,days,cutoff,condition=retention.cutoff_policy(key,now=datetime(2026,11,6,tzinfo=timezone.utc))
        assert days>=30 and 'created_at' in condition
        assert not table.startswith(('paper_trading.','chanlun.'))
        with pytest.raises(ValueError):retention.cutoff_policy(key,0)
    assert 'exists(select' in retention.cutoff_policy('quotes')[3]
    assert 'exists(select' in retention.cutoff_policy('terms')[3]


def test_private_archives_cannot_be_created_in_the_git_workspace_or_nonempty_folder(tmp_path):
    with pytest.raises(ValueError):retention.secure_directory(ROOT/'.test-tmp/would-leak')
    (tmp_path/'unrelated.txt').write_text('other files',encoding='utf-8')
    with pytest.raises(ValueError):retention.secure_directory(tmp_path)


def test_container_identifiers_cannot_inject_commands():
    with pytest.raises(ValueError):retention.Postgres('postgres; echo secret')

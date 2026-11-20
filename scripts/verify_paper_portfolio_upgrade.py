"""Rehearse the V16 migration on a local backup inside the disposable test container."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = 'ai-quant-portfolio-test-20261118'
DATABASE = 'paper_upgrade'


def sql(value, database=DATABASE):
    result = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-U', 'paper_test',
        '-d', database, '-At', '-v', 'ON_ERROR_STOP=1'], input=value.encode(), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-1800:])
    return result.stdout.decode().strip()


def main():
    backups = sorted((ROOT / '.test-tmp/backups').glob('paper-before-v16-*.dump'))
    assert backups, 'Create a ledger backup first'
    assert sql('select current_database()', 'paper_test') == 'paper_test'
    sql('create database paper_upgrade', 'paper_test')
    with backups[-1].open('rb') as source:
        restored = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'pg_restore', '-U', 'paper_test',
            '-d', DATABASE, '--no-owner', '--no-acl', '--exit-on-error'], stdin=source, capture_output=True)
    if restored.returncode:
        raise RuntimeError(restored.stderr.decode(errors='replace')[-1800:])
    fingerprint = """
      select json_build_object(
        'sessions',(select count(*) from paper_trading.paper_session),
        'cash',(select coalesce(sum(cash_balance),0) from paper_trading.paper_session),
        'equity',(select coalesce(sum(equity),0) from paper_trading.paper_session),
        'positions',(select count(*) from paper_trading.paper_position),
        'orders',(select count(*) from paper_trading.paper_order),
        'fills',(select count(*) from paper_trading.paper_fill),
        'notes',(select count(*) from paper_trading.paper_fill_note))::text
    """
    before = json.loads(sql(fingerprint))
    migration = (ROOT / 'backend/paper-trading-service/src/main/resources/db/migration/V16__multi_instrument_accounts.sql').read_text(encoding='utf-8')
    sql('set search_path=paper_trading;\n' + migration)
    assert before == json.loads(sql(fingerprint)), 'V16 changed existing ledger rows or funds'
    assert sql("select count(*) from pg_policies where schemaname='paper_trading' and tablename='paper_portfolio_position'") == '1'
    assert sql('select count(*) from paper_trading.paper_session where multi_instrument') == '0'
    result = {'status': 'PASS', 'backup': backups[-1].name,
              'checks': ['archive-restores', 'v16-applies-to-existing-data', 'funds-preserved',
                         'positions-orders-fills-notes-preserved', 'no-automatic-account-upgrade', 'new-table-rls']}
    (ROOT / '.test-tmp/portfolio-upgrade-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('PASS: real ledger backup restores; V16 preserves all existing funds and record counts.')


if __name__ == '__main__':
    main()

"""Back up the existing paper schema before a migration; never alter the database."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import subprocess
import argparse
from compose import command, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',choices=['v16','v17'],default='v16')
    options=parser.parse_args()
    config = {}
    for line in (ROOT / 'infrastructure/.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip().strip('\"\'')
    user, database = config.get('POSTGRES_USER', 'aiquant'), config.get('POSTGRES_DB', 'aiquant')
    target = ROOT / '.test-tmp/backups' / ('paper-before-' + options.before + '-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.dump')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as output:
        subprocess.run(command('light', ['exec', '-T', 'postgres', 'pg_dump', '-U', user,
            '-d', database, '--format=custom', '--schema=paper_trading']), stdout=output, check=True)
    assert target.stat().st_size > 1000, 'Backup archive is unexpectedly small'
    with target.open('rb') as source:
        listing = subprocess.run(command('light', ['exec', '-T', 'postgres', 'pg_restore', '--list']),
                                 stdin=source, capture_output=True, check=True).stdout.decode('utf-8')
    for table in ['paper_session', 'paper_position', 'paper_fill', 'paper_fill_note']:
        assert 'TABLE DATA paper_trading ' + table + ' ' in listing, 'Missing ledger table: ' + table
    target.with_suffix('.json').write_text(json.dumps({'scope': 'paper_trading schema and data',
        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'bytes': target.stat().st_size,
        'verifiedArchiveListing': True}, indent=2), encoding='utf-8')
    print('Verified paper ledger backup:', target)


if __name__ == '__main__':
    main()

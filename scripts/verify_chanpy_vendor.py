"""Verify calculation files against the reviewed Git commit; emit a manifest."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

COMMIT='f8ca3b5e44d7166e2abd756a8e7fa816c79faebe'
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,required=True)
args=parser.parse_args()
actual=subprocess.check_output(['git','-C',str(args.source),'rev-parse','HEAD'],text=True).strip()
if actual!=COMMIT:raise SystemExit('Unexpected upstream commit')
vendor=ROOT/'third_party/chanpy'
files={}
for path in sorted(vendor.rglob('*.py'))+ [vendor/'LICENSE']:
    relative=path.relative_to(vendor).as_posix()
    upstream=subprocess.check_output(['git','-C',str(args.source),'show',f'{COMMIT}:{relative}'])
    if path.read_bytes().replace(b'\r\n',b'\n')!=upstream.replace(b'\r\n',b'\n'):
        raise SystemExit(f'Vendor file differs: {relative}')
    files[relative]=hashlib.sha256(upstream.replace(b'\r\n',b'\n')).hexdigest()
(vendor/'manifest.json').write_text(json.dumps({'repository':'https://github.com/Vespa314/chan.py','commit':COMMIT,'normalization':'LF','sha256':files},indent=2)+'\n',encoding='utf-8')
print(f'Verified {len(files)} unchanged upstream files')

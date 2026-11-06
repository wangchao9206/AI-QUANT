"""Run the repository Compose model with a locally saved full/light mode."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'infrastructure/.deployment-mode.json'


def command(mode,arguments):
    args=['docker','compose','--project-name','ai-quant','--env-file',str(ROOT/'infrastructure/.env'),
          '-f',str(ROOT/'infrastructure/docker-compose.yml')]
    if mode=='light':args+=['-f',str(ROOT/'infrastructure/docker-compose.light.yml')]
    return args+arguments


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('full','light'))
    parser.add_argument('--save-mode',action='store_true')
    options,rest=parser.parse_known_args()
    mode=options.mode or (json.loads(STATE.read_text(encoding='utf-8'))['mode'] if STATE.exists() else 'full')
    if mode not in ('full','light'):raise SystemExit('Invalid saved deployment mode')
    if mode=='light':
        values={}
        for line in (ROOT/'infrastructure/.env').read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key,value=line.split('=',1);values[key.strip()]=value.strip().strip('"\'')
        if os.getenv('NACOS_ENABLED',values.get('NACOS_ENABLED','false')).lower()=='true':
            raise SystemExit('Discovery is enabled. Light mode requires existing static service addresses.')
        if os.getenv('COMPOSE_PROFILES',values.get('COMPOSE_PROFILES','')):
            raise SystemExit('Clear COMPOSE_PROFILES before using light mode.')
    result=subprocess.run(command(mode,rest or ['ps']),cwd=ROOT)
    if result.returncode==0 and options.save_mode:
        pending=STATE.with_suffix('.pending')
        pending.write_text(json.dumps({'mode':mode})+'\n',encoding='utf-8');pending.replace(STATE)
    return result.returncode


if __name__=='__main__':raise SystemExit(main())

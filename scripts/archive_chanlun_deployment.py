"""Tag deployed images locally and record exact identities, without publishing."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    def command(*parts):return subprocess.run(parts,check=True,capture_output=True,text=True,encoding='utf-8').stdout.strip()
    services=[]
    for service in ('frontend','chanlun-service','algorithm-service','gateway-service','chanlun-native-worker','chanpy-worker','czsc-worker','chanlun-baseline-worker'):
        container='ai-quant-'+service+'-1'
        identity=command('docker','inspect','--format','{{.Image}}',container)
        assert re.fullmatch(r'sha256:[a-f0-9]{64}',identity)
        tag='ai-quant-'+service+':chanlun-20261031-'+identity.split(':')[1]
        existing=subprocess.run(['docker','image','inspect','--format','{{.Id}}',tag],capture_output=True,text=True,encoding='utf-8')
        if existing.returncode==0 and existing.stdout.strip()!=identity:raise RuntimeError('Existing archive tag has a conflicting image identity')
        command('docker','image','tag',identity,tag)
        health=command('docker','inspect','--format','{{.State.Health.Status}}',container)
        assert health=='healthy',(service,health)
        services.append({'service':service,'imageId':identity,'localArchiveTag':tag,'health':health})
    native=next(s for s in services if s['service']=='chanlun-native-worker')
    probe="""import importlib.util,json
from pathlib import Path
from chanlun_worker.analysis import analyze
r=analyze('native',1894)
assert importlib.util.find_spec('czsc') is None
assert not Path('/app/third_party').exists() and not Path('/app/.test-tmp').exists()
print(json.dumps({'engineId':r['engineId'],'profileHash':r['profileHash'],'datasetHash':r['datasetHash'],'observedBars':r['observedBars'],'counts':r['counts'],'events':len(r['events']),'network':'none','thirdPartyCalculationDirectories':False}))
"""
    offline=json.loads(command('docker','run','--rm','--read-only','--network','none','--tmpfs','/tmp','--entrypoint','python',native['imageId'],'-c',probe))
    result={'verifiedAt':datetime.now(timezone.utc).isoformat(),'scope':'LOCAL_IMAGE_ARCHIVE_NO_REGISTRY_PUSH',
            'workspaceBaseCommit':command('git','rev-parse','HEAD'),'dirtyWorkspace':bool(command('git','status','--porcelain')),
            'sourceNote':'The base commit alone does not represent this deployment; exact built image IDs and runtime profile hashes identify it.',
            'services':services,'nativeOfflineProbe':offline}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'services':len(services),'offline':offline,'manifest':str(args.output)},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

"""Verify DNS address replacement without restarting a disposable gateway.

Creates an internal Docker network and three temporary containers, publishes no
ports, uses no application credentials/data, and removes only objects it creates.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gateway-image',default='ai-quant-gateway-service')
parser.add_argument('--output',type=Path)
args=parser.parse_args()
suffix=uuid.uuid4().hex[:10]
network='aiquant-dns-'+suffix
gateway='gateway-'+suffix
alias='peer-'+suffix
created=[]
network_created=False


def docker(*parts,check=True):
    result=subprocess.run(['docker',*map(str,parts)],capture_output=True,text=True,timeout=120)
    if check and result.returncode:raise RuntimeError(result.stderr[-3000:])
    return result.stdout.strip()


def call():
    program=f"import json,urllib.request; print(json.load(urllib.request.urlopen('http://{gateway}:8080/api/chanlun/v1/engines', timeout=2))['marker'])"
    return docker('run','--rm','--network',network,'--read-only','ai-quant-chanlun-native-worker','python','-c',program,check=False)


def wait_for(marker,seconds):
    start=time.monotonic()
    while time.monotonic()-start<seconds:
        if call()==marker:return time.monotonic()-start
        time.sleep(1)
    raise AssertionError(f'Gateway did not return {marker} within {seconds}s')


def peer(name,ip,marker):
    identifier=docker('run','-d','--name',name,'--network',network,'--network-alias',alias,'--ip',ip,
                      '--read-only','--memory','128m','--cpus','0.5',
                      '--mount',f'type=bind,source={ROOT / "tests/integration/chanlun_dns_peer.py"},target=/probe.py,readonly',
                      '-e','PROBE_MARKER='+marker,'ai-quant-chanlun-native-worker','python','/probe.py')
    created.append(identifier)
    return identifier


try:
    docker('network','create','--internal',network);network_created=True
    details=json.loads(docker('network','inspect',network))[0]
    subnet=ipaddress.ip_network(details['IPAM']['Config'][0]['Subnet'])
    first=peer('first-'+suffix,str(subnet.network_address+10),'first')
    gateway_id=docker('run','-d','--name',gateway,'--network',network,'--read-only',
                      '--tmpfs','/tmp:rw,noexec,nosuid,size=128m','--memory','512m','--cpus','1',
                      '-e',f'CHANLUN_SERVICE_URL=http://{alias}:8084',
                      '-e','NACOS_ENABLED=false','-e','SENTINEL_ENABLED=false',
                      '-e','JAVA_TOOL_OPTIONS=-Duser.home=/tmp -Dcsp.sentinel.log.dir=/tmp/sentinel',args.gateway_image)
    created.append(gateway_id)
    wait_for('first',90)
    started=docker('inspect','--format','{{.State.StartedAt}}',gateway_id)
    docker('rm','-f',first)
    peer('second-'+suffix,str(subnet.network_address+11),'second')
    elapsed=wait_for('second',40)
    assert docker('inspect','--format','{{.State.StartedAt}}',gateway_id)==started,'Gateway restarted during check'
    result={'status':'PASSED','replacementObservedSeconds':elapsed,'gatewayRestarted':False,
            'gatewayImage':docker('inspect','--format','{{.Image}}',gateway_id),
            'testScope':'Isolated internal network; backend replaced with a different IP, same DNS alias; no published ports or production changes'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
finally:
    for identifier in reversed(created):docker('rm','-f',identifier,check=False)
    if network_created:docker('network','rm',network,check=False)

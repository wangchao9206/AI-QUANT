"""Reproducible native-kernel benchmark; no performance claim about competitors."""
import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from chanlun_worker.analysis import analyze
from chanlun_worker.data import DATASET_HASH, load_dataset
from chanlun_worker.native import NativeEngine, VERSION

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repeats',type=int,default=5)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if not 1<=args.repeats<=20:parser.error('repeats must be 1..20')
bars=load_dataset()
core_times=[];audit_times=[]
for _ in range(args.repeats):
    start=time.perf_counter();engine=NativeEngine()
    for bar in bars:engine.push(bar)
    core_times.append(time.perf_counter()-start)
    start=time.perf_counter();result=analyze('native',len(bars))
    audit_times.append(time.perf_counter()-start)
def summarize(values):return {'samplesSeconds':values,'medianSeconds':statistics.median(values),'maxSeconds':max(values)}
output={'purpose':'Single-host historical kernel and complete audit computation; excludes HTTP, database and browser rendering. No cross-project speed claim.',
        'engineVersion':VERSION,'datasetHash':DATASET_HASH,'bars':len(bars),
        'environment':{'python':platform.python_version(),'system':platform.system(),'architecture':platform.machine()},
        'coreIncremental':summarize(core_times),'fullObservationAudit':summarize(audit_times),
        'profileHash':result['profileHash'],'counts':result['counts'],'events':len(result['events'])}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(output,ensure_ascii=False,indent=2))

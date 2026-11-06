"""Reconstruct every training split and rejected leaf from frozen labeled decisions."""
import gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from discover_outcome_patterns import trees
from backtesting.outcome_features import NAMES,LABELS
OUT=ROOT/'docs/research/data/outcome-discovery-2026-11-07'
def main():
    with gzip.open(OUT/'labeled-decisions.json.gz','rt',encoding='utf-8') as stream:rows=json.load(stream)
    result=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
    x=np.array([[r['feature'][name] for name in NAMES] for r in rows]);train=np.array([i for i,r in enumerate(rows) if r['partition']=='DEV'])
    audits={};comparisons=0;leaf_count=0
    for target in LABELS:
        y=np.array([r['labels'][target] for r in rows]);base=float(y[train].mean());nodes=[];leaves=[]
        def walk(indices,path,depth):
            nonlocal comparisons
            node={'depth':depth,'path':path,'trainingSamples':len(indices),'positiveLabels':int(y[indices].sum()),'candidateSplits':[]}
            nodes.append(node)
            if depth<3 and len(indices)>=800:
                p=float(y[indices].mean());impurity=p*(1-p);best=None
                for j,name in enumerate(NAMES):
                    values=x[indices,j]
                    for threshold in sorted(set(np.quantile(values,[.2,.4,.6,.8]).tolist())):
                        mask=values<=threshold;left=indices[mask];right=indices[~mask];record={'feature':name,'threshold':float(threshold),'leftSamples':len(left),'rightSamples':len(right)}
                        comparisons+=1
                        if len(left)<400 or len(right)<400:record['rejected']='MINIMUM_LEAF';node['candidateSplits'].append(record);continue
                        a=float(y[left].mean());b=float(y[right].mean());gain=impurity-(len(left)*a*(1-a)+len(right)*b*(1-b))/len(indices)
                        record.update(gain=gain,leftProbability=a,rightProbability=b);node['candidateSplits'].append(record)
                        if best is None or gain>best[0]:best=(gain,name,float(threshold),left,right)
                if best and best[0]>1e-6:
                    gain,name,t,left,right=best;node['selectedSplit']={'feature':name,'threshold':t,'gain':gain}
                    walk(left,[*path,{'feature':name,'operator':'LE','threshold':t}],depth+1)
                    walk(right,[*path,{'feature':name,'operator':'GT','threshold':t}],depth+1);return
            probability=float(y[indices].mean());coverage=len({rows[int(i)]['root'] for i in indices});positive=int(y[indices].sum());reasons=[]
            if probability<base+.03:reasons.append('TRAINING_LIFT_BELOW_3PP')
            if positive<30:reasons.append('POSITIVE_LABELS_BELOW_30')
            if coverage<12:reasons.append('TRAINING_ROOTS_BELOW_12')
            leaf={'path':path,'samples':len(indices),'positiveLabels':positive,'roots':coverage,'probability':probability,'trainingBase':base,
                'liftPp':100*(probability-base),'rejectionReasons':reasons,'indicesSha256':hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest()}
            leaves.append(leaf)
        walk(train,[],0)
        original=trees(x,y,train)
        expected={(json.dumps(path,sort_keys=True),hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest()) for indices,path in original}
        actual={(json.dumps(r['path'],sort_keys=True),r['indicesSha256']) for r in leaves}
        assert actual==expected,target
        eligible=sorted([r for r in leaves if not r['rejectionReasons']],key=lambda r:(-r['liftPp'],-r['samples']))
        chosen=eligible[:2]
        published=[p for p in result['patterns'] if p['target']==target]
        assert [r['path'] for r in chosen]==[r['path'] for r in published],target
        for r in leaves:r['selected']=r in chosen
        audits[target]={'trainingBaseProbability':base,'nodes':nodes,'leaves':leaves,'publishedPatternIds':[p['id'] for p in published]};leaf_count+=len(leaves)
    output={'status':'PASSED','toolSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'trainingDecisions':len(train),
        'testedSplitComparisons':comparisons,'allLeaves':leaf_count,'publishedPatterns':len(result['patterns']),
        'validationLabelsUsedForTreeSplits':False,'allCandidateLeavesMatchFrozenImplementation':True,'allSelectionsMatchPublishedPatterns':True,'targets':audits}
    (OUT/'tree-candidate-audit.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='targets'},indent=2))
if __name__=='__main__':main()

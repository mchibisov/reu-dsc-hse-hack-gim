"""Opt-in live holdout check; private materials and predictions never enter Git.

Run from repo root: python -m scripts.evaluate_history --xlsx PATH PATH
Uses the pinned rubric of RECRUITMENT_ID and the configured model, at API cost.
"""
import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from gim.calibration import split_history
from gim.config import load_dotenv
from gim.shared_config import SharedSettings
from gim.shared_service import SharedService
from gim_db.materials import prepare_history
from gim_db.repository import create_pool, one


def evaluation_metrics(predictions):
    scored=[r for r in predictions if r['score'] is not None]
    correct=sum(r['score']==r['expert_score'] for r in scored)
    n=len(predictions)
    return {'holdout':n,'predicted':len(scored),'coverage':len(scored)/n if n else 0,
            'exact_match':correct/len(scored) if scored else None,
            'exact_match_all':correct/n if n else None,
            'mae':sum(abs(r['score']-r['expert_score']) for r in scored)/len(scored) if scored else None,
            'abstentions':dict(Counter(r.get('error') for r in predictions if r['score'] is None)),
            'baseline_score_2':{'exact_match':sum(r['expert_score']==2 for r in predictions)/n if n else None,
                                'mae':sum(abs(2-r['expert_score']) for r in predictions)/n if n else None}}


async def evaluate(paths, output):
    records,_=prepare_history(paths)
    _,holdout=split_history(records)
    settings=SharedSettings.load()
    async with create_pool(settings.database_worker_url) as pool:
        async with pool.connection() as c:
            rubric=await one(c,'SELECT rubric,rubric_version,direction_info FROM gim.recruitments WHERE id=%s',
                            (settings.recruitment_id,))
    references={r['id'] for r in rubric['rubric'].get('history_examples',[])}
    assert not references & {r['id'] for r in holdout}, 'Reference/holdout overlap'
    service=SharedService(*(SimpleNamespace(pool=None),)*3,None,settings,None)
    semaphore=asyncio.Semaphore(2)

    async def predict(record):
        answers=[{'id':str(uuid5(NAMESPACE_URL,record['id']+':'+slot)), 'target_slot':slot,
                  'answer_text':str(text)} for slot,text in record['features'].items() if text is not None]
        row={'id':record['id'],'expert_score':record['expert_score'],'score':None}
        for attempt in range(2):
            try:
                async with semaphore:
                    result=await service.analyze({'snapshot':{**rubric,'answers':answers}})
                row['score']=result['score']
                row['attempts']=attempt+1
                break
            except Exception as exc:
                # No bodies/answers/keys in the aggregate report.
                if attempt==1:
                    row['error']=type(exc).__name__
                    if isinstance(exc,ValueError):
                        row['validation_error']=str(exc)
        print(json.dumps({'phase':'history_checked','expert':row['expert_score'],
                          'score':row['score'],'error':row.get('error')}),flush=True)
        return row

    predictions=await asyncio.gather(*(predict(r) for r in holdout if r['expert_score'] is not None))
    metrics={**evaluation_metrics(predictions),'available_labels':len(records),
             'model':settings.llm_model,'rubric_version':rubric['rubric_version']}
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump({'metrics':metrics,'predictions':predictions},f,ensure_ascii=False,indent=2)
    print(json.dumps(metrics,ensure_ascii=False))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xlsx',nargs='+',required=True)
    p.add_argument('--output',default='runtime/history-evaluation.json')
    args=p.parse_args()
    load_dotenv()
    asyncio.run(evaluate(args.xlsx,args.output))


if __name__=='__main__':
    main()

"""Reproducible, opt-in private evaluation. No raw data/predictions are committed.
Usage: PYTHONPATH=runtime/eval-deps:database/src python -m scripts.evaluate_final prepare|development|select|final
Requires scikit-learn in isolated evaluation environment; runtime never imports it.
"""
from types import SimpleNamespace
import argparse,asyncio,hashlib,json,os,time,unicodedata
from pathlib import Path
from collections import Counter
from copy import deepcopy
import numpy as np
from sklearn.model_selection import StratifiedKFold,train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge,LogisticRegression
from sklearn.metrics import confusion_matrix,classification_report
from sklearn.pipeline import make_pipeline
from gim.config import load_dotenv
from gim.shared_config import SharedSettings
from gim.llm import LLMClient
from gim.shared_analysis import safe_answers,validate_result,ANALYSIS_PROMPT
from gim.evidence import FACTS,PROMPT,validate_facts,fact_vector,calculate
from gim.calibration import split_history,reference_examples,museum_rubric
from gim_db.materials import prepare_history

ROOT=Path('runtime/final-evaluation'); ROOT.mkdir(parents=True,exist_ok=True)
SEED=42

def save(name,data):
    path=ROOT/name; tmp=path.with_suffix('.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    tmp.replace(path)

def read(name):return json.loads((ROOT/name).read_text())

def text(r):return '\n'.join(f'{a["slot"]}: {a["text"]}' for a in answers(r))
def answers(r):return safe_answers([{'id':f'{r["id"]}:{s}','target_slot':s,'answer_text':v} for s,v in r['features'].items() if v])
def fingerprint(r):
    return hashlib.sha256('\n'.join(' '.join(unicodedata.normalize('NFKC',str(r['features'].get(s) or '')).casefold().split()) for s in ('experience','expectations','interests','hobbies','directions')).encode()).hexdigest()
def records():
    data,_=prepare_history(list(Path(os.environ.get('GIM_MATERIALS_DIR',str(Path.home()/'Downloads'))).glob('Анкеты 202*.xlsx')))
    return [r for r in data if r['expert_score'] is not None]
def metrics(y,p):
    valid=[i for i,v in enumerate(p) if v is not None]; n=len(y); k=sum(a==b for a,b in zip(y,p)); z=1.96; ph=k/n
    centre=(ph+z*z/(2*n))/(1+z*z/n); half=z*((ph*(1-ph)/n+z*z/(4*n*n))**.5)/(1+z*z/n)
    return {'n':n,'predicted':len(valid),'coverage':len(valid)/n,'accuracy_all':k/n,
      'accuracy_scored':k/len(valid) if valid else None,'mae':sum(abs(y[i]-p[i]) for i in valid)/len(valid) if valid else None,
      'accuracy_wilson95':[centre-half,centre+half],
      'confusion_labels':[0,1,2,3,'abstain'],'confusion':[[sum(a==c and b==d for a,b in zip(y,p)) for d in [0,1,2,3,None]] for c in range(4)],
      'per_class':{str(c):{'n':sum(a==c for a in y),'recall':sum(a==c and b==c for a,b in zip(y,p))/max(1,sum(a==c for a in y))} for c in range(4)}}
def rounded(v):return [int(max(0,min(3,float(x)))+.5) for x in v]

def prepare():
    if (ROOT/'split.json').exists():raise ValueError('Split already frozen; do not overwrite')
    rs=records(); train,oldtest=split_history(rs); excluded={r['id'] for r in oldtest}|{r['id'] for r in reference_examples(train)}
    vector,_=prepare_history(list(Path(os.environ.get('GIM_MATERIALS_DIR',str(Path.home()/'Downloads'))).glob('Вект*данные.xlsx')))
    inspected={fingerprint(r) for r in vector[:3]}
    excluded|={r['id'] for r in rs if fingerprint(r) in inspected}
    groups={}; conflicts=[]
    for r in rs:
        fp=fingerprint(r)
        if fp in groups:
            if groups[fp]['expert_score']!=r['expert_score']:conflicts.append(fp)
            excluded.add(r['id'])
        else:groups[fp]=r
    eligible=[r for r in rs if r['id'] not in excluded]
    strat=[f'{r["cohort"]}:{r["expert_score"]}' for r in eligible]
    if min(Counter(strat).values())<2:strat=[r['expert_score'] for r in eligible]
    _,test=train_test_split(eligible,test_size=22,stratify=strat,random_state=SEED)
    test_ids={r['id'] for r in test}; dev=list({fingerprint(r):r for r in rs if r['id'] not in test_ids}.values())
    # Previously inspected records may be development data, but duplicates must not cross CV folds.
    # Similarity is audited before tuning. Only aggregate pairs; never inspect held-out text.
    v=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),min_df=2).fit_transform([text(r) for r in rs]); sim=(v@v.T).toarray()
    pairs=[(rs[i]['id'],rs[j]['id'],float(sim[i,j])) for i in range(len(rs)) for j in range(i) if sim[i,j]>.92]
    if pairs:raise ValueError('Near duplicates detected; group before freezing and CV')
    save('split.json',{'seed':SEED,'dev':[r['id'] for r in dev],'test':[r['id'] for r in test],
      'excluded_from_test':sorted(excluded),'fingerprints':{r['id']:fingerprint(r) for r in rs},'near_duplicates':pairs,'conflicts':conflicts})
    print(json.dumps({'phase':'split_frozen','dev':len(dev),'test':len(test),'excluded':len(excluded),'test_classes':dict(Counter(r['expert_score'] for r in test))}))

def select_fixed_model():
    s=read('selection.json');fs=read('dev-facts.json');by={r['id']:r for r in records()};valid=[f for f in fs if f.get('facts')];x=np.array([fact_vector(f['facts']) for f in valid]);y=np.array([by[f['id']]['expert_score'] for f in valid]);dev=s['dev_ids'];indices={r:i for i,r in enumerate(dev)}
    results={};models={}
    for C in [.1,1,10]:
     for balanced in [None,'balanced']:
      p=[None]*len(dev)
      for tr,va in StratifiedKFold(3,shuffle=True,random_state=42).split(x,y):
       m=LogisticRegression(C=C,class_weight=balanced,max_iter=1000).fit(x[tr],y[tr])
       for i,pred in zip(va,m.predict(x[va])):p[indices[valid[i]['id']]]=int(pred)
      name=f'fixed-facts-logistic-{C}-{balanced}';results[name]=metrics([by[i]['expert_score'] for i in dev],p)
      m=LogisticRegression(C=C,class_weight=balanced,max_iter=1000).fit(x,y);models[name]={'kind':'logistic','classes':m.classes_.tolist(),'coefficients':m.coef_.tolist(),'intercept':m.intercept_.tolist(),'C':C,'class_weight':balanced}
    for alpha in [1,10,100]:
     p=[None]*len(dev)
     for tr,va in StratifiedKFold(3,shuffle=True,random_state=42).split(x,y):
      m=Ridge(alpha=alpha,positive=True).fit(x[tr],y[tr])
      for i,pred in zip(va,rounded(m.predict(x[va]))):p[indices[valid[i]['id']]]=pred
     name=f'hybrid-ridge-{alpha}';results[name]=metrics([by[i]['expert_score'] for i in dev],p)
     m=Ridge(alpha=alpha,positive=True).fit(x,y);models[name]={'coefficients':m.coef_.tolist(),'intercept':float(m.intercept_),'alpha':alpha}
    winner=sorted(results,key=lambda k:(-results[k]['accuracy_all'],results[k]['mae']))[0]
    if (ROOT/'final.json').exists():raise ValueError('Cannot tune after final')
    save('selection-initial-small-sample.json',s)
    s.update(winner=winner,model=models[winner],fixed_facts_cv=results,selection_basis='All 90 development records, 3 stratified folds; primary exact accuracy, secondary MAE. Prompting/RAG compared separately on 12 balanced development records; not used for hyperparameter ranking across different populations.')
    save('selection.json',s)
    print(json.dumps({'winner':winner,'metrics':results[winner],'all':{k:(v['accuracy_all'],v['mae']) for k,v in results.items()}}))

async def main(stage):
    if stage=='select':select_fixed_model();return
    if stage=='prepare':prepare();return
    split=read('split.json'); rs=records(); by={r['id']:r for r in rs}
    assert all(fingerprint(r)==split['fingerprints'][r['id']] for r in rs)
    dev=[by[i] for i in split['dev']]; test=[by[i] for i in split['test']]
    load_dotenv(os.environ.get('GIM_ENV_FILE','.env')); settings=SharedSettings.load(); llm=LLMClient(settings)
    semaphore=asyncio.Semaphore(3)
    async def cached(task,r,system,payload,validator):
        digest=hashlib.sha256(json.dumps([system,payload,settings.llm_model],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        name='call-'+digest+'.json'
        if (ROOT/name).exists():return read(name)
        row={'id':r['id'],'task':task,'score':None}; started=time.monotonic()
        for attempt in range(2 if task=='facts' else 1):
            try:
                async with semaphore:
                    client=llm if task=='facts' else LLMClient(SimpleNamespace(**{**vars(settings),'llm_reasoning_enabled':False,'llm_max_tokens':3500}))
                    async with asyncio.timeout(60):value=await client.complete(system,payload)
                row.update(validator(value)); row['error']=None; break
            except Exception as exc:
                row['error']=type(exc).__name__
                if type(exc) is ValueError:row['validation_error']=str(exc)
        row['seconds']=round(time.monotonic()-started,3);save(name,row)
        print(json.dumps({'phase':task,'id':r['id'],'error':row.get('error'),'seconds':row['seconds']}),flush=True)
        return row
    async def extract(r):
        safe=answers(r)
        return await cached('facts',r,PROMPT,{'facts':{c:t[1] for c,t in FACTS.items()},'answers':safe},lambda x:{'facts':validate_facts(x.get('facts'),safe)})
    def cv(y):return list(StratifiedKFold(3,shuffle=True,random_state=SEED).split(np.zeros(len(y)),y))
    async def llm_score(r,training,mode):
        rubric=museum_rubric(training)
        rubric['history_examples']=reference_examples(training)
        if mode=='rag':
            corpus=[text(x) for x in training]; vec=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True)
            mat=vec.fit_transform(corpus); similarities=(mat@vec.transform([text(r)]).T).toarray().ravel()
            nearest=[training[i] for i in np.argsort(-similarities)[:8]]
            rubric['history_examples']=[{'id':x['id'],'expert_score':x['expert_score'],'answers':[{'slot':a['slot'],'text':a['text'][:600]} for a in answers(x)]} for x in nearest]
        if mode=='current':rubric=museum_rubric(rs) # frozen existing references, excluded from final test
        raw=[{'id':a['id'],'answer_text':a['text'],'target_slot':a['slot']} for a in answers(r)]
        snap={'rubric':rubric,'answers':raw}; payload={'rubric':{k:v for k,v in rubric.items() if k!='history_examples'},'answers':answers(r),'history_examples':rubric['history_examples'],'direction_info':{}}
        return await cached(mode,r,ANALYSIS_PROMPT,payload,lambda x:{'score':validate_result(x,snap,answers(r))['score']})
    if stage=='development':
        facts=await asyncio.gather(*(extract(r) for r in dev));save('dev-facts.json',facts)
        valid=[i for i,f in enumerate(facts) if f.get('facts')];
        if len(valid)<len(dev)*.9:raise ValueError('Insufficient extraction coverage')
        y=np.array([dev[i]['expert_score'] for i in valid]); x=np.array([fact_vector(facts[i]['facts']) for i in valid]); folds=cv(y)
        out={}; models={}
        for alpha in [1,10,100]:
            predictions=[None]*len(dev)
            for tr,va in folds:
                model=Ridge(alpha=alpha,positive=True).fit(x[tr],y[tr])
                for i,p in zip(va,rounded(model.predict(x[va]))):predictions[valid[i]]=p
            name=f'hybrid-ridge-{alpha}';out[name]=predictions
            model=Ridge(alpha=alpha,positive=True).fit(x,y);models[name]={'coefficients':model.coef_.tolist(),'intercept':float(model.intercept_),'alpha':alpha}
        # Cheap text classifier; preprocessing fitted inside each training fold.
        yp=np.array([r['expert_score'] for r in dev]); texts=[text(r) for r in dev]; p=[None]*len(dev)
        for tr,va in cv(yp):
            model=make_pipeline(TfidfVectorizer(ngram_range=(1,2),min_df=2,sublinear_tf=True),LogisticRegression(C=1,max_iter=1000))
            model.fit([texts[i] for i in tr],yp[tr]); pred=model.predict([texts[i] for i in va])
            for i,pv in zip(va,pred):p[i]=int(pv)
        out['tfidf-logistic']=p
        # Same 12 development records for costly comparisons; validation examples never enter prompts/RAG.
        selected=[]
        reference_ids={r['id'] for r in reference_examples(split_history(rs)[0])}
        for c in range(4):selected.extend([i for i,r in enumerate(dev) if r['expert_score']==c and r['id'] not in reference_ids][:3])
        selection=set(selected); valpairs={}
        for tr,va in cv(yp):
            training=[dev[i] for i in tr]
            for i in va:
                if i in selection:valpairs[i]=training
        for mode in ['current','fewshot','rag']:
            res=await asyncio.gather(*(llm_score(dev[i],valpairs[i],mode) for i in selected))
            out[mode]=[x.get('score') for x in res]
        sample_y=[int(yp[i]) for i in selected]
        comparisons={name:metrics(sample_y,[pred[i] for i in selected] if len(pred)==len(dev) else pred) for name,pred in out.items()}
        comparisons['majority']=metrics(sample_y,[Counter(yp.tolist()).most_common(1)[0][0]]*len(selected))
        # Production must remain evidence-explainable: text classifier is diagnostic, not an opaque replacement.
        candidates=[n for n in comparisons if n in models or n in ['current','fewshot','rag']]
        winner=sorted(candidates,key=lambda n:(-comparisons[n]['accuracy_all'],comparisons[n]['mae'] if comparisons[n]['mae'] is not None else 99,0 if n=='current' else 1))[0]
        freeze={'winner':winner,'comparisons':comparisons,'all_dev_cv':{n:metrics(yp.tolist(),p) for n,p in out.items() if len(p)==len(dev)},'model':models.get(winner),'dev_ids':split['dev'],'test_ids':split['test'],'sample_ids':[dev[i]['id'] for i in selected],'model_name':settings.llm_model,'selection_locked':True}
        if (ROOT/'selection.json').exists():raise ValueError('Selection already frozen; do not overwrite after final')
        save('selection.json',freeze);print(json.dumps({'winner':winner,'comparisons':comparisons},ensure_ascii=False));return
    selection=read('selection.json')
    if (ROOT/'final.json').exists():raise ValueError('Final already evaluated; do not retune')
    winner=selection['winner']; rows=[]
    if selection.get('model') is not None:
        extracted=await asyncio.gather(*(extract(r) for r in test))
        for r,f in zip(test,extracted):
            try:p=calculate(f['facts'],selection['model'])['score']
            except (ValueError,KeyError):p=None
            rows.append(p)
    else:
        results=await asyncio.gather(*(llm_score(r,dev,winner) for r in test));rows=[r['score'] for r in results]
    previous=await asyncio.gather(*(llm_score(r,dev,'current') for r in test))
    yy=[r['expert_score'] for r in test];baseline=Counter(r['expert_score'] for r in dev).most_common(1)[0][0]
    result={'selected':winner,'new':metrics(yy,rows),'current':metrics(yy,[r['score'] for r in previous]),'baseline':metrics(yy,[baseline]*len(test)), 'predictions':[{'id':r['id'],'expert':r['expert_score'],'new':p,'current':o['score']} for r,p,o in zip(test,rows,previous)]}
    save('final.json',result);print(json.dumps({k:v for k,v in result.items() if k!='predictions'},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','development','select','final'])
    asyncio.run(main(parser.parse_args().stage))

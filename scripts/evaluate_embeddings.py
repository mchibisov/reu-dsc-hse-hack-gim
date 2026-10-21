"""Opt-in diagnostic embedding CV on frozen development records only. No production integration."""
import asyncio,json,os
from pathlib import Path
import httpx,numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from scripts.evaluate_final import records,read,save,text,metrics
from gim.config import load_dotenv
from gim.shared_config import SharedSettings
async def main():
 load_dotenv(os.environ.get('GIM_ENV_FILE','.env'));s=SharedSettings.load()
 split=read('split.json');by={r['id']:r for r in records()};dev=[by[i] for i in split['dev']]
 model='openai/text-embedding-3-small'; vectors=[]
 async with httpx.AsyncClient(timeout=90) as c:
  for i in range(0,len(dev),15):
   res=await c.post(s.llm_base_url+'/embeddings',headers={'Authorization':'Bearer '+s.llm_api_key},json={'model':model,'input':[text(r) for r in dev[i:i+15]]})
   if res.status_code!=200:
    save('embeddings.json',{'model':model,'status':res.status_code,'experiment':'unsupported_or_unavailable','raw_body_saved':False});print('embedding endpoint status',res.status_code);return
   vectors.extend(x['embedding'] for x in sorted(res.json()['data'],key=lambda r:r['index']))
 x=np.array(vectors);x=x/np.maximum(np.linalg.norm(x,axis=1,keepdims=True),1e-9);y=np.array([r['expert_score'] for r in dev]);pred=[None]*len(y)
 for tr,va in StratifiedKFold(3,shuffle=True,random_state=42).split(x,y):
  m=LogisticRegression(C=10,max_iter=1000).fit(x[tr],y[tr])
  for i,p in zip(va,m.predict(x[va])):pred[i]=int(p)
 save('embeddings.json',{'model':model,'status':200,'cv':metrics(y.tolist(),pred),'runtime_integration':False,'reason':'Diagnostic opaque-text model; no evidence calculation for production.'})
 save('dev-vectors.json',{'ids':split['dev'],'vectors':vectors,'model':model})
 print(json.dumps(read('embeddings.json')))
asyncio.run(main())

"""Private model validation. JSONL predictions: id,score. No model invented here."""
import argparse
import json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('history');p.add_argument('predictions');a=p.parse_args()
truth={r['id']:r['expert_score'] for r in map(json.loads,Path(a.history).read_text().splitlines()) if r['expert_score'] is not None}
pred={}
for line in Path(a.predictions).read_text().splitlines():
    r=json.loads(line)
    if r['id'] in pred or type(r['score']) is not int or not 0<=r['score']<=3:raise ValueError('Invalid/duplicate prediction')
    pred[r['id']]=r['score']
if set(pred)-set(truth):raise ValueError('Unknown prediction id')
if not pred:raise ValueError('No predictions')
print(json.dumps({'predicted':len(pred),'available_labels':len(truth),'coverage':len(pred)/len(truth),
 'exact_match':sum(pred[k]==truth[k] for k in pred)/len(pred),'mae':sum(abs(pred[k]-truth[k]) for k in pred)/len(pred)}))

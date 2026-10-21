import argparse
import json
from gim_db.materials import prepare_history,write_private_jsonl

p=argparse.ArgumentParser(description='Prepare private historical features and labels; future outcomes excluded')
p.add_argument('xlsx',nargs='+');p.add_argument('--output',required=True)
a=p.parse_args();records,counts=prepare_history(a.xlsx)
write_private_jsonl(a.output,records)
print(json.dumps({'counts':counts,'total':len(records),'labelled':sum(r['expert_score'] is not None for r in records)},ensure_ascii=False))

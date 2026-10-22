"""Operator-only import into a DRAFT recruitment. No historical personal data upload."""
import argparse
import json
import os
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from gim_db.materials import questionnaire_from_docx,direction_text_from_pdf

p=argparse.ArgumentParser(description='Load private museum bank; team supplies approved rubric/direction mapping')
p.add_argument('--docx',required=True);p.add_argument('--directions-pdf',required=True)
p.add_argument('--config',required=True,help='Private JSON: group_id,title,questionnaire_version,rubric_version,rubric,direction_info,followup_policy')
a=p.parse_args();config=json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
# No demo weights are silently promoted to official rules.
if not config['rubric'].get('approved_by') or not config['rubric'].get('scoring_rule'):
    raise ValueError('Team-approved rubric and explicit score mapping required')
if set(config['direction_info'])!={'organizational','project','collections','inclusive','media'}:
    raise ValueError('All five actual directions required')
config['direction_info']['_source_pages']=direction_text_from_pdf(a.directions_pdf)
bank=questionnaire_from_docx(a.docx)
with psycopg.connect(os.environ['DATABASE_ADMIN_URL']) as c:
    rid=c.execute('''INSERT INTO gim.recruitments(group_id,title,questionnaire_version,rubric_version,rubric,direction_info,followup_policy)
      VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id''',(config['group_id'],config['title'],config['questionnaire_version'],config['rubric_version'],Jsonb(config['rubric']),Jsonb(config['direction_info']),Jsonb(config['followup_policy']))).fetchone()[0]
    for q in bank:
        c.execute('''INSERT INTO gim.question_templates(recruitment_id,code,kind,text,position,required,target_slot,directions,validation)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(rid,q['code'],q['kind'],q['text'],q['position'],q['required'],q['target_slot'],q['directions'],Jsonb(q['validation'])))
print(json.dumps({'recruitment_id':str(rid),'status':'draft','templates':len(bank)}))

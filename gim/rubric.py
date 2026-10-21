"""Human-authored rubric validation. No default criteria or inferred weights."""
import json
import math
from decimal import Decimal
from pathlib import Path

from gim.llm import ModelUnavailable
from gim.scoring import validate_evaluation


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Invalid criterion points')
    return Decimal(str(value))


def validate_rubric(rubric):
    if not isinstance(rubric, dict) or not isinstance(rubric.get('version'), str) or not rubric['version'].strip():
        raise ValueError('A human-authored rubric version is required')
    criteria = rubric.get('criteria')
    if not isinstance(criteria, list) or not criteria:
        raise ValueError('Human-authored criteria are required')
    codes, total = set(), Decimal(0)
    for criterion in criteria:
        if not isinstance(criterion, dict) or not isinstance(criterion.get('code'), str) or not criterion['code'].strip():
            raise ValueError('Invalid criterion code')
        code = criterion['code']
        if code in codes or not isinstance(criterion.get('description'), str) or not criterion['description'].strip():
            raise ValueError('Invalid criterion description or duplicate code')
        codes.add(code)
        maximum = number(criterion.get('max_score'))
        if maximum <= 0:
            raise ValueError('Invalid criterion weight')
        total += maximum
    if total != 3:
        raise ValueError('Rubric maximum must be exactly 3')
    return rubric


def load_rubric(path):
    if not path:
        raise ModelUnavailable('RUBRIC_PATH must point to the team criteria')
    try:
        return validate_rubric(json.loads(Path(path).read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError):
        raise ModelUnavailable('Invalid human-authored rubric file') from None


def validate_rubric_evaluation(result, rubric, answers):
    validate_rubric(rubric)
    if not isinstance(result, dict) or not isinstance(result.get('criteria_results'), list):
        raise ValueError('Invalid model evaluation')
    maxima = {c['code']: number(c['max_score']) for c in rubric['criteria']}
    seen, total = set(), Decimal(0)
    for item in result['criteria_results']:
        if not isinstance(item, dict) or item.get('criterion') not in maxima or item['criterion'] in seen:
            raise ValueError('Missing, repeated or invented criterion')
        code = item['criterion']
        seen.add(code)
        points = number(item.get('points'))
        if not 0 <= points <= maxima[code]:
            raise ValueError('Criterion score outside approved weight')
        if points > 0 and (not item.get('quote') or not item.get('answer_id')):
            raise ValueError('Positive score requires source evidence')
        total += points
    if seen != set(maxima) or number(result.get('score')) != total:
        raise ValueError('Criterion coverage or score sum mismatch')
    result = {**result, 'rubric_version': rubric['version'], 'rubric_snapshot': rubric}
    return validate_evaluation(result, answers)

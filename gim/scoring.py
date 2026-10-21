import math
from gim.dialog import DIRECTIONS


def validate_evaluation(result, answers):
    score = result.get('score')
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 3:
        raise ValueError('Invalid score')
    if not isinstance(result.get('rubric_version'), str) or not result['rubric_version'].strip():
        raise ValueError('Rubric version required')
    if not isinstance(result.get('rubric_snapshot'), dict) or not result['rubric_snapshot']:
        raise ValueError('Rubric snapshot required')
    citations = {str(a['id']): a['answer_text'] for a in answers}
    if not isinstance(result.get('criteria_results'), list) or not result['criteria_results']:
        raise ValueError('Criterion evidence required')
    for item in result['criteria_results']:
        if not isinstance(item, dict) or not item.get('criterion') or not item.get('reason'):
            raise ValueError('Invalid criterion')
        # Unmet criteria may have no quote; positive evidence must reference a real answer.
        if item.get('quote'):
            if item.get('answer_id') not in citations or item['quote'] not in citations[item['answer_id']]:
                raise ValueError('Citation is not present in source answer')
    if not isinstance(result.get('summary'), str):
        raise ValueError('Summary required')
    if not isinstance(result.get('interview_questions'), list) or not all(isinstance(q, str) for q in result['interview_questions']):
        raise ValueError('Invalid interview questions')
    directions = result.get('recommended_directions')
    if not isinstance(directions, list) or any(d not in DIRECTIONS for d in directions):
        raise ValueError('Invalid directions')
    return result

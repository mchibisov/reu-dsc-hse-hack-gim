"""Validation only. Question selection/generation belongs exclusively to the model."""


def validate_decision(result, directions, asked):
    if not isinstance(result, dict) or result.get('action') not in ('ask', 'finish'):
        raise ValueError('Invalid model action')
    if result['action'] == 'finish':
        return {'action': 'finish'}
    question = result.get('question')
    if result.get('direction') not in directions:
        raise ValueError('Question direction is not selected')
    if not isinstance(question, str) or not 10 <= len(question.strip()) <= 1000:
        raise ValueError('Invalid generated question')
    normalized = ' '.join(question.split()).casefold()
    if normalized in {' '.join(q.split()).casefold() for q in asked}:
        raise ValueError('Repeated question')
    return {'action': 'ask', 'direction': result['direction'], 'question': question.strip()}

"""Воспроизводимая оценка без сохранения персональных строк в отчёт."""
import argparse
import asyncio
import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from .analysis import Provider, sanitize_answers
from .config import get_settings
from .rubric import RUBRIC_VERSION


def normalize(value):
    return ' '.join(value.lower().replace('ё', 'е').split())


def load_dataset(paths):
    rows, inventory = [], []
    mapping = {'вуз': 'university', 'факультет': 'faculty', 'курс': 'course',
        'сфера научных интересов': 'interests', 'опыт работы': 'experience',
        'владение иностранными языками': 'languages', 'интересующие виды волонтерства': 'directions',
        'чего вы ожидаете': 'expectations', 'ваше хобби': 'hobbies', 'откуда вы узнали': 'source',
        'фио': 'name', 'электронная почта': 'email'}
    for path in paths:
        path = Path(path)
        data = path.read_bytes()
        text = data.decode('utf-8-sig')
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        source_rows = list(csv.DictReader(text.splitlines(keepends=True), dialect=dialect))
        labeled = 0
        for row in source_rows:
            answers, label = {}, None
            for header, value in row.items():
                if header is None:
                    continue
                key = normalize(header)
                value = str(value or '').strip()
                if key.startswith('сколько баллов') or key == 'оценка анкеты':
                    try:
                        score = float(value.replace(',', '.'))
                        label = int(score) if score in (0, 1, 2, 3) else None
                    except ValueError:
                        pass
                    continue
                for prefix, target in mapping.items():
                    if key.startswith(prefix) and value:
                        answers[target] = value
                        break
            if label is not None:
                rows.append({'answers': sanitize_answers(answers), 'label': label})
                labeled += 1
        inventory.append({'file': path.name, 'sha256': hashlib.sha256(data).hexdigest(),
                          'rows': len(source_rows), 'labeled': labeled})
    return rows, inventory


def split_dataset(rows, seed=42):
    groups = {}
    for row in rows:
        key = json.dumps(row['answers'], ensure_ascii=False, sort_keys=True)
        groups.setdefault(key, []).append(row)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    test_keys = set(keys[:max(1, len(keys) // 5)]) if len(keys) > 1 else set()
    train = [row for key, group in groups.items() if key not in test_keys for row in group]
    test = [row for key, group in groups.items() if key in test_keys for row in group]
    return train, test


def metrics(labels, predictions):
    matrix = [[0] * 4 for _ in range(4)]
    pairs = [(a, b) for a, b in zip(labels, predictions, strict=True) if b is not None]
    for actual, predicted in pairs:
        matrix[actual][predicted] += 1
    return {'total': len(labels), 'scored': len(pairs),
            'coverage': len(pairs) / len(labels) if labels else 0,
            'accuracy': sum(a == b for a, b in pairs) / len(pairs) if pairs else None,
            'mae': sum(abs(a - b) for a, b in pairs) / len(pairs) if pairs else None,
            'confusion_matrix': matrix}


async def evaluate(paths, use_llm=False):
    rows, inventory = load_dataset(paths)
    train, holdout = split_dataset(rows)
    majority = Counter(row['label'] for row in train).most_common(1)
    baseline = majority[0][0] if majority else None
    labels = [row['label'] for row in holdout]
    report = {'inventory': inventory, 'seed': 42, 'rubric_version': RUBRIC_VERSION,
              'train_rows': len(train), 'holdout_rows': len(holdout),
              'majority_baseline': metrics(labels, [baseline] * len(labels)),
              'llm': None, 'limitations': [
                  '0 означает не приглашён, а 1–3 качество анкеты; интерпретация неоднородна.',
                  'Будущие часы, принятие, явка и удержание исключены из признаков.',
                  'Промпт и рубрика не настраиваются по holdout; baseline не является результатом LLM.',
                  'Исторические анкеты не содержат всех полей нового опроса.']}
    if use_llm:
        settings = get_settings()
        if not settings.llm_api_key or not settings.llm_model:
            raise ValueError('Для --llm нужны LLM_API_KEY и LLM_MODEL.')
        provider = Provider(settings)
        try:
            predictions = []
            for row in holdout:
                result = await provider.analyze(row['answers'])
                predictions.append(result['score'] if result else None)
            report['llm'] = metrics(labels, predictions)
        finally:
            await provider.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--llm', action='store_true', help='Разрешить платные запросы выбранной модели')
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.csv, args.llm))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Анкет: {sum(x['rows'] for x in report['inventory'])}; holdout: {report['holdout_rows']}. "
          'Отчёт сохранён без персональных строк.')


if __name__ == '__main__':
    main()

"""Проверка конкретной модели Polza только на синтетических ответах."""
import argparse
import asyncio
import json
from pathlib import Path

from check_groq import probe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='deepseek/deepseek-v4.1-flash-1017')
    parser.add_argument('--provider', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(probe(args.model, args.provider, base_url='https://polza.ai/api/v1',
                              key_variable='POLZA_API_KEY', provider_name='Polza'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    if not report.get('structured_json_valid') or (args.provider and not (
        report.get('provider_analysis_valid') and report.get('provider_followups_valid')
    )):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

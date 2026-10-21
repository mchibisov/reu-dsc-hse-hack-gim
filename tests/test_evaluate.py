import csv

from gim_bot.evaluate import load_dataset, metrics, split_dataset


def test_metrics_include_coverage_and_unknowns():
    result = metrics([0, 1, 3], [0, 2, None])
    assert result['accuracy'] == .5
    assert result['mae'] == .5
    assert result['coverage'] == 2 / 3
    assert result['confusion_matrix'][1][2] == 1


def test_historical_outcomes_are_never_model_features(tmp_path):
    source = tmp_path / 'synthetic.csv'
    with source.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['Сколько баллов дали после обработки анкеты:',
            'Активность в часах в год:', 'Взяли ли кандидата в команду?',
            'Опыт работы, стажировки', 'Чего Вы ожидаете от волонтерства в Историческом музее?'])
        writer.writeheader()
        writer.writerow({'Сколько баллов дали после обработки анкеты:': 3,
                         'Активность в часах в год:': 70, 'Взяли ли кандидата в команду?': 'ДА',
                         'Опыт работы, стажировки': 'Работал в архиве',
                         'Чего Вы ожидаете от волонтерства в Историческом музее?': 'Опыт работы с фондами'})
    rows, inventory = load_dataset([source])
    assert rows[0]['label'] == 3
    assert set(rows[0]['answers']) == {'experience', 'expectations'}
    assert inventory[0]['rows'] == 1


def test_holdout_keeps_duplicate_profiles_together():
    rows = [{'answers': {'experience': str(i)}, 'label': i % 4} for i in range(20)]
    rows.append(rows[0].copy())
    train, test = split_dataset(rows)
    assert {str(r['answers']) for r in train}.isdisjoint({str(r['answers']) for r in test})
    assert split_dataset(rows) == (train, test)

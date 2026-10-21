import pytest

from gim_bot.process_lock import single_vk_process


def test_only_one_local_vk_process_and_lock_is_released(tmp_path):
    path = tmp_path / 'vk.lock'
    with single_vk_process(path):
        with pytest.raises(RuntimeError, match='уже запущен'):
            with single_vk_process(path):
                pytest.fail('Второй poller не должен запуститься')
    with single_vk_process(path):
        pass

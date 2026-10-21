import os
import unittest
from unittest.mock import patch

from gim.config import Settings


class ConfigTests(unittest.TestCase):
    def test_migration_settings_accept_unconfigured_vk(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://localhost/test', 'VK_GROUP_ID': ''}, clear=True):
            self.assertEqual(Settings.load().group_id, 0)

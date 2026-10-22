"""Docker bootstrap never needs private museum documents on a clean machine."""
import json
from pathlib import Path
import tempfile
import unittest

class LocalSetupTests(unittest.TestCase):
    def test_packaged_museum_bank_is_ready_without_private_files(self):
        from gim.local_setup import load_bank
        bank=load_bank()
        base=[q for q in bank['questions'] if q['kind']=='base']
        self.assertEqual(len(base),18)
        self.assertEqual(base[0]['target_slot'],'consent')
        self.assertNotIn('university_other',{q['target_slot'] for q in base})
        self.assertEqual(len(bank['direction_info']),5)
        self.assertIn('КАМИС',bank['direction_info']['collections'])

    def test_local_runtime_reads_only_generated_runtime_credentials(self):
        from gim.local_setup import runtime_environment
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runtime.json'
            path.write_text(json.dumps({'env':{'DATABASE_BOT_URL':'bot','VK_GROUP_ID':'123'},'installation_id':'x'}))
            self.assertEqual(runtime_environment(path),{'DATABASE_BOT_URL':'bot','VK_GROUP_ID':'123'})
            path.write_text(json.dumps({'env':{'DATABASE_ADMIN_URL':'operator'}}))
            with self.assertRaises(ValueError):runtime_environment(path)

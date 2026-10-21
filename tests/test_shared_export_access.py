import unittest
from copy import deepcopy

class AccessProofTests(unittest.TestCase):
    def event(self,text):
        return {'group_id':17,'event_id':'synthetic-event','object':{'message':{'from_id':42,'peer_id':42,'text':text}}}

    def test_code_is_not_persisted_and_proof_is_identity_bound(self):
        from gim.shared_export_access import seal_export, valid_proof
        secret='synthetic-private-code'
        event=seal_export(self.event('/export '+secret),secret)
        self.assertNotIn(secret,str(event))
        self.assertTrue(valid_proof(event,secret))
        self.assertFalse(valid_proof(event,'rotated-code'))
        changed=deepcopy(event);changed['object']['message']['from_id']=99
        self.assertFalse(valid_proof(changed,secret))
        self.assertFalse(valid_proof(event,''))

    def test_bare_export_has_no_grant(self):
        from gim.shared_export_access import seal_export,valid_proof
        event=seal_export(self.event('/export'),'synthetic')
        self.assertFalse(valid_proof(event,'synthetic'))

    def test_excel_alias_seals_code_before_persistence(self):
        from gim.shared_export_access import seal_export,valid_proof
        event=seal_export(self.event('/excel synthetic-private-code'),'synthetic-private-code')
        self.assertNotIn('synthetic-private-code',str(event))
        self.assertEqual(event['object']['message']['text'],'/export')
        self.assertTrue(valid_proof(event,'synthetic-private-code'))

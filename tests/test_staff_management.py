import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from gim.shared_service import SharedService

class StaffManagementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service=object.__new__(SharedService)
        self.service.settings=SimpleNamespace(group_id=123)
        self.service._staff=AsyncMock(return_value={'role':'admin'})
        self.service._emit=AsyncMock()
        self.service.staff_repo=SimpleNamespace(set_staff=AsyncMock())
    async def test_admin_can_add_verified_id_using_existing_protected_function(self):
        await self.service._staff_command({'id':'evt'},1,'/staff add 456 admin','/staff')
        self.service.staff_repo.set_staff.assert_awaited_once_with(1,123,456,role='admin',active=True,notify=True)
    async def test_curator_and_invalid_input_cannot_grant_access(self):
        self.service._staff.return_value={'role':'curator'}
        await self.service._staff_command({},1,'/staff add 456 admin','/staff')
        self.service.staff_repo.set_staff.assert_not_awaited()
        self.service._staff.return_value={'role':'admin'}
        for command in ['/staff add -1 admin','/staff add 456 superuser','/staff add 456 admin extra']:
            await self.service._staff_command({},1,command,'/staff')
        self.service.staff_repo.set_staff.assert_not_awaited()
    async def test_remove_revokes_access_and_notifications(self):
        await self.service._staff_command({},1,'/staff remove 456','/staff')
        self.service.staff_repo.set_staff.assert_awaited_once_with(1,123,456,role='curator',active=False,notify=False)

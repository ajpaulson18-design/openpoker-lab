"""Storage-mode failures must precede physical/literal preparation."""
import struct
import unittest
from unittest.mock import patch
from tests.compact_role_storage_reference import native_resources,verify
from tests.virtual_role_walk_wire_reference import header
from tests.virtual_role_walk_reference import OUTPUT


class CompactRoleStorageAdmissionTests(unittest.TestCase):
    def test_foreign_mode_cannot_choose_a_fallback(self):
        for mode in (False,True,-1,2,'compact',None):
            with self.subTest(mode=mode),self.assertRaises(ValueError):native_resources(mode)

    def test_foreign_or_oversized_format_refuses_before_context(self):
        request=b'OPLRIN01'+struct.pack('<11Q',1,0,2,0,0,0,0,0,0,0,0)
        with patch('tests.compact_role_storage_reference.Context',side_effect=AssertionError('unadmitted reference entered')):
            for raw in (b'',b'OPLROW01',b'OPLRSW00',b'\0'*(OUTPUT+1)):
                with self.subTest(bytes=len(raw)),self.assertRaises(ValueError):
                    verify(raw,request,0,((0,0),(0,0)),'first',1)

    def test_foreign_resource_or_carrier_contract_refuses_before_context(self):
        request=b'OPLRIN01'+struct.pack('<11Q',1,0,2,0,0,0,0,0,0,0,0)
        values=list(header(0));values[0]=2;model=native_resources(1);values[13]=model['work'];values[22]=model['parent_work']
        valid=b'OPLRSW01'+struct.pack('<34Q',*values)+struct.pack('<6Q',1,1,365,52,371,54)
        with patch('tests.compact_role_storage_reference.Context',side_effect=AssertionError('unadmitted reference entered')):
            for at in (8,8+13*8,280,288,296,304,312,320):
                changed=bytearray(valid);changed[at]^=1
                with self.subTest(offset=at),self.assertRaises(ValueError):
                    verify(bytes(changed),request,0,((0,0),(0,0)),'first',1)


if __name__=='__main__':unittest.main()

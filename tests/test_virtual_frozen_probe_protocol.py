import unittest
from tests.virtual_frozen_probe_protocol import parse, request, ProtocolError, MAX_BYTES

BOARD=(16,17,24,32,33)

def fixture(mode='EVAL', rows=True):
    forecast=[1,10,1,2,7,4,2,4,1,1,1,384,1,1,1,1,1]
    lines=['FROZEN_UPDATE_RESULT_V1','mode '+mode,
           'status '+('COMPLETE' if mode=='EVAL' else 'ADMITTED'),
           'scope PROOF9_FULL_V1','proposal UNIFORM','board 16 17 24 32 33',
           f'probe 1 {MAX_BYTES} {16384+16+16*MAX_BYTES} 512 384','forecast '+' '.join(map(str,forecast)),
           'setup 1 2 3 4 5','calls 0 0 0 0']
    if mode=='EVAL': lines+=['actual 1 2 3 4','regret_denominator a']
    lines+=['rows '+str(int(rows and mode=='EVAL'))]
    if rows and mode=='EVAL':
        lines+=['row 0 0 43 48 1 2','token call','average a 4',
                'action 0 1 fold -2 2','action 1 1 call 2 2','endrow']
    return ('\n'.join(lines+['end'])+'\n').encode()

class ProtocolTests(unittest.TestCase):
    def test_good_error_admit_and_full_row(self):
        self.assertEqual(parse(fixture())['rows'][0]['average_mass'],4)
        self.assertEqual(parse(fixture('ADMIT'))['status'],'ADMITTED')
        self.assertEqual(parse(b'FROZEN_UPDATE_ERROR_V1\nreason rejected\nend\n')['error'],'rejected')
        self.assertTrue(request('EVAL','UNIFORM',BOARD).endswith(b'\n'))
    def test_malformed_inputs_rejected(self):
        raw=fixture()
        variants=[raw+b'end\n',raw.replace(b'average a 4',b'average '+b'f'*97+b' 4'),
                  raw.replace(b'average a 4',b'average 0a 4'),raw.replace(b' -2 2',b' -0 2'),
                  raw.replace(b'action 1 1 call 2 2',b'action 2 1 call 2 2'),
                  raw.replace(b'action 1 1 call 2 2',b'action 1 1 call 1 2'),
                  raw.replace(b'average a 4',b'average a 5'),
                  raw.replace(b'action 0 1 fold -2 2',b'action 0 1 fold -2 1').replace(b'action 1 1 call 2 2',b'action 1 1 call 2 3'),
                  raw.replace(b'actual 1 2 3 4',b'actual 2 2 3 4'), raw.replace(b' 512 384\n',b' 511 384\n'),raw.replace(b'row 0 0 43 48',b'row 0 0 16 17'),
                  raw.replace(b'setup 1 2 3 4 5',b'setup 1 2 3 4'),raw[:-1],b'x'*(MAX_BYTES+1),b'\xff\n']
        for item in variants:
            with self.subTest(item=item[:100]):
                with self.assertRaises(ProtocolError):parse(item)
    def test_duplicate_keys_and_requests(self):
        raw=fixture().decode(); section=raw[raw.index('row 0 '):raw.index('endrow')+len('endrow\n')]
        duplicate=raw.replace('rows 1','rows 2').replace('endrow\nend\n','endrow\n'+section.replace('row 0 ','row 1 ',1)+'end\n')
        with self.assertRaisesRegex(ProtocolError,'duplicate'):parse(duplicate.encode())
        for board in ((17,16,24,32,33),(16,17,24,32,32),(16,17,24,32,99)):
            with self.assertRaises(ProtocolError):request('EVAL','UNIFORM',board)

if __name__=='__main__':unittest.main()

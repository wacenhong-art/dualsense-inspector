import unittest
import json
import subprocess
from unittest.mock import patch
import app

class EvidenceTests(unittest.TestCase):
    def evidence(self):
        return {'devices':[{'checks':{k:{'structure_ok':True} for k in ('calibration','pairing','firmware','input')}}],
                'official_app':{'status':'recognized','signature_valid':True,'controller_count':1,'firmware':['B-0000']}}

    def test_official_requires_verified_signature(self):
        r=self.evidence()
        r['official_app']['signature_valid']=False
        self.assertNotIn('较强',app.assessment(r)[0])

    def test_combined_evidence_is_not_authenticity_certificate(self):
        title,note=app.assessment(self.evidence())
        self.assertIn('较强证据',title)
        self.assertIn('换壳',note)

    def test_multiple_controllers_are_not_correlated(self):
        r=self.evidence()
        r['devices']*=2
        self.assertNotIn('较强',app.assessment(r)[0])

    def test_official_cannot_replace_usb_evidence(self):
        r=self.evidence();r['devices']=[]
        self.assertIn('证据不足',app.assessment(r)[0])

    def test_official_timeout_is_inconclusive(self):
        with patch('app.subprocess.run',side_effect=subprocess.TimeoutExpired('powershell',25)):
            self.assertEqual(app.official_probe()['status'],'unavailable')

    def test_official_child_process_environment(self):
        result={'status':'not_running','signature_valid':True}
        with patch.dict('os.environ',{'PSModulePath':'incompatible host modules'}):
            with patch('app.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(result).encode(),b'')) as run:
                self.assertEqual(app.official_probe(),result)
                self.assertNotIn('PSModulePath',run.call_args.kwargs['env'])

    def test_no_controller_is_not_counterfeit(self):
        self.assertIn('未发现', app.verdict([]))

    def test_partial_reports_cannot_pass(self):
        checks = {k:{'structure_ok':True} for k in ('calibration','pairing','firmware')}
        self.assertIn('证据不足',app.verdict([{'checks':checks}]))

    def test_complete_reports_still_not_certificate(self):
        checks = {k:{'structure_ok':True} for k in ('calibration','pairing','firmware','input')}
        self.assertIn('仍不能认证正版',app.verdict([{'checks':checks}]))

    def test_label_boundary(self):
        fields=app.label_fields('CFI-ZCT2N A1234567890123456 XXA1234567890123456XX')
        self.assertEqual(fields['models'],['CFI-ZCT2N'])
        self.assertEqual(fields['serial_candidates'],['A1234567890123456'])

    def test_access_denied_is_inconclusive(self):
        with patch('hid.device') as factory:
            factory.return_value.open_path.side_effect=OSError('denied')
            result=app.probe_device({'path':b'placeholder'})
            self.assertIn('无法打开',result['error'])
            factory.return_value.close.assert_called_once()

if __name__=='__main__':
    unittest.main()

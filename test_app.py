import unittest
from unittest.mock import patch
import app

class EvidenceTests(unittest.TestCase):
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

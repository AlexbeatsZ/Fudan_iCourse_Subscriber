"""Offline tests for UIS TOTP generation and the second-factor handshake."""
import base64
import unittest
from unittest.mock import Mock, patch

from src.api.webvpn import SecondFactorError, WebVPNSession, totp_code
from src.runtime import config


SEED = base64.b32encode(b"12345678901234567890").decode("ascii")


class TOTPTests(unittest.TestCase):
    def test_rfc6238_six_digit_vectors(self):
        self.assertEqual(totp_code(SEED, 59), "287082")
        self.assertEqual(totp_code(SEED, 1111111109), "081804")

    def test_empty_secret_fails_without_revealing_credentials(self):
        with self.assertRaisesRegex(SecondFactorError, "UIS_TOTP_SECRET"):
            totp_code("")

    def test_invalid_base32_secret(self):
        with self.assertRaisesRegex(SecondFactorError, "Base32"):
            totp_code("invalid*secret")

    def test_second_factor_http_request(self):
        vpn = WebVPNSession.__new__(WebVPNSession)
        vpn.session = Mock()
        response = Mock()
        response.json.return_value = {"code": 200, "loginToken": "ticket-hidden"}
        vpn.session.post.return_value = response
        challenge = {
            "moduleCodes": ["userAndOtp"],
            "requestNumber": "req-1",
            "authChainCode": "chain-1",
            "userName": "student",
        }
        with patch.object(config, "TOTP_SECRET", SEED), patch(
            "src.api.webvpn.totp_code", return_value="123456"
        ):
            result = vpn._authenticate_totp(
                challenge, "student", "lck", config.ICOURSE_BASE,
                "chain_type", via_vpn=True,
            )
        self.assertEqual(result["loginToken"], "ticket-hidden")
        args, kwargs = vpn.session.post.call_args
        self.assertIn("/idp/authn/authExecute", args[0])
        self.assertIn(config.WEBVPN_BASE, args[0])
        self.assertEqual(kwargs["json"]["authModuleCode"], "userAndOtp")
        self.assertEqual(kwargs["json"]["requestNumber"], "req-1")
        self.assertEqual(kwargs["json"]["authPara"]["otpCode"], "123456")

    def test_missing_second_factor_module_is_rejected(self):
        vpn = WebVPNSession.__new__(WebVPNSession)
        vpn.session = Mock()
        with self.assertRaises(SecondFactorError):
            vpn._authenticate_totp(
                {"moduleCodes": ["sms"], "requestNumber": "req",
                 "authChainCode": "chain"},
                "student", "lck", config.ICOURSE_BASE, "chain_type",
            )
        vpn.session.post.assert_not_called()

    def test_rejected_totp_stops_login(self):
        vpn = WebVPNSession.__new__(WebVPNSession)
        vpn.session = Mock()
        response = Mock()
        response.json.return_value = {"code": 401}
        vpn.session.post.return_value = response
        challenge = {
            "moduleCodes": ["userAndOtp"],
            "requestNumber": "req-2",
            "authChainCode": "chain-2",
        }
        with patch.object(config, "TOTP_SECRET", SEED), patch(
            "src.api.webvpn.totp_code", return_value="123456"
        ):
            with self.assertRaisesRegex(SecondFactorError, "TOTP authentication failed"):
                vpn._authenticate_totp(
                    challenge, "student", "lck", config.ICOURSE_BASE, "chain_type",
                )


if __name__ == "__main__":
    unittest.main()

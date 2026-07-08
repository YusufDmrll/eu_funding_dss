import unittest

from core.access_control import (
    ACCESS_CODE_ENV,
    access_gate_required,
    get_configured_access_code,
    verify_access_code,
)


class AccessControlTests(unittest.TestCase):
    def test_access_gate_is_off_when_no_code_is_configured(self) -> None:
        self.assertEqual(get_configured_access_code(env={}, secrets={}), "")
        self.assertFalse(access_gate_required(env={}, secrets={}))

    def test_environment_code_takes_precedence_over_secrets(self) -> None:
        code = get_configured_access_code(
            env={ACCESS_CODE_ENV: " env-code "},
            secrets={"access_code": "secret-code"},
        )

        self.assertEqual(code, "env-code")

    def test_streamlit_secret_keys_are_supported(self) -> None:
        self.assertEqual(
            get_configured_access_code(env={}, secrets={"access_code": "client-code"}),
            "client-code",
        )
        self.assertEqual(
            get_configured_access_code(env={}, secrets={"EU_FUNDING_ACCESS_CODE": "cloud-code"}),
            "cloud-code",
        )

    def test_missing_streamlit_secrets_object_does_not_crash(self) -> None:
        class MissingSecrets:
            def __len__(self):
                raise RuntimeError("No secrets found")

            def get(self, key, default=None):
                raise RuntimeError("No secrets found")

        self.assertEqual(get_configured_access_code(env={}, secrets=MissingSecrets()), "")
        self.assertFalse(access_gate_required(env={}, secrets=MissingSecrets()))

    def test_verify_access_code_is_strict_and_trims_input(self) -> None:
        self.assertTrue(verify_access_code(" client-code ", "client-code"))
        self.assertFalse(verify_access_code("wrong", "client-code"))
        self.assertFalse(verify_access_code("", "client-code"))
        self.assertFalse(verify_access_code("client-code", ""))


if __name__ == "__main__":
    unittest.main()

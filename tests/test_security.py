import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from polaris_guidance.security import Principal, current_principal, require_roles


class SecurityTests(unittest.TestCase):
    def test_demo_mode_uses_local_admin(self):
        with patch.dict("os.environ", {"POLARIS_AUTH_MODE": "demo"}):
            principal = current_principal(None)
        self.assertEqual(principal.role, "admin")

    def test_strict_mode_authenticates_configured_role(self):
        keys = {"secret": {"subject": "nurse-1", "role": "nurse"}}
        with patch.dict(
            "os.environ",
            {"POLARIS_AUTH_MODE": "strict", "POLARIS_API_KEYS_JSON": json.dumps(keys)},
        ):
            principal = current_principal("secret")
        self.assertEqual(principal, Principal(subject="nurse-1", role="nurse"))

    def test_strict_mode_rejects_unknown_key(self):
        with (
            patch.dict(
                "os.environ",
                {"POLARIS_AUTH_MODE": "strict", "POLARIS_API_KEYS_JSON": "{}"},
            ),
            self.assertRaises(HTTPException) as caught,
        ):
            current_principal("wrong")
        self.assertEqual(caught.exception.status_code, 401)

    def test_invalid_auth_configuration_fails_closed(self):
        with (
            patch.dict(
                "os.environ",
                {"POLARIS_AUTH_MODE": "strict", "POLARIS_API_KEYS_JSON": "not-json"},
            ),
            self.assertRaises(HTTPException) as caught,
        ):
            current_principal("key")
        self.assertEqual(caught.exception.status_code, 503)

    def test_role_dependency_rejects_wrong_role(self):
        dependency = require_roles("doctor")
        with self.assertRaises(HTTPException) as caught:
            dependency(Principal(subject="p1", role="patient"))
        self.assertEqual(caught.exception.status_code, 403)

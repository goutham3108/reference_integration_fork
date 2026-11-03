import unittest

from auth import make_password_record, verify_password


class TestPasswordRecords(unittest.TestCase):
    def test_password_is_stored_as_salted_hash(self):
        record = make_password_record("Dev@Example.com", "a-long-test-password")
        second_record = make_password_record("dev@example.com", "a-long-test-password")
        self.assertEqual(record["email"], "dev@example.com")
        self.assertNotIn("a-long-test-password", str(record))
        self.assertNotEqual(record["salt"], second_record["salt"])
        self.assertTrue(verify_password("a-long-test-password", record))

    def test_wrong_password_is_rejected(self):
        record = make_password_record("dev@example.com", "a-long-test-password")
        self.assertFalse(verify_password("wrong-password", record))

    def test_invalid_hash_record_is_rejected(self):
        self.assertFalse(verify_password("anything", {"salt": "not-hex"}))


if __name__ == "__main__":
    unittest.main()

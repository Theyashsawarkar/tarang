"""retry_worth: which failed connects tarang tries again."""
import unittest

from tarang import retry_worth


class Retry(unittest.TestCase):
    def test_wrong_password_said_at_once(self):
        self.assertFalse(retry_worth("Error: Connection activation failed: Secrets were required, but not provided", 4))

    def test_out_of_range_said_at_once(self):
        self.assertFalse(retry_worth("Error: No network with SSID 'Cafe' found.", 10))

    def test_timeout_retried(self):
        self.assertTrue(retry_worth("", 124))

    def test_dhcp_retried(self):
        self.assertTrue(retry_worth("Error: Connection activation failed: IP configuration could not be reserved", 4))

    def test_dropped_link_retried(self):
        self.assertTrue(retry_worth("Error: Connection activation failed: The base network connection was interrupted", 4))


if __name__ == "__main__":
    unittest.main()

"""A deliberate failure for issue 168: a test that needs Python 3.15.

The pinned image runs 3.15 and passes it. The host's Python, 3.14, does not.
This file never reaches main.
"""

import sys
import unittest


class NeedsPython315(unittest.TestCase):
    def test_runs_on_3_15(self):
        self.assertGreaterEqual(sys.version_info[:2], (3, 15))


if __name__ == "__main__":
    unittest.main()

"""The frozen-input gate compares exact UTF-8 bytes, including newlines."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import freeze_inputs


class FrozenBytesTests(unittest.TestCase):
    def test_exact_bytes_pass_and_newline_changes_fail(self):
        original = freeze_inputs.serialized().encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="frozen-bytes-") as directory:
            root = Path(directory)
            (root / "inputs").mkdir()
            target = root / "inputs" / "validation-cases.json"
            with patch.object(freeze_inputs, "ROOT", root), patch.object(
                sys, "argv", ["freeze_inputs.py", "--check"]
            ), contextlib.redirect_stdout(io.StringIO()):
                target.write_bytes(original)
                freeze_inputs.main()
                for damaged in (
                    original.replace(b"\n", b"\r\n"),
                    original.rstrip(b"\n"),
                    b"\xef\xbb\xbf" + original,
                ):
                    with self.subTest(length=len(damaged)):
                        target.write_bytes(damaged)
                        with self.assertRaisesRegex(SystemExit, "differs"):
                            freeze_inputs.main()


if __name__ == "__main__":
    unittest.main()

import unittest

from thonnycontrib.thonny_ai_assistant.thonny_ai_assistant_tool import (
    DEFAULT_MAX_TOKENS,
    MAX_OUTPUT_TOKENS,
    MIN_OUTPUT_TOKENS,
    normalize_output_tokens,
    snap_output_tokens,
)


class GenerationSettingsTests(unittest.TestCase):
    def test_output_tokens_are_clamped(self):
        self.assertEqual(normalize_output_tokens(-1), MIN_OUTPUT_TOKENS)
        self.assertEqual(
            normalize_output_tokens(MAX_OUTPUT_TOKENS + 1),
            MAX_OUTPUT_TOKENS,
        )
        self.assertEqual(
            normalize_output_tokens("invalid"),
            DEFAULT_MAX_TOKENS,
        )

    def test_output_tokens_snap_to_step(self):
        self.assertEqual(snap_output_tokens(16001), 16128)
        self.assertEqual(snap_output_tokens(0), MIN_OUTPUT_TOKENS)


if __name__ == "__main__":
    unittest.main()

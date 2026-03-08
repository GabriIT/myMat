from __future__ import annotations

import unittest

from myMAT_app.vector.answer import _parse_structured_answer


class AnswerStructuringTests(unittest.TestCase):
    def test_parse_structured_answer_strips_think_and_extracts_json(self) -> None:
        raw = """
<think>
internal reasoning that should never appear in UI
</think>
{
  "bullets": [
    "Point one from source.",
    "Point two from source."
  ],
  "answer_text": "Short summary from context."
}
""".strip()
        parsed = _parse_structured_answer(raw, question="What is covered?")
        self.assertEqual(parsed.prompt, "What is covered?")
        self.assertEqual(parsed.bullets, ["Point one from source.", "Point two from source."])
        self.assertEqual(parsed.answer_text, "Short summary from context.")

    def test_parse_structured_answer_fallback_omits_reasoning_tags(self) -> None:
        raw = "<think>hidden</think> This is a plain answer without JSON."
        parsed = _parse_structured_answer(raw, question="Question?")
        self.assertEqual(parsed.prompt, "Question?")
        self.assertNotIn("<think>", parsed.answer_text)
        self.assertNotIn("hidden", parsed.answer_text)
        self.assertTrue(parsed.bullets)


if __name__ == "__main__":
    unittest.main()

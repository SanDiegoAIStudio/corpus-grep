import re
import unittest

import support
from corpus_grep import collapse_rolling


def reference(text):
    """The substitution that collapse_rolling must give."""
    return re.sub(r"(\b[\w' ,.\-]{15,80}?\b)(?:\s*\1){1,5}", r"\1", text)


UNIT = "the market was full of people"
_BASE = " ".join("w%02d" % n for n in range(1, 12))
UNIT_80 = _BASE + "x" * (80 - len(_BASE))
UNIT_81 = _BASE + "x" * (81 - len(_BASE))
FIRST = "the first thing said"
SECOND = "a second thing said"

# (name, text, whether the substitution must change the text)
SAMPLES = [
    ("single repeat", "we went to " + UNIT + " " + UNIT + " and then we left", True),
    ("five repeats", "we went to " + " ".join([UNIT] * 6) + " and then we left", True),
    ("two separate runs",
     "first " + FIRST + " " + FIRST + " then something else entirely and " + SECOND
     + " " + SECOND + " done", True),
    ("run at the start", UNIT + " " + UNIT + " and the rest follows here", True),
    ("run at the end", "and the story ends with " + UNIT + " " + UNIT, True),
    ("no run", "nothing in this sentence is said twice, not even a little", False),
    ("run of 14 characters", "abcdefghijklmn|abcdefghijklmn", False),
    ("run of 81 characters", UNIT_81 + "|" + UNIT_81, False),
    ("run of 80 characters", UNIT_80 + " " + UNIT_80, True),
    ("run with punctuation", "well, that was fine. well, that was fine. well, that was fine. and so on", True),
    ("empty", "", False),
]


class CollapseRolling(unittest.TestCase):
    def test_unit_lengths_used_below_are_right(self):
        self.assertEqual(len(UNIT_80), 80)
        self.assertEqual(len(UNIT_81), 81)

    def test_collapsed_equals_the_reference_substitution(self):
        self.assertGreaterEqual(len(SAMPLES), 8)
        for name, text, changes in SAMPLES:
            with self.subTest(name):
                collapsed, _ = collapse_rolling(text)
                self.assertEqual(collapsed, reference(text))
                self.assertEqual(collapsed != text, changes)

    def test_origin_points_at_the_same_character(self):
        for name, text, _ in SAMPLES:
            with self.subTest(name):
                collapsed, origin = collapse_rolling(text)
                self.assertEqual(len(origin), len(collapsed))
                for i, ch in enumerate(collapsed):
                    self.assertEqual(text[origin[i]], ch)

    def test_origin_strictly_increases(self):
        for name, text, _ in SAMPLES:
            with self.subTest(name):
                _, origin = collapse_rolling(text)
                for a, b in zip(origin, origin[1:]):
                    self.assertLess(a, b)

    def test_text_without_a_run_maps_to_itself(self):
        text = "nothing in this sentence is said twice, not even a little"
        self.assertEqual(collapse_rolling(text), (text, list(range(len(text)))))

    def test_first_copy_of_a_run_is_the_one_kept(self):
        text = "we went to " + UNIT + " " + UNIT + " " + UNIT + " and then we left"
        collapsed, origin = collapse_rolling(text)
        at = collapsed.index(UNIT)
        self.assertEqual(origin[at], text.index(UNIT))

    def test_character_after_a_run_maps_past_the_dropped_copies(self):
        text = "we went to " + UNIT + " " + UNIT + " " + UNIT + " and then we left"
        collapsed, origin = collapse_rolling(text)
        self.assertEqual(collapsed, reference(text))
        after = collapsed.index("then")
        self.assertEqual(origin[after], text.index("then"))
        self.assertGreater(origin[after], text.index(UNIT) + 2 * len(UNIT))

    def test_two_runs_each_map_back_correctly(self):
        a, b = "the first thing said", "a second thing said"
        text = "xx %s %s yy %s %s zz" % (a, a, b, b)
        collapsed, origin = collapse_rolling(text)
        self.assertEqual(collapsed, reference(text))
        self.assertEqual(origin[collapsed.index("zz")], text.index("zz"))
        self.assertEqual(origin[collapsed.index(b)], text.index(b))


if __name__ == "__main__":
    unittest.main()

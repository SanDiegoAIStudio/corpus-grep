import os
import re
import tempfile
import unittest
from unittest import mock

import support
from support import run_main, run_measure, vtt, write

import corpus_grep
import measure


def sample_words():
    raw = support.read_text(support.SAMPLE_PATH)
    return measure.searched_text(raw, "vtt").split()


class Holder(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = holder.name

    def file(self, name, content):
        return write(self.tmp, name, content)


class OutputFormat(Holder):
    def test_lines_and_their_format_on_the_sample(self):
        result = run_measure(support.SAMPLE_PATH)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.split("\n")
        self.assertEqual(lines[-1], "")
        lines = lines[:-1]
        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[0], "file: MADEUP00001.en.vtt")
        m = re.fullmatch(r"caption lines: (\d+) as written, (\d+) after repeats are dropped",
                         lines[1])
        self.assertIsNotNone(m, lines[1])
        raw = support.read_text(support.SAMPLE_PATH)
        self.assertEqual(int(m.group(1)), len(corpus_grep.cue_lines(raw, collapse=False)))
        dropped = len(corpus_grep.cue_lines(raw, collapse=True))
        self.assertEqual(int(m.group(2)), dropped)
        self.assertLess(dropped, int(m.group(1)))
        words = len(sample_words())
        m = re.fullmatch(r"words: (\d+) \((\d+\.\d) per line\)", lines[2])
        self.assertIsNotNone(m, lines[2])
        self.assertEqual(int(m.group(1)), words)
        self.assertEqual(m.group(2), "%.1f" % (words / dropped))
        self.assertEqual(lines[3], "words  found by a plain line search")
        for line, length in zip(lines[4:], (4, 6, 8, 12)):
            self.assertRegex(line, r"^%5d  \d+%% \(\d+ of 200\)$" % length)

    def test_lengths_are_printed_in_the_order_given(self):
        result = run_measure(support.SAMPLE_PATH, "--words", "8,3,10", "--samples", "20")
        rows = result.stdout.split("\n")[4:7]
        self.assertEqual([r[:5] for r in rows], ["    8", "    3", "   10"])
        for row in rows:
            self.assertRegex(row, r"^ +\d+  \d+% \(\d+ of 20\)$")

    def test_percentage_is_rounded_half_up(self):
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha beta gamma delta epsilon"])))
        cases = [(1, 8, "13% (1 of 8)"), (1, 3, "33% (1 of 3)"), (2, 3, "67% (2 of 3)"),
                 (0, 5, "0% (0 of 5)"), (5, 5, "100% (5 of 5)"), (1, 200, "1% (1 of 200)"),
                 (3, 8, "38% (3 of 8)")]
        for hits, samples, text in cases:
            with self.subTest(text):
                answers = [True] * hits + [False] * (samples - hits)
                with mock.patch.object(measure, "found_in_a_line", side_effect=answers):
                    out = measure.measure(path, [2], samples, 1)
                self.assertEqual(out[-1], "    2  " + text)

    def test_raw_counts_for_a_rolling_file(self):
        line = "alpha beta gamma delta"
        cues = [("00:00:0%d.000" % i, [line]) for i in (1, 2, 3)]
        path = self.file("a.vtt", vtt(*cues))
        out = measure.measure(path, [4], 5, 1)
        self.assertEqual(out[0], "file: a.vtt")
        self.assertEqual(out[1], "caption lines: 3 as written, 1 after repeats are dropped")
        self.assertEqual(out[2], "words: 4 (4.0 per line)")
        self.assertEqual(out[4], "    4  100% (5 of 5)")

    def test_srt_file_is_accepted(self):
        path = self.file("a.srt", "1\n00:00:01,000 --> 00:00:02,000\nalpha beta gamma delta\n")
        self.assertEqual(run_measure(path, "--words", "4").returncode, 0)

    def test_extension_letter_case_is_ignored(self):
        path = self.file("a.VTT", vtt(("00:00:01.000", ["alpha beta gamma delta"])))
        self.assertEqual(run_measure(path, "--words", "4").returncode, 0)


class Seeds(Holder):
    def test_same_seed_same_output(self):
        a = run_measure(support.SAMPLE_PATH, "--seed", "7")
        b = run_measure(support.SAMPLE_PATH, "--seed", "7")
        self.assertEqual(a.stdout, b.stdout)
        default = run_measure(support.SAMPLE_PATH)
        explicit = run_measure(support.SAMPLE_PATH, "--seed", "1")
        self.assertEqual(default.stdout, explicit.stdout)

    def test_another_seed_draws_other_phrases(self):
        words = sample_words()
        one = measure.draw_phrases(words, [6, 8], 50, 1)
        two = measure.draw_phrases(words, [6, 8], 50, 2)
        self.assertNotEqual(one, two)
        self.assertEqual(one, measure.draw_phrases(words, [6, 8], 50, 1))

    def test_the_numbers_follow_the_seed(self):
        seen = {run_measure(support.SAMPLE_PATH, "--seed", str(s), "--words", "4,6").stdout
                for s in (1, 2, 3, 4, 5)}
        self.assertGreater(len(seen), 1)

    def test_phrases_are_drawn_from_one_generator_in_the_order_given(self):
        import random
        words = sample_words()
        rng = random.Random(3)
        expected = []
        for length in (5, 2):
            phrases = []
            for _ in range(4):
                start = rng.randrange(len(words) - length + 1)
                phrases.append(" ".join(words[start:start + length]))
            expected.append(phrases)
        self.assertEqual(measure.draw_phrases(words, [5, 2], 4, 3), expected)

    def test_phrases_have_the_asked_number_of_words_and_come_from_the_text(self):
        words = sample_words()
        text = " ".join(words)
        for length, phrases in zip((1, 4, 12), measure.draw_phrases(words, [1, 4, 12], 30, 9)):
            self.assertEqual(len(phrases), 30)
            for phrase in phrases:
                self.assertEqual(len(phrase.split(" ")), length)
                self.assertIn(phrase, text)

    def test_the_last_word_can_end_a_phrase(self):
        words = ["a1", "b2", "c3"]
        drawn = measure.draw_phrases(words, [3], 20, 1)[0]
        self.assertEqual(set(drawn), {"a1 b2 c3"})
        drawn = measure.draw_phrases(words, [2], 200, 1)[0]
        self.assertEqual(set(drawn), {"a1 b2", "b2 c3"})


class WhatCountsAsFound(Holder):
    def test_phrase_across_two_lines_is_not_found_and_one_inside_a_line_is(self):
        raw = vtt(("00:00:01.000", ["alpha beta gamma"]), ("00:00:02.000", ["delta epsilon zeta"]))
        lines = raw.split("\n")
        self.assertFalse(measure.found_in_a_line("gamma delta", lines))
        self.assertTrue(measure.found_in_a_line("beta gamma", lines))
        self.assertTrue(measure.found_in_a_line("alpha beta gamma", lines))

    def test_whole_file_phrase_over_two_lines_scores_zero(self):
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha beta gamma"]),
                                      ("00:00:02.000", ["delta epsilon zeta"])))
        out = measure.measure(path, [6], 5, 1)
        self.assertEqual(out[-1], "    6  0% (0 of 5)")

    def test_phrase_inside_one_line_scores_all(self):
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha beta gamma delta"])))
        self.assertEqual(measure.measure(path, [4], 5, 1)[-1], "    4  100% (5 of 5)")

    def test_lines_are_searched_as_written_on_disk(self):
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha &amp; beta gamma delta"])))
        out = measure.measure(path, [5], 5, 1)
        self.assertEqual(out[2], "words: 5 (5.0 per line)")
        self.assertEqual(out[-1], "    5  0% (0 of 5)")

    def test_markup_on_the_line_stops_a_match(self):
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha<c> beta</c> gamma delta epsilon"])))
        out = measure.measure(path, [5], 5, 1)
        self.assertEqual(out[-1], "    5  0% (0 of 5)")

    def test_header_and_timing_lines_are_part_of_the_lines_searched(self):
        lines = vtt(("00:00:01.000", ["alpha"])).split("\n")
        self.assertTrue(measure.found_in_a_line("WEBVTT", lines))


class AgreesWithGrep(Holder):
    def test_found_matches_grep_on_drawn_phrases(self):
        words = sample_words()
        raw = support.read_text(support.SAMPLE_PATH)
        lines = raw.split("\n")
        drawn = measure.draw_phrases(words, [2, 3, 4, 6, 8], 24, 11)
        phrases = [p for group in drawn for p in group]
        self.assertGreaterEqual(len(phrases), 40)
        found = 0
        for phrase in phrases:
            expected = support.grep_count(phrase, support.SAMPLE_PATH) > 0
            self.assertEqual(measure.found_in_a_line(phrase, lines), expected, phrase)
            found += expected
        self.assertGreater(found, 0)
        self.assertLess(found, len(phrases))

    def test_every_drawn_phrase_is_found_by_the_search(self):
        words = sample_words()
        write(self.tmp, "MADEUP00001.en.vtt", support.read_text(support.SAMPLE_PATH))
        drawn = measure.draw_phrases(words, [4, 8, 12], 20, 5)
        phrases = [p for group in drawn for p in group]
        self.assertGreaterEqual(len(phrases), 40)
        for phrase in phrases:
            code, out, err = run_main(corpus_grep, phrase, "--root", self.tmp,
                                      "--max", "1", "--context", "0")
            self.assertEqual(code, 0, (phrase, out, err))
            self.assertIn("=== MADEUP00001 ::", out)


class Failures(Holder):
    def run_cli(self, *args):
        result = run_measure(*args)
        self.assertEqual(result.returncode, 2, (args, result.stdout))
        self.assertEqual(result.stdout, "")
        lines = result.stderr.strip().split("\n")
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertTrue(lines[0].startswith("measure: "), lines[0])
        self.assertNotIn("Traceback", result.stderr)
        return lines[0]

    def test_file_that_cannot_be_read(self):
        message = self.run_cli(os.path.join(self.tmp, "missing.vtt"))
        self.assertIn("could not read", message)

    def test_file_that_is_not_readable_by_mode(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("file modes do not stop the superuser")
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha beta gamma delta"])))
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)
        self.assertIn("could not read", self.run_cli(path, "--words", "4"))

    def test_folder_given_as_the_file(self):
        self.assertIn("measure: ", self.run_cli(self.tmp))

    def test_file_that_is_not_vtt_or_srt(self):
        path = self.file("a.txt", "alpha beta gamma delta epsilon")
        self.assertIn("not a vtt or srt file", self.run_cli(path, "--words", "2"))
        path = self.file("noextension", "alpha beta gamma delta epsilon")
        self.assertIn("not a vtt or srt file", self.run_cli(path, "--words", "2"))

    def test_too_few_words(self):
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha beta gamma"])))
        message = self.run_cli(path, "--words", "2,4")
        self.assertIn("3 words", message)
        self.assertIn("4", message)
        self.assertEqual(run_measure(path, "--words", "3").returncode, 0)

    def test_file_with_no_speech(self):
        path = self.file("a.vtt", "WEBVTT\n\n")
        self.run_cli(path)

    def test_option_values_that_are_not_positive_whole_numbers(self):
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha beta gamma delta"])))
        for args in (("--words", "0"), ("--words", "x"), ("--words", "4,"), ("--words", ""),
                     ("--words", "4,-1"), ("--words", "2.5"), ("--samples", "0"),
                     ("--samples", "-3"), ("--samples", "x"), ("--seed", "0"),
                     ("--seed", "x"), ("--seed", "1.5")):
            with self.subTest(args):
                self.run_cli(path, *args)

    def test_missing_file_argument_and_unknown_option(self):
        result = run_measure()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        result = run_measure("--nope")
        self.assertEqual(result.returncode, 2)

    def test_main_returns_the_exit_code(self):
        path = self.file("a.vtt", vtt(("00:00:01.000", ["alpha beta gamma delta"])))
        self.assertEqual(run_main(measure, path, "--words", "4")[0], 0)
        self.assertEqual(run_main(measure, path, "--words", "9")[0], 2)
        self.assertEqual(run_main(measure)[0], 2)


class HelpText(unittest.TestCase):
    def test_help_says_what_is_measured_and_what_is_by_construction(self):
        result = run_measure("--help")
        self.assertEqual(result.returncode, 0)
        flat = " ".join(result.stdout.split())
        self.assertIn("by construction", flat)
        self.assertIn("plain line search", flat)
        for option in ("--words", "--samples", "--seed"):
            self.assertIn(option, flat)

    def test_module_docstring_says_the_same(self):
        flat = " ".join(measure.__doc__.split())
        self.assertIn("by construction", flat)
        self.assertIn("plain line search", flat)


if __name__ == "__main__":
    unittest.main()

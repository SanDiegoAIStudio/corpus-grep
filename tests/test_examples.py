import contextlib
import io
import itertools
import os
import re
import shlex
import subprocess
import sys
import unittest

import support

import corpus_grep
import make_captions

CAPTIONS = os.path.join(support.EXAMPLES, "captions")


def all_files(top):
    found = []
    for folder, names, files in os.walk(top):
        names[:] = sorted(n for n in names if n != "__pycache__")
        for name in sorted(files):
            if not name.endswith(".pyc"):
                found.append(os.path.join(folder, name))
    return found


class SampleCaptionFile(unittest.TestCase):
    def test_committed_file_is_what_build_vtt_returns(self):
        built = make_captions.build_vtt(support.talk_text()).encode("ascii")
        with open(support.SAMPLE_PATH, "rb") as fh:
            self.assertEqual(fh.read(), built)

    def test_build_is_deterministic(self):
        talk = support.talk_text()
        self.assertEqual(make_captions.build_vtt(talk), make_captions.build_vtt(talk))

    def test_stdout_mode_prints_the_same_bytes(self):
        result = subprocess.run(
            [sys.executable, os.path.join(support.EXAMPLES, "make_captions.py"), "--stdout"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(support.SAMPLE_PATH, "rb") as fh:
            self.assertEqual(result.stdout, fh.read())

    def test_unknown_argument_is_a_usage_error(self):
        result = subprocess.run(
            [sys.executable, os.path.join(support.EXAMPLES, "make_captions.py"), "--nope"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("usage", result.stderr)

    def test_header_and_note_block(self):
        text = support.read_text(support.SAMPLE_PATH)
        self.assertTrue(text.startswith("WEBVTT\nKind: captions\nLanguage: en\n\nNOTE "))
        head = text.split("\n\n")[1].split("\n")
        self.assertIn(len(head), (1, 2))
        self.assertIn("made up", " ".join(head))
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn("\r", text)

    def test_every_caption_line_is_shown_three_times(self):
        raw = support.read_text(support.SAMPLE_PATH)
        shown = [text for text, _ in corpus_grep.cue_lines(raw, collapse=False)]
        expected = [" ".join(words) for _, words in make_captions.caption_lines(support.talk_text())]
        expected = [t.replace("&amp;", "&").replace("&gt;", ">") for t in expected]
        runs = [(text, len(list(group))) for text, group in itertools.groupby(shown)]
        self.assertEqual([text for text, _ in runs], expected)
        self.assertEqual({count for _, count in runs}, {3})

    def test_every_cue_is_in_the_rolling_shape(self):
        raw = support.read_text(support.SAMPLE_PATH)
        blocks = raw.strip("\n").split("\n\n")[2:]
        self.assertGreater(len(blocks), 100)
        timing = re.compile(r"^\d\d:\d\d:\d\d\.\d{3} --> \d\d:\d\d:\d\d\.\d{3} align:start position:0%$")
        for block in blocks:
            lines = block.split("\n")
            self.assertRegex(lines[0], timing)
            self.assertIn(len(lines), (2, 3), block)
        self.assertEqual(blocks[0].split("\n")[1], " ")
        count = len(make_captions.caption_lines(support.talk_text()))
        self.assertEqual(len(blocks), 2 * count + 1)
        tagged = [b for b in blocks if "<c>" in b]
        multi = [w for _, w in make_captions.caption_lines(support.talk_text()) if len(w) > 1]
        self.assertEqual(len(tagged), len(multi))
        for block in tagged:
            self.assertRegex(block.split("\n")[2],
                             r"^\S+(<\d\d:\d\d:\d\d\.\d{3}><c> \S+</c>)+$")

    def test_flash_cue_lasts_ten_milliseconds(self):
        raw = support.read_text(support.SAMPLE_PATH)
        blocks = raw.strip("\n").split("\n\n")[2:]
        count = len(make_captions.caption_lines(support.talk_text()))
        flash = blocks[1:2 * count:2]
        self.assertEqual(len(flash), count)
        for block in flash:
            m = re.match(r"(\d\d):(\d\d):(\d\d)\.(\d{3}) --> (\d\d):(\d\d):(\d\d)\.(\d{3})", block)
            a = [int(x) for x in m.groups()]
            start = ((a[0] * 60 + a[1]) * 60 + a[2]) * 1000 + a[3]
            end = ((a[4] * 60 + a[5]) * 60 + a[6]) * 1000 + a[7]
            self.assertEqual(end - start, 10, block)

    def test_lines_are_short_and_filled_greedily(self):
        lines = make_captions.caption_lines(support.talk_text())
        self.assertGreater(len(lines), 60)
        for (_, words), (_, following) in zip(lines, lines[1:]):
            self.assertLessEqual(len(" ".join(words)), 38)
            if following[0] != "&gt;&gt;":
                self.assertGreater(len(" ".join(words + [following[0]])), 38)

    def test_words_are_lower_case_without_sentence_punctuation(self):
        for _, words in make_captions.caption_lines(support.talk_text()):
            for word in words:
                self.assertRegex(word, r"^(&gt;&gt;|[a-z0-9'&;]+)$")
        words = [w for _, ws in make_captions.caption_lines(support.talk_text()) for w in ws]
        self.assertIn("&amp;", words)
        self.assertIn("&gt;&gt;", words)

    def test_each_word_takes_four_tenths_of_a_second(self):
        lines = make_captions.caption_lines(support.talk_text())
        for (start, words), (following, _) in zip(lines, lines[1:]):
            self.assertEqual(following - start, 400 * len(words))
        self.assertEqual(lines[0][0], 0)

    def test_speaker_change_starts_a_caption_line(self):
        talk = support.talk_text()
        changes = len([p for p in re.split(r"\n\s*\n", talk) if p.startswith(">>")])
        lines = make_captions.caption_lines(talk)
        starts = [words for _, words in lines if words[0] == "&gt;&gt;"]
        self.assertEqual(len(starts), changes)

    def test_search_finds_the_sample_through_the_command(self):
        result = support.cli("windowsill", "--root", CAPTIONS, "--max", "1", cwd=support.ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("=== MADEUP00001 :: Window herbs, a made-up talk  [00:00:", result.stdout)


class TalkFile(unittest.TestCase):
    def test_length_and_shape(self):
        talk = support.talk_text()
        words = talk.split()
        self.assertGreaterEqual(len(words), 520)
        self.assertLessEqual(len(words), 700)
        paragraphs = [p for p in re.split(r"\n\s*\n", talk) if p.strip()]
        self.assertGreaterEqual(len([p for p in paragraphs if p.startswith(">>")]), 2)
        self.assertIn(" & ", talk)

    def test_a_long_sentence_is_said_twice_far_apart(self):
        talk = " ".join(support.talk_text().replace(">>", " ").split())
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", talk) if s.strip()]
        seen = {}
        far = []
        position = 0
        for sentence in sentences:
            count = len(sentence.split())
            if count >= 8:
                seen.setdefault(sentence, []).append(position)
            position += count
        for sentence, places in seen.items():
            if len(places) == 2 and places[1] - places[0] >= 100:
                far.append(sentence)
        self.assertEqual(len(far), 1, far)

    def test_ids_in_examples_are_made_up(self):
        for path in all_files(support.EXAMPLES):
            text = support.read_text(path)
            for found in re.findall(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{11}(?![A-Za-z0-9_-])", text):
                if found.upper() == found and any(c.isdigit() for c in found):
                    self.assertTrue(found.startswith("MADEUP"), (path, found))


class OtherSampleFiles(unittest.TestCase):
    def test_srt_clip_has_about_ten_cues_and_no_repeats(self):
        raw = support.read_text(os.path.join(CAPTIONS, "workshop-tour.srt"))
        lines = corpus_grep.cue_lines(raw, collapse=False)
        self.assertGreaterEqual(raw.count(" --> "), 8)
        self.assertLessEqual(raw.count(" --> "), 12)
        texts = [text for text, _ in lines]
        self.assertEqual(len(texts), len(set(texts)))
        self.assertEqual(texts, [text for text, _ in corpus_grep.cue_lines(raw, collapse=True)])
        self.assertIn(" --> ", raw)
        self.assertRegex(raw, r"\d\d:\d\d:\d\d,\d{3} -->")

    def test_titles_file_holds_one_made_up_row_with_a_tab(self):
        data = support.read_text(os.path.join(CAPTIONS, "titles.tsv"))
        rows = [r for r in data.split("\n") if r]
        self.assertEqual(len(rows), 1)
        columns = rows[0].split("\t")
        self.assertEqual(len(columns), 2)
        self.assertEqual(columns[0], "MADEUP00001")
        self.assertTrue(columns[1].strip())
        self.assertNotEqual(columns[1], columns[0])

    def test_plain_text_sample_exists_and_is_short(self):
        text = support.read_text(os.path.join(CAPTIONS, "reading-list.txt"))
        self.assertGreater(len(text.split()), 10)
        self.assertLess(len(text), 2000)

    def test_example_folder_has_exactly_the_files_the_readme_names(self):
        names = sorted(os.path.relpath(p, support.EXAMPLES).replace(os.sep, "/")
                       for p in all_files(support.EXAMPLES))
        self.assertEqual(names, [
            "captions/MADEUP00001.en.vtt", "captions/reading-list.txt",
            "captions/titles.tsv", "captions/workshop-tour.srt",
            "make_captions.py", "talk.txt"])


class PublishedText(unittest.TestCase):
    def published(self):
        paths = []
        for name in ("README.md", "LICENSE", ".gitignore", "corpus_grep.py", "measure.py"):
            paths.append(os.path.join(support.ROOT, name))
        paths.extend(all_files(support.EXAMPLES))
        paths.extend(p for p in all_files(os.path.join(support.ROOT, "tests")))
        return paths

    def test_no_file_under_examples_holds_a_character_outside_ascii(self):
        paths = all_files(support.EXAMPLES)
        self.assertGreaterEqual(len(paths), 6)
        for path in paths:
            with open(path, "rb") as fh:
                data = fh.read()
            data.decode("ascii")

    def test_published_files_are_plain_ascii(self):
        for path in self.published():
            with self.subTest(os.path.basename(path)):
                with open(path, "rb") as fh:
                    fh.read().decode("ascii")


class Readme(unittest.TestCase):
    def test_sections_come_in_the_asked_order(self):
        text = support.read_text(support.README_PATH)
        headings = re.findall(r"^## (.+)$", text, re.M)
        self.assertEqual(headings, [
            "What you get", "Quick start", "Why plain grep misses", "Search",
            "Measure your own captions", "Get caption files", "Tests", "Limits",
            "License", "Built at San Diego AI Studio"])
        self.assertTrue(text.startswith("# corpus-grep\n"))

    def run_and_compare(self, block):
        out, argv = support.run_block(block)
        self.assertEqual(out.rstrip("\n").split("\n"), block[1:], argv)

    def test_what_you_get_blocks_equal_fresh_runs(self):
        blocks = support.readme_section("What you get")
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            self.run_and_compare(block)
        self.assertTrue(blocks[0][0].startswith("$ python3 corpus_grep.py "))
        self.assertTrue(blocks[1][0].startswith("$ grep -c -F "))
        self.assertEqual(blocks[1][1:], ["0"])

    def test_readme_phrase_is_long_and_plain_grep_does_not_find_it(self):
        blocks = support.readme_section("What you get")
        search = shlex.split(blocks[0][0][2:])
        phrase = search[2]
        self.assertGreaterEqual(len(phrase.split()), 8)
        self.assertEqual(support.grep_count(phrase, support.SAMPLE_PATH), 0)
        grep_argv = shlex.split(blocks[1][0][2:])
        self.assertEqual(grep_argv[-2], phrase)
        self.assertEqual(grep_argv[-1], "examples/captions/MADEUP00001.en.vtt")
        out = "\n".join(blocks[0][1:])
        self.assertEqual(len([l for l in blocks[0] if l.startswith("=== ")]), 1)
        self.assertRegex(out, r"\[\d\d:\d\d:\d\d\]  https://www\.youtube\.com/watch\?v=MADEUP00001&t=\d+s")

    def test_measure_block_equals_a_fresh_run(self):
        blocks = [b for b in support.readme_section("Why plain grep misses")
                  if b[0].startswith("$ python3 measure.py")]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][0], "$ python3 measure.py examples/captions/MADEUP00001.en.vtt")
        self.run_and_compare(blocks[0])

    def test_every_pasted_command_block_equals_a_fresh_run(self):
        text = support.read_text(support.README_PATH)
        titles = re.findall(r"^## (.+)$", text, re.M)
        checked = 0
        for title in titles:
            for block in support.readme_section(title):
                first = block[0]
                if first.startswith(("$ python3 corpus_grep.py ", "$ python3 measure.py ")):
                    with self.subTest(first):
                        self.run_and_compare(block)
                    checked += 1
        self.assertGreaterEqual(checked, 5)

    def test_shape_block_is_a_run_of_lines_of_the_sample_file(self):
        shape = [b for b in support.readme_section("Why plain grep misses")
                 if not b[0].startswith("$ ")]
        self.assertEqual(len(shape), 1)
        sample = support.read_text(support.SAMPLE_PATH).split("\n")
        block = shape[0]
        starts = [i for i in range(len(sample) - len(block) + 1)
                  if sample[i:i + len(block)] == block]
        self.assertEqual(len(starts), 1)

    def test_collapse_claim_in_the_search_section_is_true(self):
        flat = " ".join(support.read_text(support.README_PATH).split())
        self.assertIn("`gets high` gives 4 hits by default and 6 with `--no-collapse`", flat)
        for extra, expected in (([], 4), (["--no-collapse"], 6)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = corpus_grep.main(["gets high", "--root", support.EXAMPLES] + extra)
            self.assertEqual(code, 0)
            self.assertIn("%d hits across" % expected, out.getvalue())

    def test_past_measurement_is_quoted_in_the_asked_words(self):
        text = support.read_text(support.README_PATH)
        flat = " ".join(text.split())
        for needle in ("5,700 words", "840 caption lines", "200 random phrases per length",
                       "62%", "24%", "4%", "0%"):
            self.assertIn(needle, flat)

    def test_pasted_blocks_have_no_home_folder_path(self):
        text = support.read_text(support.README_PATH)
        self.assertNotRegex(text, r"/(Users|home[A-Za-z])")

    def test_one_outside_link_only(self):
        text = support.read_text(support.README_PATH)
        links = set(re.findall(r"https?://[^\s)>\]]+", text))
        outside = {l for l in links if "youtube.com/watch?v=MADEUP" not in l}
        self.assertEqual(outside, {"https://sandiegoaistudio.com/projects"})


if __name__ == "__main__":
    unittest.main()

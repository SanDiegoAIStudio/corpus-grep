import html
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import support
from support import cli, header_lines, vtt, write

import corpus_grep
import make_captions

LINES = None


def caption_lines():
    global LINES
    if LINES is None:
        LINES = make_captions.caption_lines(support.talk_text())
    return LINES


class SearchCase(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = holder.name

    def make(self, relative, content):
        return write(self.tmp, relative, content)

    def search(self, pattern, *args, root=None):
        return cli(pattern, "--root", root or self.tmp, *args)


class SampleCaptions(SearchCase):
    def setUp(self):
        super().setUp()
        self.sample = self.make("MADEUP00001.en.vtt",
                                make_captions.build_vtt(support.talk_text()))

    def test_phrase_across_three_caption_lines_found_once_with_its_time(self):
        phrase = "growing herbs on a kitchen windowsill and i promise you do not need"
        self.assertEqual(len(phrase.split()), 13)
        texts = [html.unescape(" ".join(words)) for _, words in caption_lines()]
        self.assertFalse(any(phrase in t for t in texts))
        joined = " ".join(texts)
        at = joined.find(phrase)
        self.assertNotEqual(at, -1)
        starts, offset = [], 0
        for t in texts:
            starts.append(offset)
            offset += len(t) + 1

        def line_of(pos):
            return max(i for i, begin in enumerate(starts) if begin <= pos)

        crossed = line_of(at + len(phrase) - 1) - line_of(at) + 1
        self.assertGreaterEqual(crossed, 3)
        self.assertEqual(support.grep_count(phrase, self.sample), 0)
        expected = support.caption_oracle(caption_lines(), phrase)
        self.assertEqual(len(expected), 1)
        result = self.search(phrase)
        self.assertEqual(result.returncode, 0, result.stderr)
        heads = header_lines(result.stdout)
        self.assertEqual(len(heads), 1)
        self.assertIn("[00:00:%02d]" % expected[0], heads[0])
        self.assertIn("&t=%ds" % expected[0], heads[0])
        self.assertIn("https://www.youtube.com/watch?v=MADEUP00001&t=", heads[0])
        self.assertIn("\n1 hits across 1 sources / 1 files\n", result.stdout)

    def test_a_sentence_said_twice_gives_two_hits_with_two_correct_times(self):
        phrase = "water the seedlings early in the morning before the sun gets high"
        self.assertGreaterEqual(len(phrase.split()), 8)
        expected = support.caption_oracle(caption_lines(), phrase)
        self.assertEqual(len(expected), 2)
        self.assertNotEqual(expected[0], expected[1])
        result = self.search(phrase, "--no-links")
        heads = header_lines(result.stdout)
        self.assertEqual(len(heads), 2)
        for head, seconds in zip(heads, expected):
            self.assertTrue(head.endswith("[%s]" % corpus_grep.format_time(seconds)), head)
        self.assertIn("\n2 hits across 1 sources / 1 files\n", result.stdout)

    def test_no_collapse_shows_the_repeats(self):
        collapsed = self.search("growing herbs")
        self.assertIn("\n1 hits across", collapsed.stdout)
        raw = self.search("growing herbs", "--no-collapse")
        self.assertIn("\n3 hits across", raw.stdout)

    def test_phrase_and_grep_agree_on_a_phrase_inside_one_line(self):
        result = self.search("workshop")
        self.assertEqual(result.returncode, 0)
        self.assertGreater(support.grep_count("workshop", self.sample), 0)


class Timing(SearchCase):
    def test_hit_after_forty_entities_has_the_right_time(self):
        cues = [("00:00:%02d.000" % (i + 1), ["fish &amp; chips order %d" % i])
                for i in range(45)]
        cues.append(("00:01:40.000", ["the needle phrase sits here"]))
        self.make("MADEUP00007.en.vtt", vtt(*cues))
        result = self.search("needle phrase")
        self.assertEqual(header_lines(result.stdout)[0].split("  ")[1], "[00:01:40]")

    def test_time_past_one_hour_in_the_link(self):
        self.make("MADEUP00008.en.vtt", vtt(("01:02:03.000", ["somewhere deep in the talk"])))
        result = self.search("deep in")
        head = header_lines(result.stdout)[0]
        self.assertIn("[01:02:03]", head)
        self.assertTrue(head.endswith("&t=3723s"), head)

    def test_collapsed_run_before_the_match_does_not_shift_the_time(self):
        run = "the market was full of people"
        cues = [("00:00:01.000", [run]), ("00:00:02.000", [run]), ("00:00:03.000", [run]),
                ("00:00:04.000", ["and then the target word came"])]
        self.make("MADEUP00009.en.vtt", vtt(*cues))
        result = self.search("target word", "--no-collapse")
        self.assertIn("[00:00:04]", result.stdout)
        result = self.search("target word")
        self.assertIn("[00:00:04]", result.stdout)

    def test_match_across_a_collapsed_run_gets_a_time(self):
        a = "the first thing said"
        text = "xx %s %s yy" % (a, a)
        self.make("MADEUP00010.en.vtt", vtt(("00:00:07.000", [text])))
        result = self.search("said yy")
        self.assertIn("[00:00:07]", result.stdout)


class Patterns(SearchCase):
    def hits(self, result):
        return int(result.stdout.split(" hits across")[0].split("\n")[-1])

    def test_no_collapse_keeps_a_repeated_phrase_in_a_plain_file(self):
        unit = "the market was full of people"
        self.make("repeat.txt", "we went to " + " ".join([unit] * 3) + " and then left")
        collapsed = self.search("market was full", "--context", "0")
        self.assertIn("\n1 hits across 1 sources / 1 files\n", collapsed.stdout)
        plain = self.search("market was full", "--context", "0", "--no-collapse")
        self.assertIn("\n3 hits across 1 sources / 1 files\n", plain.stdout)

    def test_literal_does_not_treat_the_pattern_as_a_regular_expression(self):
        self.make("a.txt", "abc and a.c are different")
        literal = self.search("a.c", "--context", "0")
        self.assertEqual(self.hits(literal), 1)
        self.assertIn("    a.c\n", literal.stdout)
        regex = self.search("a.c", "--regex", "--context", "0")
        self.assertEqual(self.hits(regex), 2)

    def test_regex_alternation(self):
        self.make("a.txt", "close to the money and closer to the deal")
        result = self.search("clos(e|er) to the (money|deal)", "--regex", "--context", "0")
        self.assertEqual(self.hits(result), 2)

    def test_literal_with_doubled_space_and_padding(self):
        self.make("a.txt", "in the morning light we left")
        for pattern in ("the  morning", "  the morning  ", "the\tmorning"):
            with self.subTest(pattern):
                result = self.search(pattern, "--context", "0")
                self.assertEqual(result.returncode, 0)
                self.assertIn("    the morning\n", result.stdout)

    def test_case_is_ignored_unless_asked(self):
        self.make("a.txt", "Hello and hello and HELLO")
        self.assertEqual(self.hits(self.search("hello")), 3)
        self.assertEqual(self.hits(self.search("hello", "--case-sensitive")), 1)
        self.assertEqual(self.hits(self.search("Hello", "--case-sensitive")), 1)

    def test_empty_pattern(self):
        self.make("a.txt", "text")
        for pattern in ("", "   "):
            with self.subTest(repr(pattern)):
                result = self.search(pattern)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "corpus-grep: bad pattern: empty pattern\n")

    def test_empty_regex(self):
        self.make("a.txt", "text")
        result = self.search("", "--regex")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "corpus-grep: bad pattern: empty pattern\n")

    def test_bad_regular_expression(self):
        self.make("a.txt", "text")
        result = self.search("(unclosed", "--regex")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.strip().split("\n")), 1)
        self.assertTrue(result.stderr.startswith("corpus-grep: bad pattern: "))
        self.assertNotIn("Traceback", result.stderr)

    def test_zero_length_matches_are_ignored(self):
        self.make("a.txt", "abbc")
        result = self.search("x*", "--regex")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no matches for 'x*'", result.stdout)
        result = self.search("b*", "--regex", "--context", "0")
        self.assertEqual(self.hits(result), 1)
        self.assertIn("    bb\n", result.stdout)

    def test_context_zero_and_ten(self):
        self.make("a.txt", "0123456789 alpha BETA gamma 0123456789 and more")
        zero = self.search("beta", "--context", "0")
        self.assertIn("\n    BETA\n", zero.stdout)
        ten = self.search("beta", "--context", "10")
        self.assertIn("\n    789 alpha BETA gamma 012\n", ten.stdout)

    def test_context_at_the_ends_of_the_text(self):
        self.make("a.txt", "beta is first and last is beta")
        result = self.search("beta", "--context", "5")
        self.assertIn("\n    beta is f\n", result.stdout)
        self.assertIn("\n    t is beta\n", result.stdout)

    def test_max_cuts_the_list_and_says_so(self):
        self.make("a.txt", "needle one and needle two and needle three")
        result = self.search("needle", "--max", "1")
        self.assertEqual(len(header_lines(result.stdout)), 1)
        self.assertIn("\n3 hits across 1 sources / 1 files (showing 1)\n", result.stdout)
        full = self.search("needle", "--max", "3")
        self.assertEqual(len(header_lines(full.stdout)), 3)
        self.assertNotIn("showing", full.stdout)

    def test_invalid_option_values(self):
        self.make("a.txt", "needle")
        for args in (("--context", "-1"), ("--max", "0"), ("--max", "x"), ("--context", "1.5")):
            with self.subTest(args):
                result = self.search("needle", *args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_no_root_is_a_usage_error(self):
        result = cli("needle")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_main_returns_the_exit_code(self):
        self.make("a.txt", "needle")
        self.assertEqual(support.run_main(corpus_grep, "needle", "--root", self.tmp)[0], 0)
        self.assertEqual(support.run_main(corpus_grep, "zzz", "--root", self.tmp)[0], 1)
        self.assertEqual(support.run_main(corpus_grep, "needle")[0], 2)


class OutputFormat(SearchCase):
    def test_exact_output_with_title_time_and_link(self):
        self.make("MADEUP00005.en.vtt", vtt(("00:00:03.000", ["the end of the line"])))
        self.make("titles.tsv", "MADEUP00005\tThe Title\n")
        result = self.search("end of")
        expected = ("\n=== MADEUP00005 :: The Title  [00:00:03]  "
                    "https://www.youtube.com/watch?v=MADEUP00005&t=3s\n"
                    "    the end of the line\n"
                    "\n1 hits across 1 sources / 1 files\n")
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.returncode, 0)

    def test_label_is_the_file_name_without_a_title(self):
        self.make("MADEUP00005.en.vtt", vtt(("00:00:03.000", ["the end of the line"])))
        result = self.search("end of")
        self.assertTrue(result.stdout.startswith("\n=== MADEUP00005 :: MADEUP00005.en.vtt  [00:00:03]  "))

    def test_no_match_line_and_exit_one(self):
        self.make("a.txt", "text")
        result = self.search("zzz")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "no matches for 'zzz' across 1 files in 1 root(s)\n")
        self.assertEqual(result.stderr, "")

    def test_no_links(self):
        self.make("MADEUP00005.en.vtt", vtt(("00:00:03.000", ["the end of the line"])))
        result = self.search("end of", "--no-links")
        head = header_lines(result.stdout)[0]
        self.assertTrue(head.endswith("[00:00:03]"), head)
        self.assertNotIn("youtube", result.stdout)

    def test_no_link_for_a_name_without_an_id(self):
        self.make("workshop-tour.srt", "1\n00:00:03,000 --> 00:00:04,000\nthe end of the line\n")
        result = self.search("end of")
        head = header_lines(result.stdout)[0]
        self.assertEqual(head, "=== workshop-tour :: workshop-tour.srt  [00:00:03]")

    def test_plain_file_has_no_time_and_no_link(self):
        self.make("MADEUP00005.txt", "the end of the line")
        result = self.search("end of")
        self.assertEqual(header_lines(result.stdout), ["=== MADEUP00005 :: MADEUP00005.txt"])

    def test_list_only(self):
        self.make("MADEUP00005.en.vtt", vtt(("00:00:03.000", ["the end of the line"])))
        self.make("notes.txt", "the end of notes, the end of days")
        self.make("other.txt", "nothing")
        self.make("titles.tsv", "MADEUP00005\tThe Title\n")
        result = self.search("end of", "--list-only")
        self.assertEqual(result.stdout,
                         "MADEUP00005\tThe Title\nnotes\t\n"
                         "\n3 hits across 2 sources / 3 files\n")
        self.assertEqual(result.returncode, 0)

    def test_list_only_ignores_max_and_shows_no_cut(self):
        for name in ("a", "b", "c"):
            self.make(name + ".txt", "the end of it")
        result = self.search("end of", "--list-only", "--max", "1")
        self.assertEqual(result.stdout, "a\t\nb\t\nc\t\n\n3 hits across 3 sources / 3 files\n")

    def test_summary_counts_sources_and_files(self):
        self.make("a.txt", "needle in a")
        self.make("b.txt", "needle in b")
        self.make("c.txt", "nothing")
        result = self.search("needle")
        self.assertIn("\n2 hits across 2 sources / 3 files\n", result.stdout)


class VideoIds(SearchCase):
    def test_bracketed_id_with_a_title_that_holds_dots(self):
        name = "Some talk, part 2. Notes on v1.5. [MADEUP00002].en.vtt"
        self.make(name, vtt(("00:02:00.000", ["a line with the phrase inside"])))
        result = self.search("the phrase")
        head = header_lines(result.stdout)[0]
        self.assertEqual(head, "=== MADEUP00002 :: " + name
                         + "  [00:02:00]  https://www.youtube.com/watch?v=MADEUP00002&t=120s")

    def test_bracketed_id_gets_its_title_from_the_tsv(self):
        self.make("Talk. [MADEUP00002].en.vtt", vtt(("00:00:05.000", ["a line with the phrase"])))
        self.make("titles.tsv", "MADEUP00002\tThe Bracket Title\n")
        head = header_lines(self.search("the phrase").stdout)[0]
        self.assertTrue(head.startswith("=== MADEUP00002 :: The Bracket Title  [00:00:05]"), head)

    def test_bracket_must_end_the_name_apart_from_dot_pieces(self):
        self.assertEqual(corpus_grep.video_id("Talk [MADEUP00002] extra.en.vtt"), None)
        self.assertEqual(corpus_grep.video_id("Talk [MADEUP00002].en.vtt"), "MADEUP00002")
        self.assertEqual(corpus_grep.video_id("Talk [MADEUP00002].vtt"), "MADEUP00002")
        self.assertEqual(corpus_grep.video_id("Talk [SHORT].vtt"), None)

    def test_first_form_id(self):
        self.assertEqual(corpus_grep.video_id("MADEUP00001.en.vtt"), "MADEUP00001")
        self.assertEqual(corpus_grep.video_id("MADEUP00001"), "MADEUP00001")
        self.assertEqual(corpus_grep.video_id("MADEUP0000.en.vtt"), None)
        self.assertEqual(corpus_grep.video_id("MADEUP000011.en.vtt"), None)
        self.assertEqual(corpus_grep.video_id("MADEUP 0001.en.vtt"), None)
        self.assertEqual(corpus_grep.video_id("a_b-c_d-e_f.txt"), "a_b-c_d-e_f")

    def test_source_name(self):
        self.assertEqual(corpus_grep.source_name("MADEUP00001.en.vtt"), "MADEUP00001")
        self.assertEqual(corpus_grep.source_name("Talk [MADEUP00002].en.vtt"), "MADEUP00002")
        self.assertEqual(corpus_grep.source_name("workshop-tour.srt"), "workshop-tour")
        self.assertEqual(corpus_grep.source_name("workshop-tour.en.srt"), "workshop-tour")
        self.assertEqual(corpus_grep.source_name("workshop-tour.pt-BR.vtt"), "workshop-tour")
        self.assertEqual(corpus_grep.source_name("reading-list.txt"), "reading-list")
        self.assertEqual(corpus_grep.source_name("my.notes.txt"), "my.notes")
        self.assertEqual(corpus_grep.source_name("tour.en.txt"), "tour.en")
        self.assertEqual(corpus_grep.source_name("tour.EN.VTT"), "tour")
        self.assertEqual(corpus_grep.source_name("noext"), "noext")


class Titles(SearchCase):
    def test_title_is_the_second_column_and_the_first_one_found_wins(self):
        self.make("MADEUP00003.txt", "the phrase here")
        self.make("a/one.tsv", "id\ttitle\nMADEUP00003\tFirst Title\textra column\n"
                               "MADEUP00003\tSecond Title\n")
        self.make("b/two.tsv", "MADEUP00003\tThird Title\n")
        result = self.search("the phrase")
        self.assertEqual(header_lines(result.stdout), ["=== MADEUP00003 :: First Title"])

    def test_rows_that_do_not_count(self):
        self.make("MADEUP00003.txt", "the phrase here")
        self.make("MADEUP00004.txt", "the phrase there")
        self.make("t.tsv", "MADEUP00003\tMADEUP00003\n"
                           "MADEUP00004\t\n"
                           "short\tA Title\n"
                           "MADEUP000044\tToo Long\n"
                           "only one column\n")
        heads = header_lines(self.search("the phrase").stdout)
        self.assertEqual(heads, ["=== MADEUP00003 :: MADEUP00003.txt",
                                 "=== MADEUP00004 :: MADEUP00004.txt"])

    def test_crlf_title_file_and_title_is_trimmed(self):
        self.make("MADEUP00003.txt", "the phrase here")
        self.make("t.tsv", "MADEUP00003\t  Padded Title  \r\n")
        self.assertEqual(header_lines(self.search("the phrase").stdout),
                         ["=== MADEUP00003 :: Padded Title"])

    def test_tsv_is_not_searched(self):
        self.make("t.tsv", "MADEUP00003\tthe phrase in a title\n")
        result = self.search("the phrase")
        self.assertEqual(result.returncode, 1)
        self.assertIn("across 0 files", result.stdout)

    def test_title_file_in_a_second_root_is_used(self):
        a = os.path.join(self.tmp, "a")
        b = os.path.join(self.tmp, "b")
        write(a, "MADEUP00003.txt", "the phrase here")
        write(b, "t.tsv", "MADEUP00003\tFrom Root B\n")
        result = cli("the phrase", "--root", a, "--root", b)
        self.assertEqual(header_lines(result.stdout), ["=== MADEUP00003 :: From Root B"])


class FileRules(SearchCase):
    def test_html_with_a_txt_twin_is_skipped(self):
        self.make("page.html", "<p>the phrase in a page</p>")
        self.make("page.txt", "the phrase in the text")
        result = self.search("the phrase")
        self.assertEqual(header_lines(result.stdout), ["=== page :: page.txt"])
        self.assertIn("1 hits across 1 sources / 1 files", result.stdout)

    def test_html_without_a_twin_is_searched_with_tags_removed(self):
        self.make("page.html", "<p>the phrase</p><p>in a page</p>")
        self.make("other.txt", "unrelated")
        result = self.search("phrase in a page")
        self.assertEqual(header_lines(result.stdout), ["=== page :: page.html"])

    def test_html_twin_in_another_folder_does_not_count(self):
        self.make("a/page.html", "<p>the phrase in a page</p>")
        self.make("b/page.txt", "unrelated")
        self.assertEqual(self.search("the phrase").returncode, 0)

    def test_extensions_and_letter_case(self):
        self.make("a.TXT", "needle one")
        self.make("b.Md", "needle two")
        self.make("c.json", '{"k": "needle three"}')
        self.make("d.csv", "needle four")
        self.make("e", "needle five")
        self.make("f.vtt.bak", "needle six")
        result = self.search("needle", "--list-only")
        self.assertEqual(result.stdout.split("\n")[:3], ["a\t", "b\t", "c\t"])
        self.assertIn("3 hits across 3 sources / 3 files", result.stdout)

    def test_dot_names_are_skipped(self):
        self.make(".hidden.txt", "needle in a dot file")
        self.make(".hidden/inside.txt", "needle in a dot folder")
        self.make("sub/.also.txt", "needle in a nested dot file")
        self.make("sub/.deep/inside.txt", "needle in a nested dot folder")
        self.make("shown.txt", "needle in a shown file")
        result = self.search("needle", "--list-only")
        self.assertEqual(result.stdout, "shown\t\n\n1 hits across 1 sources / 1 files\n")

    def test_dot_names_are_skipped_for_titles_too(self):
        self.make("MADEUP00003.txt", "the phrase")
        self.make(".t.tsv", "MADEUP00003\tHidden Title\n")
        self.make(".d/t.tsv", "MADEUP00003\tHidden Folder Title\n")
        self.assertEqual(header_lines(self.search("the phrase").stdout),
                         ["=== MADEUP00003 :: MADEUP00003.txt"])

    def test_linked_folder_is_not_entered(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        write(outside.name, "far.txt", "needle in a linked folder")
        self.make("near.txt", "needle in a near file")
        try:
            os.symlink(outside.name, os.path.join(self.tmp, "link"))
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are not available")
        result = self.search("needle", "--list-only")
        self.assertEqual(result.stdout, "near\t\n\n1 hits across 1 sources / 1 files\n")

    def test_folders_are_searched_recursively(self):
        self.make("a/b/c/deep.txt", "needle deep down")
        self.assertEqual(self.search("needle").returncode, 0)

    def test_cue_files_come_before_plain_files(self):
        self.make("a.txt", "needle in the text a")
        self.make("b.md", "needle in the md b")
        self.make("y.srt", "1\n00:00:01,000 --> 00:00:02,000\nneedle in the srt y\n")
        self.make("z.vtt", vtt(("00:00:01.000", ["needle in the vtt z"])))
        heads = [h.split(" :: ")[0] for h in header_lines(self.search("needle").stdout)]
        self.assertEqual(heads, ["=== y", "=== z", "=== a", "=== b"])

    def test_paths_are_in_sorted_order_within_a_group(self):
        for name in ("c", "a", "b"):
            self.make("%s/%s.txt" % (name, name), "needle")
        heads = [h.split(" :: ")[0] for h in header_lines(self.search("needle").stdout)]
        self.assertEqual(heads, ["=== a", "=== b", "=== c"])

    def test_roots_in_the_order_given(self):
        a, b = os.path.join(self.tmp, "a"), os.path.join(self.tmp, "b")
        write(a, "fromA.txt", "needle")
        write(b, "fromB.txt", "needle")
        first = header_lines(cli("needle", "--root", a, "--root", b).stdout)
        second = header_lines(cli("needle", "--root", b, "--root", a).stdout)
        self.assertEqual([h.split(" :: ")[0] for h in first], ["=== fromA", "=== fromB"])
        self.assertEqual([h.split(" :: ")[0] for h in second], ["=== fromB", "=== fromA"])

    def test_two_roots_are_both_searched(self):
        a, b = os.path.join(self.tmp, "a"), os.path.join(self.tmp, "b")
        write(a, "one.txt", "needle in one")
        write(b, "two.txt", "needle in two")
        result = cli("needle", "--root", a, "--root", b)
        self.assertIn("2 hits across 2 sources / 2 files", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_a_root_given_twice_is_searched_once(self):
        write(self.tmp, "one.txt", "needle in one")
        result = cli("needle", "--root", self.tmp, "--root", self.tmp)
        self.assertIn("\n1 hits across 1 sources / 1 files\n", result.stdout)

    def test_a_folder_inside_another_root_is_searched_once(self):
        write(self.tmp, "sub/one.txt", "needle in one")
        result = cli("needle", "--root", self.tmp, "--root", os.path.join(self.tmp, "sub"))
        self.assertIn("\n1 hits across 1 sources / 1 files\n", result.stdout)

    def test_relative_root_is_relative_to_the_current_folder(self):
        write(self.tmp, "sub/one.txt", "needle in one")
        result = cli("needle", "--root", "sub", cwd=self.tmp)
        self.assertEqual(result.returncode, 0)
        result = cli("needle", "--root", "missing", cwd=self.tmp)
        self.assertEqual(result.returncode, 2)

    def test_undecodable_bytes_do_not_stop_the_search(self):
        self.make("bad.txt", b"before \xff\xfe the needle after")
        result = self.search("the needle")
        self.assertEqual(result.returncode, 0)
        self.assertIn("before \ufffd\ufffd the needle after", result.stdout)

    def test_byte_order_mark_does_not_hide_the_first_word(self):
        self.make("bom.txt", b"\xef\xbb\xbfneedle at the start")
        result = self.search("needle at", "--context", "0")
        self.assertEqual(result.returncode, 0)


class Duplicates(SearchCase):
    def test_same_passage_in_a_vtt_and_a_txt_of_one_source_printed_once_with_the_time(self):
        passage = "alpha beta gamma the needle phrase delta epsilon zeta"
        self.make("MADEUP00004.en.vtt", vtt(("00:00:09.000", [passage])))
        self.make("MADEUP00004.txt", passage)
        result = self.search("needle phrase")
        heads = header_lines(result.stdout)
        self.assertEqual(len(heads), 1)
        self.assertIn("[00:00:09]", heads[0])
        self.assertIn("\n1 hits across 1 sources / 1 files", result.stdout.replace("2 files", "1 files"))
        self.assertIn("/ 2 files", result.stdout)

    def test_same_passage_in_different_sources_printed_twice(self):
        passage = "alpha beta gamma the needle phrase delta epsilon zeta"
        self.make("one.txt", passage)
        self.make("two.txt", passage)
        self.assertEqual(len(header_lines(self.search("needle phrase").stdout)), 2)

    def test_different_context_in_one_source_is_not_merged(self):
        self.make("MADEUP00004.en.vtt", vtt(("00:00:09.000", ["one needle phrase here"])))
        self.make("MADEUP00004.txt", "another needle phrase there")
        self.assertEqual(len(header_lines(self.search("needle phrase").stdout)), 2)

    def test_two_hits_near_the_start_of_one_file_are_both_printed(self):
        self.make("a.txt", "needle one and needle two and then the rest of the text goes on")
        result = self.search("needle")
        self.assertEqual(len(header_lines(result.stdout)), 2)
        self.assertIn("\n2 hits across 1 sources", result.stdout)

    def test_the_same_sentence_twice_in_one_file_is_not_merged(self):
        filler = " and the story goes on with other words in between"
        self.make("a.txt", "needle phrase" + filler * 4 + " needle phrase" + filler)
        result = self.search("needle phrase", "--context", "0")
        self.assertEqual(len(header_lines(result.stdout)), 2)


class Folders(SearchCase):
    def write_episodes(self):
        """Write the two measured episodes under one root.

        The first sentence is the same and the second differs. The difference
        starts after the 40 characters beside the match, so a check that
        ignores the folder sees one hit.
        """
        opening = ("Welcome back to the workshop hour, where we build small tools "
                   "from scrap wood and old parts.")
        shared = " Today we"
        self.make("ep1/transcript.txt", opening + shared
                  + " plane the legs of a stool until they sit flat.")
        self.make("ep2/transcript.txt", opening + shared
                  + " glue the drawer and leave it to set overnight.")

    def test_two_episodes_with_the_same_transcript_name_are_two_sources(self):
        """source: a folder per episode is its own source, labelled with the path under the root."""
        self.write_episodes()
        result = self.search("small tools")
        self.assertEqual(header_lines(result.stdout), [
            "=== transcript :: ep1/transcript.txt",
            "=== transcript :: ep2/transcript.txt",
        ])
        self.assertIn("\n2 hits across 2 sources / 2 files\n", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_one_video_id_in_two_folders_is_one_source(self):
        """source: the same video id joins a cue file and a plain file across folders."""
        passage = "alpha beta gamma the needle phrase delta epsilon zeta"
        self.make("a/MADEUP00008.en.vtt", vtt(("00:00:12.000", [passage])))
        self.make("b/MADEUP00008.txt", passage)
        result = self.search("needle phrase")
        self.assertEqual(header_lines(result.stdout), [
            "=== MADEUP00008 :: a/MADEUP00008.en.vtt  [00:00:12]  "
            "https://www.youtube.com/watch?v=MADEUP00008&t=12s",
        ])
        self.assertIn("\n1 hits across 1 sources / 2 files\n", result.stdout)

    def test_cue_and_plain_file_of_one_name_in_one_folder_are_one_source(self):
        """source: one folder still joins a cue file and a plain file of the same name."""
        passage = "alpha beta gamma the needle phrase delta epsilon zeta"
        self.make("x/notes.vtt", vtt(("00:00:04.000", [passage])))
        self.make("x/notes.txt", passage)
        result = self.search("needle phrase")
        self.assertEqual(header_lines(result.stdout), [
            "=== notes :: x/notes.vtt  [00:00:04]",
        ])
        self.assertIn("\n1 hits across 1 sources / 2 files\n", result.stdout)

    def test_list_only_prints_the_same_name_twice_for_two_folders(self):
        """source: --list-only prints one NAME line per folder when the source name is shared."""
        self.write_episodes()
        result = self.search("small tools", "--list-only")
        self.assertEqual(
            result.stdout,
            "transcript\t\ntranscript\t\n\n2 hits across 2 sources / 2 files\n")


class Failures(SearchCase):
    def setUp(self):
        super().setUp()
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("file modes do not stop the superuser")

    def lock(self, path):
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o700)

    def test_unreadable_file_is_named_counted_and_fails_the_run(self):
        bad = self.make("bad.txt", "needle hidden")
        self.make("good.txt", "needle visible")
        self.lock(bad)
        result = self.search("needle")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr,
                         "corpus-grep: could not read %s: Permission denied\n" % bad)
        self.assertEqual(len(header_lines(result.stdout)), 1)
        self.assertIn("=== good :: good.txt", result.stdout)
        self.assertTrue(result.stdout.endswith(
            "\n1 hits across 1 sources / 2 files, 1 could not be read\n"))

    def test_unreadable_file_with_no_hits_says_so_in_the_no_match_line(self):
        bad = self.make("bad.txt", "needle hidden")
        self.lock(bad)
        result = self.search("needle")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout,
                         "no matches for 'needle' across 1 files in 1 root(s), 1 could not be read\n")

    def test_unreadable_file_with_list_only(self):
        bad = self.make("bad.txt", "needle hidden")
        self.make("good.txt", "needle visible")
        self.lock(bad)
        result = self.search("needle", "--list-only")
        self.assertEqual(result.stdout,
                         "good\t\n\n1 hits across 1 sources / 2 files, 1 could not be read\n")

    def test_unreadable_title_file_is_reported(self):
        bad = self.make("t.tsv", "MADEUP00003\tA Title\n")
        self.make("MADEUP00003.txt", "needle visible")
        self.lock(bad)
        result = self.search("needle")
        self.assertEqual(result.returncode, 2)
        self.assertIn("corpus-grep: could not read %s: " % bad, result.stderr)
        self.assertIn(", 1 could not be read", result.stdout)

    def test_unreadable_folder_is_reported(self):
        self.make("sub/inner.txt", "needle inner")
        self.make("good.txt", "needle visible")
        folder = os.path.join(self.tmp, "sub")
        os.chmod(folder, 0)
        self.addCleanup(os.chmod, folder, 0o700)
        result = self.search("needle")
        self.assertEqual(result.returncode, 2)
        self.assertIn("corpus-grep: could not read %s: " % folder, result.stderr)
        self.assertIn(", 1 could not be read", result.stdout)

    def test_root_that_is_not_a_folder(self):
        good = os.path.join(self.tmp, "good")
        write(good, "one.txt", "needle in one")
        missing = os.path.join(self.tmp, "missing")
        result = cli("needle", "--root", missing, "--root", good)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "corpus-grep: not a folder: %s\n" % missing)
        self.assertIn("=== one :: one.txt", result.stdout)

    def test_root_that_is_a_file(self):
        path = self.make("one.txt", "needle in one")
        result = cli("needle", "--root", path)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "corpus-grep: not a folder: %s\n" % path)
        self.assertEqual(result.stdout,
                         "no matches for 'needle' across 0 files in 0 root(s)\n")

    def test_dangling_link_named_like_a_text_file_is_reported(self):
        link = os.path.join(self.tmp, "gone.txt")
        try:
            os.symlink(os.path.join(self.tmp, "nowhere"), link)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are not available")
        self.make("good.txt", "needle visible")
        result = self.search("needle")
        self.assertEqual(result.returncode, 2)
        self.assertIn("corpus-grep: could not read %s: " % link, result.stderr)


class Defaults(SearchCase):
    def test_default_context_is_260_characters_each_side(self):
        self.make("wide.txt", "a" * 300 + " needle " + "b" * 300)
        result = self.search("needle")
        context = result.stdout.split("\n")[2]
        self.assertEqual(context, "    " + "a" * 259 + " needle " + "b" * 259)

    def test_default_max_is_40_hits(self):
        self.make("many.txt", " ".join("needle number %d" % i for i in range(45)))
        result = self.search("needle number")
        self.assertEqual(len(header_lines(result.stdout)), 40)
        self.assertTrue(result.stdout.endswith(
            "\n45 hits across 1 sources / 1 files (showing 40)\n"))

    def test_a_root_given_twice_is_one_root(self):
        self.make("a.txt", "something else")
        result = cli("needle", "--root", self.tmp, "--root", self.tmp)
        self.assertEqual(result.stdout,
                         "no matches for 'needle' across 1 files in 1 root(s)\n")
        self.assertEqual(result.returncode, 1)

    def test_a_missing_root_given_twice_is_reported_once(self):
        gone = os.path.join(self.tmp, "gone")
        result = cli("needle", "--root", gone, "--root", gone)
        self.assertEqual(result.stderr, "corpus-grep: not a folder: %s\n" % gone)
        self.assertEqual(result.returncode, 2)


class NotRegularFiles(SearchCase):
    def test_a_named_pipe_is_not_opened(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("named pipes are not available")
        os.mkfifo(os.path.join(self.tmp, "pipe.txt"))
        self.make("real.txt", "needle in a real file")
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(support.ROOT, "corpus_grep.py"), "needle",
                 "--root", self.tmp],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
                encoding="utf-8")
        except subprocess.TimeoutExpired:
            self.fail("the search opened the named pipe and waited for it")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(header_lines(result.stdout), ["=== real :: real.txt"])
        self.assertIn("1 hits across 1 sources / 1 files", result.stdout)


class ClosedOutput(SearchCase):
    def test_output_closed_early_leaves_no_traceback(self):
        lines = ["entry number %05d says something about the needle in its own words" % i
                 for i in range(3000)]
        self.make("big.txt", "\n".join(lines))
        args = [sys.executable, os.path.join(support.ROOT, "corpus_grep.py"), "needle",
                "--root", self.tmp, "--max", "100000"]
        sized = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertGreater(len(sized.stdout), 200 * 1024)
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        first = proc.stdout.readline()
        second = proc.stdout.readline()
        proc.stdout.close()
        stderr = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        proc.wait()
        self.assertEqual(first, b"\n")
        self.assertTrue(second.startswith(b"=== big :: big.txt"))
        self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()

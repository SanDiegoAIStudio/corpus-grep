import unittest

import support
from corpus_grep import normalize


def cue(start, *lines):
    """One cue block: a timing line (start only) followed by text lines."""
    return "%s --> 99:59:59.000\n%s\n" % (start, "\n".join(lines))


class TimingLines(unittest.TestCase):
    def test_dot_form_with_hours(self):
        raw = "WEBVTT\n\n01:02:03.000 --> 01:02:05.000 align:start\nhello there\n"
        text, stamps = normalize(raw, "vtt")
        self.assertEqual(text, "hello there")
        self.assertEqual(set(stamps), {3723})

    def test_comma_form(self):
        raw = "1\n00:00:07,500 --> 00:00:09,000\nhello there\n"
        text, stamps = normalize(raw, "srt")
        self.assertEqual(text, "hello there")
        self.assertEqual(set(stamps), {7})

    def test_short_form_without_hours(self):
        raw = "WEBVTT\n\n01:05.000 --> 01:09.000\nhello there\n"
        text, stamps = normalize(raw, "vtt")
        self.assertEqual(text, "hello there")
        self.assertEqual(set(stamps), {65})

    def test_tab_before_arrow_and_long_hours(self):
        raw = "WEBVTT\n\n100:00:01.000\t--> 100:00:02.000\nhello\n"
        text, stamps = normalize(raw, "vtt")
        self.assertEqual(text, "hello")
        self.assertEqual(set(stamps), {360001})

    def test_time_applies_to_all_lines_up_to_next_timing_line(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "one", "two") + "\n" + cue("00:00:05.000", "three")
        text, stamps = normalize(raw, "vtt")
        self.assertEqual(text, "one two three")
        self.assertEqual(stamps, [1] * 8 + [5] * 5)


class WhatIsNotSpeech(unittest.TestCase):
    def test_header_and_block_before_first_cue_dropped(self):
        raw = ("WEBVTT\nKind: captions\nLanguage: en\n\nsome text before any cue\n\n"
               + cue("00:00:01.000", "hello"))
        self.assertEqual(normalize(raw, "vtt")[0], "hello")

    def test_cue_identifier_dropped_in_vtt(self):
        raw = ("WEBVTT\n\nintro\n" + cue("00:00:01.000", "first")
               + "\nsecond-id\n" + cue("00:00:02.000", "second"))
        self.assertEqual(normalize(raw, "vtt")[0], "first second")

    def test_cue_identifier_dropped_in_srt(self):
        raw = "1\n" + cue("00:00:01,000", "first") + "\n2\n" + cue("00:00:02,000", "second")
        self.assertEqual(normalize(raw, "srt")[0], "first second")

    def test_note_block_after_a_cue_dropped(self):
        raw = ("WEBVTT\n\n" + cue("00:00:01.000", "first")
               + "\nNOTE a comment\nthat goes on\n\n" + cue("00:00:02.000", "second"))
        self.assertEqual(normalize(raw, "vtt")[0], "first second")

    def test_note_alone_on_its_line_starts_a_block(self):
        raw = ("WEBVTT\n\n" + cue("00:00:01.000", "first")
               + "\nNOTE\nthe comment\n\n" + cue("00:00:02.000", "second"))
        self.assertEqual(normalize(raw, "vtt")[0], "first second")

    def test_note_with_a_tab_starts_a_block(self):
        raw = ("WEBVTT\n\n" + cue("00:00:01.000", "first")
               + "\nNOTE\tcomment\nmore\n\n" + cue("00:00:02.000", "second"))
        self.assertEqual(normalize(raw, "vtt")[0], "first second")

    def test_style_and_region_blocks_dropped(self):
        raw = ("WEBVTT\n\n" + cue("00:00:01.000", "first")
               + "\nSTYLE\n::cue { color: red }\n\nREGION\nid:one\n\n"
               + cue("00:00:02.000", "second"))
        self.assertEqual(normalize(raw, "vtt")[0], "first second")

    def test_note_without_a_space_after_it_is_speech(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "first") + "\nNOTEBOOK\n" + cue("00:00:02.000", "x")
        # NOTEBOOK follows a blank line and is followed by a timing line: an identifier
        self.assertEqual(normalize(raw, "vtt")[0], "first x")
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "first") + "\nNOTEBOOK more\nsecond line\n\n"
        self.assertEqual(normalize(raw, "vtt")[0], "first NOTEBOOK more second line")

    def test_number_only_spoken_line_kept(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "it was the year", "1999", "and things changed")
        self.assertEqual(normalize(raw, "vtt")[0], "it was the year 1999 and things changed")

    def test_number_only_first_line_of_a_cue_kept(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "2024", "was a year")
        self.assertEqual(normalize(raw, "vtt")[0], "2024 was a year")

    def test_spoken_line_starting_with_note_kept(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "please", "NOTE that this matters")
        self.assertEqual(normalize(raw, "vtt")[0], "please NOTE that this matters")

    def test_spoken_line_starting_with_kind_or_language_kept(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "Kind: of a surprise", "Language: is hard")
        self.assertEqual(normalize(raw, "vtt")[0], "Kind: of a surprise Language: is hard")


class LineText(unittest.TestCase):
    def test_tags_removed(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "<c>hello</c><00:00:01.500><c> there</c> <i>you</i>")
        self.assertEqual(normalize(raw, "vtt")[0], "hello there you")

    def test_entities_decoded(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "&gt;&gt; fish &amp; chips")
        self.assertEqual(normalize(raw, "vtt")[0], ">> fish & chips")

    def test_escaped_less_than_survives_as_a_character(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "I &lt;3 this and &lt;b&gt;that&lt;/b&gt; too")
        self.assertEqual(normalize(raw, "vtt")[0], "I <3 this and <b>that</b> too")

    def test_no_break_space_becomes_a_space(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "hello\u00a0world", "and&nbsp;more")
        self.assertEqual(normalize(raw, "vtt")[0], "hello world and more")

    def test_whitespace_runs_become_one_space(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "  a \t  b   c  ")
        self.assertEqual(normalize(raw, "vtt")[0], "a b c")

    def test_line_empty_after_cleaning_is_dropped(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", " ", "<c></c>", "&nbsp;", "kept")
        text, stamps = normalize(raw, "vtt")
        self.assertEqual(text, "kept")
        self.assertEqual(len(stamps), 4)

    def test_lines_are_joined_with_one_space_not_a_newline(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "one", "two")
        self.assertEqual(normalize(raw, "vtt")[0], "one two")


class RepeatedLines(unittest.TestCase):
    def rolling(self, line, times=3):
        return "WEBVTT\n\n" + "\n".join(
            cue("00:00:%02d.000" % (i + 1), line) for i in range(times))

    def test_tripled_short_line_dropped(self):
        text, _ = normalize(self.rolling("so yes"), "vtt")
        self.assertEqual(text, "so yes")
        self.assertEqual(len("so yes"), 6)

    def test_tripled_line_with_a_question_mark_dropped(self):
        self.assertEqual(normalize(self.rolling("who is there?"), "vtt")[0], "who is there?")

    def test_tripled_line_with_a_colon_dropped(self):
        self.assertEqual(normalize(self.rolling("said: no"), "vtt")[0], "said: no")

    def test_first_copy_keeps_its_time(self):
        _, stamps = normalize(self.rolling("so yes"), "vtt")
        self.assertEqual(set(stamps), {1})

    def test_repeat_with_different_tags_is_still_a_repeat(self):
        raw = ("WEBVTT\n\n" + cue("00:00:01.000", "one<00:00:01.200><c> two</c>")
               + "\n" + cue("00:00:02.000", "one two"))
        self.assertEqual(normalize(raw, "vtt")[0], "one two")

    def test_line_that_returns_later_is_kept(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "alpha", "beta", "alpha")
        self.assertEqual(normalize(raw, "vtt")[0], "alpha beta alpha")

    def test_only_the_line_directly_before_is_compared(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "a b", "c d", "a b", "a b", "c d")
        self.assertEqual(normalize(raw, "vtt")[0], "a b c d a b c d")

    def test_nothing_dropped_with_collapse_off(self):
        text, stamps = normalize(self.rolling("so yes"), "vtt", collapse=False)
        self.assertEqual(text, "so yes so yes so yes")
        self.assertEqual(stamps, [1] * 7 + [2] * 7 + [3] * 6)


class OffsetsAndTimes(unittest.TestCase):
    def test_stamps_cover_the_text_exactly(self):
        for raw in ("WEBVTT\n\n" + cue("00:00:01.000", "a", "bb") + "\n" + cue("00:00:02.000", "ccc"),
                    "WEBVTT\n\n", "", "WEBVTT\n\n" + cue("00:00:01.000", "x")):
            text, stamps = normalize(raw, "vtt")
            self.assertEqual(len(stamps), len(text))

    def test_every_kept_line_sits_at_its_offset_with_its_time(self):
        expected = [
            ("fish & chips", 1),
            (">> a <b> tag survives", 3),
            ("caf\u00e9 au lait", 4),
            ("plain line", 9),
            ("last &amp; line", 12),
        ]
        raw = "WEBVTT\n\n" + "\n".join([
            cue("00:00:01.000", "fish &amp; chips"),
            cue("00:00:03.000", "&gt;&gt; a &lt;b&gt; tag survives"),
            cue("00:00:04.000", "caf&eacute;   au\u00a0lait"),
            cue("00:00:09.000", "<c>plain</c> line"),
            cue("00:00:12.000", "last &amp;amp; line"),
        ])
        text, stamps = normalize(raw, "vtt")
        offset = 0
        for line, seconds in expected:
            self.assertEqual(text[offset:offset + len(line)], line)
            self.assertEqual(stamps[offset], seconds)
            self.assertEqual(stamps[offset + len(line) - 1], seconds)
            offset += len(line)
            if offset < len(text):
                self.assertEqual(text[offset], " ")
                self.assertEqual(stamps[offset], seconds)
                offset += 1
        self.assertEqual(offset, len(text))


class FileFormat(unittest.TestCase):
    def test_byte_order_mark_removed_from_a_cue_file(self):
        raw = "\ufeff" + cue("00:00:01.000", "hello")
        self.assertEqual(normalize(raw, "vtt"), ("hello", [1] * 5))
        self.assertEqual(normalize(raw.encode("utf-8"), "srt")[0], "hello")

    def test_byte_order_mark_removed_from_a_plain_file(self):
        self.assertEqual(normalize(b"\xef\xbb\xbfhello there", "txt")[0], "hello there")
        self.assertEqual(normalize("\ufeffhello", "md")[0], "hello")

    def test_crlf_line_ends(self):
        raw = "WEBVTT\r\n\r\n1\r\n00:00:01,000 --> 00:00:02,000\r\nhello\r\nthere\r\n\r\n"
        raw += "NOTE x\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nagain\r\n"
        text, stamps = normalize(raw, "srt")
        self.assertEqual(text, "hello there again")
        self.assertNotIn("\r", text)

    def test_undecodable_bytes_are_replaced(self):
        text, _ = normalize(b"hello \xff\xfe world", "txt")
        self.assertEqual(text, "hello \ufffd\ufffd world")

    def test_html_tags_replaced_with_a_space(self):
        text, stamps = normalize("<p>one</p><p>two</p><b>three</b>four", "html")
        self.assertEqual(text.strip(), "one two three four")
        self.assertEqual(stamps, [])

    def test_html_no_break_space_entity_becomes_a_space(self):
        text, _ = normalize("<p>fish&nbsp;chips &amp; more</p>", "html")
        self.assertEqual(text.strip(), "fish chips & more")

    def test_plain_file_text_and_no_stamps(self):
        text, stamps = normalize("line one\n\n  line   two &amp; three\n", "txt")
        self.assertEqual(text, "line one line two & three ")
        self.assertEqual(stamps, [])

    def test_extension_is_case_insensitive_and_may_have_a_dot(self):
        raw = "WEBVTT\n\n" + cue("00:00:01.000", "hello")
        self.assertEqual(normalize(raw, "VTT")[0], "hello")
        self.assertEqual(normalize(raw, ".vtt")[0], "hello")

    def test_json_and_md_are_plain(self):
        self.assertEqual(normalize('{"a": "x &amp; y"}', "json"), ('{"a": "x & y"}', []))
        self.assertEqual(normalize("# title\n\ntext", "md"), ("# title text", []))


if __name__ == "__main__":
    unittest.main()

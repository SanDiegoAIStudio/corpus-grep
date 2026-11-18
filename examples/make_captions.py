#!/usr/bin/env python3
"""Turn examples/talk.txt into the sample caption file.

The file written has the rolling shape of auto-generated captions: every
caption line is shown three times, once as the new line of a cue with a timing
tag before each word, once in a cue ten milliseconds long, and once as the
first line of the next cue.

Usage:
    python3 examples/make_captions.py            # writes examples/captions/MADEUP00001.en.vtt
    python3 examples/make_captions.py --stdout   # prints the same bytes instead
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TALK_PATH = os.path.join(HERE, "talk.txt")
OUTPUT_PATH = os.path.join(HERE, "captions", "MADEUP00001.en.vtt")

MAX_LINE = 38
WORD_MS = 400
FLASH_MS = 10
TAIL_MS = 1000
SPEAKER_MARK = "&gt;&gt;"
STYLE = " align:start position:0%"


def clean_word(token):
    """Lower-case a word and drop punctuation other than apostrophes and ampersands."""
    word = re.sub(r"[^a-z0-9'&]", "", token.lower())
    return word.replace("&", "&amp;")


def caption_lines(talk_text):
    """Return the caption lines as (start in milliseconds, list of words)."""
    lines = []
    current = []
    for paragraph in re.split(r"\n\s*\n", talk_text):
        paragraph = " ".join(re.sub(r"[-/]", " ", paragraph).split())
        if not paragraph:
            continue
        speaker_change = paragraph.startswith(">>")
        if speaker_change:
            paragraph = paragraph[2:]
        words = [w for w in (clean_word(t) for t in paragraph.split()) if w]
        if speaker_change:
            words.insert(0, SPEAKER_MARK)
            if current:
                lines.append(current)
                current = []
        for word in words:
            if current and len(" ".join(current + [word])) > MAX_LINE:
                lines.append(current)
                current = []
            current.append(word)
    if current:
        lines.append(current)
    result = []
    start = 0
    for words in lines:
        result.append((start, words))
        start += WORD_MS * len(words)
    return result


def stamp(ms):
    """Format milliseconds as HH:MM:SS.mmm."""
    return "%02d:%02d:%02d.%03d" % (ms // 3600000, ms // 60000 % 60,
                                    ms // 1000 % 60, ms % 1000)


def tagged_line(start, words):
    """Write a line with a timing tag before each word after the first."""
    text = words[0]
    for j, word in enumerate(words[1:], 1):
        text += "<%s><c> %s</c>" % (stamp(start + WORD_MS * j), word)
    return text


def build_vtt(talk_text):
    """Return the text of the sample caption file for a talk."""
    lines = caption_lines(talk_text)
    blocks = [
        "WEBVTT\nKind: captions\nLanguage: en",
        "NOTE These captions are made up.\n"
        "They copy the shape of auto-generated captions.",
    ]
    end_of_talk = lines[-1][0] + WORD_MS * len(lines[-1][1])
    for k, (start, words) in enumerate(lines):
        text = " ".join(words)
        before = " " if k == 0 else " ".join(lines[k - 1][1])
        next_start = lines[k + 1][0] if k + 1 < len(lines) else end_of_talk
        flash = next_start - FLASH_MS
        blocks.append("%s --> %s%s\n%s\n%s" % (
            stamp(start), stamp(flash), STYLE, before, tagged_line(start, words)))
        blocks.append("%s --> %s%s\n%s" % (stamp(flash), stamp(next_start), STYLE, text))
    last_text = " ".join(lines[-1][1])
    blocks.append("%s --> %s%s\n%s" % (
        stamp(end_of_talk), stamp(end_of_talk + TAIL_MS), STYLE, last_text))
    return "\n\n".join(blocks) + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in ([], ["--stdout"]):
        print("usage: make_captions.py [--stdout]", file=sys.stderr)
        return 2
    with open(TALK_PATH, "rb") as fh:
        talk_text = fh.read().decode("utf-8")
    data = build_vtt(talk_text).encode("ascii")
    if argv:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        with open(OUTPUT_PATH, "wb") as fh:
            fh.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())

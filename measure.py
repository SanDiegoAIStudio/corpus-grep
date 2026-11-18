#!/usr/bin/env python3
"""Measure how many phrases a plain line search finds in one caption file.

Phrases are drawn at random from the text of the file (repeats dropped). A
phrase counts as found when at least one line of the file, exactly as it is on
disk, holds it as a substring. That is what a fixed-string line search
(grep -F) tests.

This script measures a plain line search only. corpus_grep.py finds every one
of these phrases by construction, because they are drawn from the text it
searches; no score is measured or claimed for it here.

Usage:
    python3 measure.py FILE [--words 4,6,8,12] [--samples 200] [--seed 1]
"""

import argparse
import os
import random
import re
import sys

import corpus_grep

DEFAULT_WORDS = "4,6,8,12"


class MeasureError(Exception):
    """A problem with the input that ends the run with exit code 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print("measure: %s" % message, file=sys.stderr)
        sys.exit(2)


def positive(value, what):
    """Return value as an int, or raise MeasureError when it is not a positive whole number."""
    if not re.fullmatch(r"[0-9]+", value) or int(value) < 1:
        raise MeasureError("%s must be a positive whole number, got %r" % (what, value))
    return int(value)


def read_file(path):
    """Return (lines as on disk, extension) for one vtt or srt file."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else ""
    if ext not in corpus_grep.CUE_EXTS:
        raise MeasureError("not a vtt or srt file: %s" % path)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as err:
        raise MeasureError("could not read %s: %s" % (path, err.strerror or err))
    raw = data.decode("utf-8", errors="replace")
    return raw, ext


def searched_text(raw, ext):
    """Return the text corpus_grep searches for this file, repeats dropped."""
    text, _ = corpus_grep.normalize(raw, ext, collapse=True)
    return corpus_grep.collapse_rolling(text)[0]


def draw_phrases(words, lengths, samples, seed):
    """Return one list of phrases per length, drawn with one generator."""
    rng = random.Random(seed)
    drawn = []
    for length in lengths:
        phrases = []
        for _ in range(samples):
            start = rng.randrange(len(words) - length + 1)
            phrases.append(" ".join(words[start:start + length]))
        drawn.append(phrases)
    return drawn


def found_in_a_line(phrase, lines):
    """True when one line of the file holds the phrase."""
    return any(phrase in line for line in lines)


def measure(path, lengths, samples, seed):
    """Return the output lines for one file."""
    raw, ext = read_file(path)
    lines = raw.split("\n")
    as_written = len(corpus_grep.cue_lines(raw, collapse=False))
    after_drop = len(corpus_grep.cue_lines(raw, collapse=True))
    words = searched_text(raw, ext).split()
    longest = max(lengths)
    if len(words) < longest:
        raise MeasureError("%s has %d words, fewer than the longest phrase length %d"
                           % (path, len(words), longest))
    per_line = len(words) / after_drop if after_drop else 0.0
    out = [
        "file: %s" % os.path.basename(path),
        "caption lines: %d as written, %d after repeats are dropped"
        % (as_written, after_drop),
        "words: %d (%.1f per line)" % (len(words), per_line),
        "words  found by a plain line search",
    ]
    for length, phrases in zip(lengths, draw_phrases(words, lengths, samples, seed)):
        hits = sum(1 for p in phrases if found_in_a_line(p, lines))
        percent = (200 * hits + samples) // (2 * samples)
        out.append("%5d  %d%% (%d of %d)" % (length, percent, hits, samples))
    return out


def build_parser():
    ap = _Parser(
        prog="measure.py",
        description="Measure how many phrases a plain line search (grep -F) finds "
                    "in one caption file. Phrases are drawn at random from the "
                    "text of the file; a phrase counts as found when one line of "
                    "the file, as it is on disk, holds it. This measures a plain "
                    "line search only: corpus_grep.py finds every one of these "
                    "phrases by construction, because they are drawn from the "
                    "text it searches.")
    ap.add_argument("file", metavar="FILE", help="one vtt or srt file")
    ap.add_argument("--words", default=DEFAULT_WORDS, metavar="LIST",
                    help="comma separated phrase lengths in words (default %s)"
                    % DEFAULT_WORDS)
    ap.add_argument("--samples", default="200", metavar="N",
                    help="phrases drawn per length (default 200)")
    ap.add_argument("--seed", default="1", metavar="N",
                    help="random seed; the same seed prints the same numbers (default 1)")
    return ap


def main(argv=None):
    """Run the measurement; return the exit code."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 0
    try:
        lengths = [positive(piece, "--words") for piece in args.words.split(",")]
        samples = positive(args.samples, "--samples")
        seed = positive(args.seed, "--seed")
        lines = measure(args.file, lengths, samples, seed)
    except MeasureError as err:
        print("measure: %s" % err, file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

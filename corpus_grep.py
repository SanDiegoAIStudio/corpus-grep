#!/usr/bin/env python3
"""Phrase search for caption and transcript files.

Auto-generated captions break speech into short lines and show every line two
or three times, so a phrase of more than a few words is rarely inside one line
of the file. This tool removes the caption markup, joins the lines, drops the
repeats, searches the joined text, and prints each hit with the time it was
spoken and, when the file name carries a video id, a link that opens the video
at that second.

Usage:
    python3 corpus_grep.py "some phrase" --root captions
    python3 corpus_grep.py "clos(e|er) to the (money|deal)" --root captions --regex
    python3 corpus_grep.py "some phrase" --root captions --root notes --list-only

Exit codes: 0 when at least one hit was found and nothing failed, 1 when no hit
was found and nothing failed, 2 for a usage error, a bad pattern, a root that is
not a folder, or a file that could not be read.
"""

import argparse
import html as htmllib
import os
import re
import sys

CUE_EXTS = ("vtt", "srt")
PLAIN_EXTS = ("txt", "html", "md", "json")
TEXT_EXTS = CUE_EXTS + PLAIN_EXTS

TIMING_RE = re.compile(r"^(?:(\d{2,}):)?(\d{2}):(\d{2})[.,]\d{3}[ \t]+-->")
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
BRACKET_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\](?:\.[^.\[\]]+)*$")
LANGUAGE_RE = re.compile(r"\.[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
ROLLING_RE = re.compile(r"(\b[\w' ,.\-]{15,80}?\b)(?:\s*\1){1,5}")
BLOCK_WORDS = ("NOTE", "STYLE", "REGION")
DUPLICATE_EDGE = 40


def _extension(name):
    """Return the text after the last dot of a file name, in lower case."""
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[1].lower()


def _decode(data):
    """Decode UTF-8 bytes, replacing bad bytes, and drop a leading byte order mark."""
    text = data.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


def _opens_block(line):
    """True when a stripped line starts a NOTE, STYLE or REGION block."""
    for word in BLOCK_WORDS:
        if line == word or line.startswith(word + " ") or line.startswith(word + "\t"):
            return True
    return False


def clean_line(line):
    """Remove tags, decode entities, collapse whitespace and trim one speech line."""
    text = TAG_RE.sub("", line)
    text = htmllib.unescape(text)
    return SPACE_RE.sub(" ", text).strip()


def cue_lines(raw, collapse=True):
    """Return the speech lines of a cue file as (text, seconds) pairs.

    With collapse on, a line equal to the line kept just before it is dropped.
    """
    lines = raw.split("\n")
    kept = []
    seconds = None
    in_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if in_block:
            if not stripped:
                in_block = False
            continue
        timing = TIMING_RE.match(stripped)
        if timing:
            seconds = (int(timing.group(1) or 0) * 3600
                       + int(timing.group(2)) * 60
                       + int(timing.group(3)))
            continue
        if seconds is None or not stripped:
            continue
        after_blank = i > 0 and not lines[i - 1].strip()
        if after_blank and _opens_block(stripped):
            in_block = True
            continue
        if (after_blank and i + 1 < len(lines)
                and TIMING_RE.match(lines[i + 1].strip())):
            continue
        text = clean_line(stripped)
        if not text:
            continue
        if collapse and kept and kept[-1][0] == text:
            continue
        kept.append((text, seconds))
    return kept


def normalize(raw, ext, collapse=True):
    """Return (text, stamps) for the content of one file.

    raw is the file content as str or bytes and ext its extension. For a cue
    file stamps[i] is the time in whole seconds of the line that holds
    character i of text. For a plain file stamps is an empty list.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    ext = ext.lower().lstrip(".")
    if ext in CUE_EXTS:
        lines = cue_lines(raw, collapse)
        text = " ".join(t for t, _ in lines)
        stamps = []
        last = len(lines) - 1
        for n, (line_text, seconds) in enumerate(lines):
            stamps.extend([seconds] * (len(line_text) + (1 if n < last else 0)))
        return text, stamps
    if ext == "html":
        raw = TAG_RE.sub(" ", raw)
    return SPACE_RE.sub(" ", htmllib.unescape(raw)), []


def collapse_rolling(text):
    """Collapse runs of repeated phrases; return (collapsed, origin).

    origin[i] is the offset in text of character i of collapsed. For a run of
    repeats the first copy is the one kept.
    """
    parts = []
    origin = []
    pos = 0
    for m in ROLLING_RE.finditer(text):
        parts.append(text[pos:m.start()])
        origin.extend(range(pos, m.start()))
        parts.append(m.group(1))
        origin.extend(range(m.start(1), m.end(1)))
        pos = m.end()
    parts.append(text[pos:])
    origin.extend(range(pos, len(text)))
    return "".join(parts), origin


def video_id(name):
    """Return the video id carried by a file base name, or None."""
    head = name.split(".", 1)[0]
    if ID_RE.fullmatch(head):
        return head
    m = BRACKET_ID_RE.search(name)
    if m:
        return m.group(1)
    return None


def source_name(name):
    """Return the name that groups the files of one source."""
    vid = video_id(name)
    if vid:
        return vid
    if "." in name:
        stem, ext = name.rsplit(".", 1)
    else:
        stem, ext = name, ""
    if ext.lower() in CUE_EXTS:
        stem = LANGUAGE_RE.sub("", stem, count=1)
    return stem or name


def format_time(seconds):
    """Format whole seconds as HH:MM:SS."""
    return "%02d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)


def scan_root(root, warn):
    """Return (text files, tsv files) under root, each sorted by path."""
    files = []
    tsvs = []

    def on_error(err):
        warn(err.filename or root, err.strerror or str(err))

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error,
                                                followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        names = [n for n in filenames if not n.startswith(".")]
        txt_stems = set(n[:-4] for n in names if n.lower().endswith(".txt"))
        for name in names:
            ext = _extension(name)
            path = os.path.join(dirpath, name)
            if ext == "tsv":
                tsvs.append(path)
            elif ext in TEXT_EXTS:
                if ext == "html" and name[:-5] in txt_stems:
                    continue
                if os.path.exists(path) and not os.path.isfile(path):
                    continue
                files.append(path)
    return sorted(files), sorted(tsvs)


def load_titles(tsv_paths, warn):
    """Map video id to title from the first two columns of the given tsv files."""
    titles = {}
    for path in tsv_paths:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as err:
            warn(path, err.strerror or str(err))
            continue
        for line in _decode(data).split("\n"):
            parts = line.rstrip("\r").split("\t")
            if len(parts) < 2:
                continue
            vid = parts[0]
            if not ID_RE.fullmatch(vid) or vid in titles:
                continue
            title = parts[1].strip()
            if title and title != vid:
                titles[vid] = title
    return titles


def compile_pattern(pattern, regex, case_sensitive):
    """Return a compiled pattern, or raise ValueError with a one line reason."""
    if not regex:
        pattern = SPACE_RE.sub(" ", pattern).strip()
    if pattern == "":
        raise ValueError("empty pattern")
    try:
        return re.compile(pattern if regex else re.escape(pattern),
                          0 if case_sensitive else re.I)
    except (re.error, OverflowError, RecursionError) as err:
        raise ValueError(SPACE_RE.sub(" ", str(err)))


def _int_option(minimum, what):
    def convert(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("%r is not a whole number" % value)
        if number < minimum:
            raise argparse.ArgumentTypeError("%s must be %d or more" % (what, minimum))
        return number
    return convert


def build_parser():
    ap = argparse.ArgumentParser(
        prog="corpus_grep.py", allow_abbrev=False,
        description="Phrase search for caption and transcript files. Removes "
                    "caption markup, joins the lines, drops repeats, and prints "
                    "each hit with the time it was spoken.")
    ap.add_argument("pattern", help="phrase to find (literal unless --regex)")
    ap.add_argument("--root", action="append", required=True, metavar="DIR",
                    help="folder to search, recursively; may be given more than once")
    ap.add_argument("--regex", action="store_true",
                    help="treat the pattern as a regular expression")
    ap.add_argument("--case-sensitive", action="store_true",
                    help="match letter case (default: ignore case)")
    ap.add_argument("--context", type=_int_option(0, "--context"), default=260,
                    metavar="N",
                    help="characters of text shown on each side of a match (default 260)")
    ap.add_argument("--max", type=_int_option(1, "--max"), default=40, metavar="N",
                    help="number of hits printed (default 40)")
    ap.add_argument("--list-only", action="store_true",
                    help="print one line per source that has a hit")
    ap.add_argument("--no-collapse", dest="collapse", action="store_false",
                    help="do not drop repeated lines or repeated phrases")
    ap.add_argument("--no-links", action="store_true",
                    help="do not print video links")
    return ap


def main(argv=None):
    """Run the search; return the exit code."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as stop:
        if stop.code is None:
            return 0
        return stop.code if isinstance(stop.code, int) else 2

    try:
        pat = compile_pattern(args.pattern, args.regex, args.case_sensitive)
    except ValueError as err:
        print("corpus-grep: bad pattern: %s" % err, file=sys.stderr)
        return 2

    problems = []

    def warn(path, reason):
        problems.append(path)
        print("corpus-grep: could not read %s: %s" % (path, reason), file=sys.stderr)

    failed = False
    roots = []
    seen_roots = set()
    for root in args.root:
        real = os.path.realpath(root)
        if real in seen_roots:
            continue
        seen_roots.add(real)
        if os.path.isdir(root):
            roots.append(root)
        else:
            failed = True
            print("corpus-grep: not a folder: %s" % root, file=sys.stderr)

    cue_files = []
    plain_files = []
    tsv_files = []
    seen_files = set()
    seen_tsvs = set()
    # The root a file was first found under. A file reached from two roots
    # keeps that first root, as the file itself does.
    file_roots = {}
    for root in roots:
        found, tsvs = scan_root(root, warn)
        for path in found:
            real = os.path.realpath(path)
            if real in seen_files:
                continue
            seen_files.add(real)
            file_roots[path] = root
            if _extension(path) in CUE_EXTS:
                cue_files.append(path)
            else:
                plain_files.append(path)
        for path in tsvs:
            real = os.path.realpath(path)
            if real not in seen_tsvs:
                seen_tsvs.add(real)
                tsv_files.append(path)
    titles = load_titles(tsv_files, warn)
    file_count = len(cue_files) + len(plain_files)

    sources = {}
    seen_keys = {}
    shown = []
    total = 0
    for path in cue_files + plain_files:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as err:
            warn(path, err.strerror or str(err))
            continue
        base = os.path.basename(path)
        text, stamps = normalize(data, _extension(base), args.collapse)
        if args.collapse:
            hay, origin = collapse_rolling(text)
        else:
            hay, origin = text, None
        if not hay:
            continue
        vid = video_id(base)
        shown_name = source_name(base)
        # A video id names one source in any folder. Otherwise the folder
        # and the source name together name it.
        if vid is not None:
            name = vid
        else:
            name = (os.path.dirname(path), shown_name)
        title = titles.get(vid, "") if vid else ""
        rel = os.path.relpath(path, file_roots[path]).replace(os.sep, "/")
        for m in pat.finditer(hay):
            start, end = m.start(), m.end()
            if end == start:
                continue
            key = (name, m.group(0),
                   hay[max(0, start - DUPLICATE_EDGE):start],
                   hay[end:end + DUPLICATE_EDGE])
            if seen_keys.setdefault(key, path) != path:
                continue
            total += 1
            sources.setdefault(name, (shown_name, title))
            if args.list_only or len(shown) >= args.max:
                continue
            pos = origin[start] if origin is not None else start
            seconds = stamps[pos] if pos < len(stamps) else None
            context = hay[max(0, start - args.context):end + args.context].strip()
            shown.append((shown_name, title or rel, vid, seconds, context))

    unread = ""
    if problems:
        unread = ", %d could not be read" % len(problems)
    if total == 0:
        print("no matches for %r across %d files in %d root(s)%s"
              % (args.pattern, file_count, len(roots), unread))
    else:
        if args.list_only:
            for name, title in sources.values():
                print("%s\t%s" % (name, title))
            cut = ""
        else:
            for name, label, vid, seconds, context in shown:
                head = "\n=== %s :: %s" % (name, label)
                if seconds is not None:
                    head += "  [%s]" % format_time(seconds)
                    if vid and not args.no_links:
                        head += "  https://www.youtube.com/watch?v=%s&t=%ds" % (vid, seconds)
                print(head)
                print("    " + context)
            cut = " (showing %d)" % len(shown) if len(shown) < total else ""
        print("\n%d hits across %d sources / %d files%s%s"
              % (total, len(sources), file_count, cut, unread))

    if failed or problems:
        return 2
    return 0 if total else 1


def _run():
    """Entry point for the command line."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        code = main()
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    _run()

"""Mutation check for corpus-grep.

Each mutation is a text replacement in a fresh copy of the repository under the
system temporary directory. The test suite then runs in that copy. A mutation
is killed when the suite fails, and it survives when the suite passes, which
means a test is missing.

Usage:
    /usr/bin/python3 tests/mutate.py [NAME_FRAGMENT ...]

Prints "killed NAME" or "survived NAME" for each mutation, then
"mutations: N, killed: K, survived: S". Exit 0 when nothing survived, 1 when a
mutation survived, 2 when a mutation could not be applied.
"""

import concurrent.futures
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COPY_ITEMS = ("corpus_grep.py", "measure.py", "examples", "tests", "README.md", "LICENSE",
              ".gitignore")
TIMEOUT = 170

CG = "corpus_grep.py"
ME = "measure.py"
MC = "examples/make_captions.py"


def lines(*parts):
    return "\n".join(parts)


KEY_OLD = lines(
    "            key = (name, m.group(0),",
    "                   hay[max(0, start - DUPLICATE_EDGE):start],",
    "                   hay[end:end + DUPLICATE_EDGE])",
    "            if seen_keys.setdefault(key, path) != path:",
    "                continue",
)
KEY_NEW = lines(
    "            key = (name, hay[max(0, start - args.context):end + args.context].strip()[:70])",
    "            if key in seen_keys:",
    "                continue",
    "            seen_keys[key] = path",
)

UNREAD_OLD = lines(
    "        except OSError as err:",
    "            warn(path, err.strerror or str(err))",
    "            continue",
    "        base = os.path.basename(path)",
)
UNREAD_NEW = lines(
    "        except OSError:",
    "            continue",
    "        base = os.path.basename(path)",
)

SWAP_OLD = lines(
    '    text = TAG_RE.sub("", line)',
    "    text = htmllib.unescape(text)",
)
SWAP_NEW = lines(
    "    text = htmllib.unescape(line)",
    '    text = TAG_RE.sub("", text)',
)

NOT_A_FOLDER_OLD = lines(
    "            failed = True",
    '            print("corpus-grep: not a folder: %s" % root, file=sys.stderr)',
)

TIMING_OLD = r'TIMING_RE = re.compile(r"^(?:(\d{2,}):)?(\d{2}):(\d{2})[.,]\d{3}[ \t]+-->")'
TIMING_NO_SHORT = r'TIMING_RE = re.compile(r"^(\d{2,}):(\d{2}):(\d{2})[.,]\d{3}[ \t]+-->")'
TIMING_NO_COMMA = r'TIMING_RE = re.compile(r"^(?:(\d{2,}):)?(\d{2}):(\d{2})[.]\d{3}[ \t]+-->")'

STAMP_OLD = "stamps.extend([seconds] * (len(line_text) + (1 if n < last else 0)))"
STAMP_NEW = "stamps.extend([seconds] * (len(htmllib.escape(line_text)) + (1 if n < last else 0)))"

LINK_OLD = 'head += "  https://www.youtube.com/watch?v=%s&t=%ds" % (vid, seconds)'
LINK_NEW = 'head += "  https://www.youtube.com/watch?v=%s&t=%ds" % (vid, seconds % 3600)'

CONTEXT_OLD = "context = hay[max(0, start - args.context):end + args.context].strip()"
CONTEXT_NEW = "context = hay[max(0, start - 260):end + 260].strip()"

TIME_OLD = 'return "%02d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)'
TIME_NEW = 'return "%02d:%02d:%02d" % (0, seconds % 3600 // 60, seconds % 60)'

MUTATIONS = [
    ("time map built from lines before entities are decoded", CG, STAMP_OLD, STAMP_NEW),
    ("line rule off", CG, "if collapse and kept and kept[-1][0] == text:",
     "if False and kept and kept[-1][0] == text:"),
    ("line rule drops a line equal to any earlier line", CG,
     "if collapse and kept and kept[-1][0] == text:",
     "if collapse and kept and text in [k[0] for k in kept]:"),
    ("number-only spoken line dropped", CG, "        text = clean_line(stripped)\n",
     "        if stripped.isdigit():\n            continue\n        text = clean_line(stripped)\n"),
    ("spoken line starting with NOTE dropped", CG, "        text = clean_line(stripped)\n",
     '        if stripped.startswith("NOTE"):\n            continue\n        text = clean_line(stripped)\n'),
    ("NOTE block kept as speech", CG, 'BLOCK_WORDS = ("NOTE", "STYLE", "REGION")',
     'BLOCK_WORDS = ("STYLE", "REGION")'),
    ("STYLE and REGION blocks kept as speech", CG, 'BLOCK_WORDS = ("NOTE", "STYLE", "REGION")',
     'BLOCK_WORDS = ("NOTE",)'),
    ("cue identifier kept as speech", CG, "if (after_blank and i + 1 < len(lines)",
     "if (False and i + 1 < len(lines)"),
    ("header kept as speech", CG, "if seconds is None or not stripped:", "if not stripped:"),
    ("short timing form not recognised", CG, TIMING_OLD, TIMING_NO_SHORT),
    ("comma timing form not recognised", CG, TIMING_OLD, TIMING_NO_COMMA),
    ("minutes counted as sixty one seconds", CG, "+ int(timing.group(2)) * 60",
     "+ int(timing.group(2)) * 61"),
    ("tags left in the text", CG, 'text = TAG_RE.sub("", line)', "text = line"),
    ("entities not decoded", CG, "text = htmllib.unescape(text)", "text = text"),
    ("entities decoded before tags are removed", CG, SWAP_OLD, SWAP_NEW),
    ("no-break space left alone", CG, 'SPACE_RE = re.compile(r"\\s+")',
     'SPACE_RE = re.compile(r"[ \\t\\r\\n]+")'),
    ("lines joined with a newline", CG, 'text = " ".join(t for t, _ in lines)',
     'text = "\\n".join(t for t, _ in lines)'),
    ("byte order mark kept", CG, 'if raw.startswith("\\ufeff"):', "if False:"),
    ("collapse_rolling returning its input", CG, 'return "".join(parts), origin',
     "return text, list(range(len(text)))"),
    ("origin pointing at the last copy of a run", CG,
     "origin.extend(range(m.start(1), m.end(1)))",
     "origin.extend(range(m.end() - len(m.group(1)), m.end()))"),
    ("origin not adjusted after a run", CG, "origin.extend(range(pos, len(text)))",
     "origin.extend(range(len(origin), len(origin) + len(text) - pos))"),
    ("time found by searching for the matched words again", CG,
     "pos = origin[start] if origin is not None else start",
     "pos = max(text.lower().find(m.group(0).lower()), 0)"),
    ("literal pattern treated as a regular expression", CG,
     "re.compile(pattern if regex else re.escape(pattern),", "re.compile(pattern,"),
    ("--case-sensitive ignored", CG, "0 if case_sensitive else re.I)", "re.I)"),
    ("doubled spaces in a literal pattern left alone", CG,
     'pattern = SPACE_RE.sub(" ", pattern).strip()', "pattern = pattern.strip()"),
    ("zero-length matches reported", CG, "            if end == start:", "            if False:"),
    ("--context ignored", CG, CONTEXT_OLD, CONTEXT_NEW),
    ("--context default changed", CG, "default=260,", "default=250,"),
    ("--max ignored", CG, "if args.list_only or len(shown) >= args.max:", "if args.list_only:"),
    ("--max default changed", CG, "default=40,", "default=41,"),
    ("the cut not stated in the summary", CG,
     'cut = " (showing %d)" % len(shown) if len(shown) < total else ""', 'cut = ""'),
    ("--no-collapse still dropping repeated phrases", CG, "        if args.collapse:",
     "        if True:"),
    ("--no-collapse still dropping repeated lines", CG,
     "text, stamps = normalize(data, _extension(base), args.collapse)",
     "text, stamps = normalize(data, _extension(base), True)"),
    ("--list-only printing hit blocks", CG, "        if args.list_only:", "        if False:"),
    ("--no-links still printing links", CG, "if vid and not args.no_links:", "if vid:"),
    ("link built without the hours", CG, LINK_OLD, LINK_NEW),
    ("time printed without the hours", CG, TIME_OLD, TIME_NEW),
    ("link printed for a name with no id", CG, "if vid and not args.no_links:",
     "if not args.no_links:"),
    ("bracketed id not recognised", CG, "m = BRACKET_ID_RE.search(name)", "m = None"),
    ("id of the first form taken from a longer name", CG, "if ID_RE.fullmatch(head):",
     "if ID_RE.match(head):"),
    ("language piece kept in the source name", CG, 'stem = LANGUAGE_RE.sub("", stem, count=1)',
     "stem = stem"),
    ("titles read from the wrong column", CG, "title = parts[1].strip()",
     "title = parts[-1].strip()"),
    ("a later title replacing the first one", CG,
     "if not ID_RE.fullmatch(vid) or vid in titles:", "if not ID_RE.fullmatch(vid):"),
    ("a title equal to the id accepted", CG, "if title and title != vid:", "if title:"),
    ("an html file with a txt twin searched", CG,
     'if ext == "html" and name[:-5] in txt_stems:', "if False:"),
    ("the same passage in two files of one source printed twice", CG,
     "if seen_keys.setdefault(key, path) != path:", "if False:"),
    ("two hits near the start of one file merged", CG, KEY_OLD, KEY_NEW),
    ("duplicate check looking at no text around the match", CG, "DUPLICATE_EDGE = 40",
     "DUPLICATE_EDGE = 0"),
    ("folder dropped from the source key", CG,
     "            name = (os.path.dirname(path), shown_name)",
     "            name = shown_name"),
    ("video id ignored and the folder always used", CG, lines(
        "        if vid is not None:",
        "            name = vid",
        "        else:",
        "            name = (os.path.dirname(path), shown_name)",
    ), lines(
        "        if vid is not None:",
        "            name = (os.path.dirname(path), shown_name)",
        "        else:",
        "            name = (os.path.dirname(path), shown_name)",
    )),
    ("label falling back to the base name", CG,
     "shown.append((shown_name, title or rel, vid, seconds, context))",
     "shown.append((shown_name, title or base, vid, seconds, context))"),
    ("plain files searched before cue files", CG, "for path in cue_files + plain_files:",
     "for path in plain_files + cue_files:"),
    ("only the last --root searched", CG, "for root in args.root:",
     "for root in args.root[-1:]:"),
    ("a root given twice counted twice", CG, "if real in seen_roots:", "if False:"),
    ("a file reached through two roots searched twice", CG, "if real in seen_files:",
     "if False:"),
    ("a linked folder entered", CG, "followlinks=False", "followlinks=True"),
    ("dot folders searched", CG, 'dirnames[:] = [d for d in dirnames if not d.startswith(".")]',
     "dirnames[:] = list(dirnames)"),
    ("dot files searched", CG, 'names = [n for n in filenames if not n.startswith(".")]',
     "names = list(filenames)"),
    ("a file that is not a regular file opened", CG,
     "if os.path.exists(path) and not os.path.isfile(path):", "if False:"),
    ("an unreadable file skipped in silence", CG, UNREAD_OLD, UNREAD_NEW),
    ("exit 0 with an unreadable file", CG, "if failed or problems:", "if failed:"),
    ("exit 0 with no hits", CG, "return 0 if total else 1", "return 0"),
    ("a bad pattern raising a traceback", CG, "except ValueError as err:",
     "except KeyError as err:"),
    ("a root that is not a folder ignored", CG, NOT_A_FOLDER_OLD, "            pass"),
    ("--root not required", CG, "required=True", "required=False"),
    ("a closed output raising a traceback", CG, "except BrokenPipeError:", "except KeyError:"),
    ("plain file whitespace collapsed before entities are decoded", CG,
     'return SPACE_RE.sub(" ", htmllib.unescape(raw)), []',
     'return htmllib.unescape(SPACE_RE.sub(" ", raw)), []'),
    ("html tags removed without a space", CG, 'raw = TAG_RE.sub(" ", raw)',
     'raw = TAG_RE.sub("", raw)'),
    ("measure.py counting a phrase that crosses two lines", ME,
     "return any(phrase in line for line in lines)", 'return phrase in " ".join(lines)'),
    ("measure.py ignoring the seed", ME, "rng = random.Random(seed)", "rng = random.Random(1)"),
    ("measure.py searching cleaned lines in place of the lines on disk", ME,
     'lines = raw.split("\\n")',
     'lines = [corpus_grep.clean_line(l) for l in raw.split("\\n")]'),
    ("measure.py rounding down", ME, "percent = (200 * hits + samples) // (2 * samples)",
     "percent = 100 * hits // samples"),
    ("measure.py counting the lines as written after repeats are dropped", ME,
     "as_written = len(corpus_grep.cue_lines(raw, collapse=False))",
     "as_written = len(corpus_grep.cue_lines(raw, collapse=True))"),
    ("measure.py accepting zero", ME, "int(value) < 1", "int(value) < 0"),
    ("measure.py refusing a file with exactly as many words as the longest length", ME,
     "if len(words) < longest:", "if len(words) <= longest:"),
    ("measure.py never drawing the last word", ME,
     "start = rng.randrange(len(words) - length + 1)", "start = rng.randrange(len(words) - length)"),
    ("measure.py accepting a file that is not a vtt or srt", ME,
     "if ext not in corpus_grep.CUE_EXTS:", "if False:"),
    ("make_captions.py writing lines of a different width", MC, "MAX_LINE = 38", "MAX_LINE = 40"),
    ("make_captions.py giving each word a different time", MC, "WORD_MS = 400", "WORD_MS = 500"),
    ("make_captions.py writing a flash cue of a different length", MC, "FLASH_MS = 10",
     "FLASH_MS = 20"),
]


def copy_repo(destination):
    def skip(folder, names):
        return [n for n in names if n == "__pycache__" or n.endswith(".pyc")]

    for item in COPY_ITEMS:
        source = os.path.join(ROOT, item)
        if not os.path.exists(source):
            continue
        target = os.path.join(destination, item)
        if os.path.isdir(source):
            shutil.copytree(source, target, ignore=skip)
        else:
            shutil.copy2(source, target)


class MutationError(Exception):
    """A mutation could not be applied as written."""


def run_one(entry):
    """Return (name, status, detail): status is 'killed' or 'survived'; detail names the first failing test."""
    name, relative, old, new = entry
    with tempfile.TemporaryDirectory(prefix="corpus-grep-mutation-") as scratch:
        copy_repo(scratch)
        path = os.path.join(scratch, *relative.split("/"))
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
        if text.count(old) != 1:
            raise MutationError("%s: the text to replace occurs %d times in %s"
                                % (name, text.count(old), relative))
        changed = text.replace(old, new)
        if changed == text:
            raise MutationError("%s: the copy does not differ from the original" % name)
        with open(path, "wb") as fh:
            fh.write(changed.encode("utf-8"))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                cwd=scratch, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return name, "killed", "timeout"
        if result.returncode == 0:
            return name, "survived", ""
        report = result.stderr.decode("utf-8", "replace").split("\n")
        failed = [l for l in report if l.startswith(("FAIL: ", "ERROR: "))]
        others = [l for l in failed if "(test_examples.Readme)" not in l]
        if not failed:
            return name, "killed", "no test named"
        if not others:
            return name, "killed", "only the README tests: " + failed[0]
        return name, "killed", "%d tests, first outside the README tests: %s" % (
            len(failed), others[0])


def baseline_passes():
    """Run the suite on an unchanged copy; a mutation result means nothing unless this passes."""
    with tempfile.TemporaryDirectory(prefix="corpus-grep-mutation-") as scratch:
        copy_repo(scratch)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-f"],
            cwd=scratch, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=TIMEOUT)
        return result.returncode == 0, result.stderr.decode("utf-8", "replace")


def main(argv):
    ok, report = baseline_passes()
    if not ok:
        print("mutate: the suite fails on an unchanged copy:\n%s" % report[-2000:],
              file=sys.stderr)
        return 2
    chosen = [m for m in MUTATIONS if not argv or any(a in m[0] for a in argv)]
    workers = max(1, min(6, os.cpu_count() or 1))
    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for name, status, detail in pool.map(run_one, chosen):
                print("%s %s" % (status, name) + (" :: " + detail if detail else ""),
                      flush=True)
                results.append(status)
    except MutationError as err:
        print("mutate: %s" % err, file=sys.stderr)
        return 2
    killed = sum(1 for s in results if s == "killed")
    survived = len(results) - killed
    print("mutations: %d, killed: %d, survived: %d" % (len(results), killed, survived))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

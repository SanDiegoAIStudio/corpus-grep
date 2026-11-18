"""Helpers shared by the tests."""

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
for _path in (ROOT, EXAMPLES):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import corpus_grep  # noqa: E402
import make_captions  # noqa: E402
import measure  # noqa: E402

# The grep found on PATH, so the tests also run where grep lives in /bin only.
GREP = shutil.which("grep") or "grep"
TALK_PATH = os.path.join(EXAMPLES, "talk.txt")
SAMPLE_PATH = os.path.join(EXAMPLES, "captions", "MADEUP00001.en.vtt")
README_PATH = os.path.join(ROOT, "README.md")


def read_text(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


def talk_text():
    return read_text(TALK_PATH)


def write(folder, relative, content):
    """Write content (str or bytes) under folder; return the full path."""
    path = os.path.join(folder, *relative.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def vtt(*cues, header="WEBVTT\n\n"):
    """Build a small vtt text from (start, [lines]) pairs; start is HH:MM:SS.mmm."""
    blocks = []
    for start, lines in cues:
        blocks.append("%s --> %s\n%s\n" % (start, start, "\n".join(lines)))
    return header + "\n".join(blocks)


def cli(*args, cwd=None):
    """Run corpus_grep.py as a script; return the completed process."""
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "corpus_grep.py")] + list(args),
        cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace")


def run_main(module, *args):
    """Call module.main(args) in this process; return (code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main(list(args))
    return code, out.getvalue(), err.getvalue()


def run_measure(*args):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "measure.py")] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace")


def grep_count(phrase, path):
    """Count lines of path that hold phrase, as grep -c -F does."""
    result = subprocess.run([GREP, "-c", "-F", "-e", phrase, path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            encoding="utf-8")
    return int(result.stdout.strip())


def header_lines(stdout):
    """Return the '=== ' lines of a search output."""
    return [line for line in stdout.split("\n") if line.startswith("=== ")]


def readme_section(title):
    """Return the fenced blocks of one README section as lists of lines."""
    text = read_text(README_PATH)
    match = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % re.escape(title), text,
                      re.S | re.M)
    if not match:
        raise AssertionError("README has no section %r" % title)
    blocks = []
    current = None
    for line in match.group(1).split("\n"):
        if line.startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append(current)
                current = None
        elif current is not None:
            current.append(line)
    return blocks


def run_block(block):
    """Run the command on the first line of a README block; return its stdout."""
    import shlex
    assert block[0].startswith("$ "), block[0]
    argv = shlex.split(block[0][2:])
    if argv[0] == "python3":
        argv[0] = sys.executable
    result = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, encoding="utf-8")
    return result.stdout, argv


def caption_oracle(lines, phrase):
    """Return the start seconds of the caption line that holds each phrase start.

    lines is the output of make_captions.caption_lines; the phrase is looked up
    in the decoded lines joined with single spaces.
    """
    import html
    texts = [html.unescape(" ".join(words)) for _, words in lines]
    joined = " ".join(texts)
    starts = []
    at = joined.find(phrase)
    while at != -1:
        offset = 0
        for (start_ms, _), text in zip(lines, texts):
            if offset <= at < offset + len(text) + 1:
                starts.append(start_ms // 1000)
                break
            offset += len(text) + 1
        at = joined.find(phrase, at + 1)
    return starts

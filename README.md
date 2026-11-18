# corpus-grep

Phrase search for caption and transcript files. Auto-generated captions split speech into short lines and show each line two or three times, so a plain line search misses most phrases longer than a few words. corpus-grep strips the caption markup, joins the lines, drops the repeats, searches the joined text, and prints every hit with the second it was spoken and a link that opens the video at that second. It is for people who keep caption files of talks and want to find what was said, not only the lines it was split into.

## What you get

The sample folder holds one made-up talk. This command searches it for a phrase of 13 words that crosses several caption lines, and prints the hit with its time and link. It is the output of `python3 corpus_grep.py` as written on the first line of the block:

```
$ python3 corpus_grep.py "growing herbs on a kitchen windowsill and i promise you do not need" --root examples/captions --context 60

=== MADEUP00001 :: Window herbs, a made-up talk  [00:00:02]  https://www.youtube.com/watch?v=MADEUP00001&t=2s
    welcome back to the workshop today we are talking about growing herbs on a kitchen windowsill and i promise you do not need a garden a greenhouse or any special tools to get started a

1 hits across 1 sources / 3 files
```

The same phrase given to `grep -c -F` on the sample caption file counts the lines that hold it. The output of that command:

```
$ grep -c -F "growing herbs on a kitchen windowsill and i promise you do not need" examples/captions/MADEUP00001.en.vtt
0
```

The id MADEUP00001 is made up, so the link above opens no video.

## Quick start

Python 3 and nothing else is needed. There is no install step and no dependency.

1. Get a copy of the repository and change into its folder.
2. Run the command from the section above on the sample captions.
3. Run it on your own folder of caption files:

```
python3 corpus_grep.py "some phrase" --root /path/to/your/captions
```

The sample id MADEUP00001 is made up, so a link printed for the sample files opens no video. Links for your own files are real when the file names carry the video id (see Search).

## Why plain grep misses

A rolling auto-caption file shows each line three times: once as the new line of a cue with a timing tag before every word after the first, once in a cue that lasts ten milliseconds, and once as the first line of the next cue. These are the first four cues of the sample file, after its header block, as written to disk:

```
00:00:00.000 --> 00:00:02.790 align:start position:0%
 
welcome<00:00:00.400><c> back</c><00:00:00.800><c> to</c><00:00:01.200><c> the</c><00:00:01.600><c> workshop</c><00:00:02.000><c> today</c><00:00:02.400><c> we</c>

00:00:02.790 --> 00:00:02.800 align:start position:0%
welcome back to the workshop today we

00:00:02.800 --> 00:00:05.590 align:start position:0%
welcome back to the workshop today we
are<00:00:03.200><c> talking</c><00:00:03.600><c> about</c><00:00:04.000><c> growing</c><00:00:04.400><c> herbs</c><00:00:04.800><c> on</c><00:00:05.200><c> a</c>

00:00:05.590 --> 00:00:05.600 align:start position:0%
are talking about growing herbs on a
```

A phrase that runs over two lines is in no single line, and a line search only looks at one line at a time. This table is quoted as a past measurement, made once on a real auto-captioned talk that is not part of this repository: one talk of about 5,700 words, 840 caption lines once repeats are dropped, 200 random phrases per length. A plain line search found:

| Phrase length | Found by a plain line search |
|---|---|
| 4 words | 62% |
| 6 words | 24% |
| 8 words | 4% |
| 12 words | 0% |

`measure.py` makes the same measurement on a file you give it. This is its output on the sample file, from the command on the first line of the block:

```
$ python3 measure.py examples/captions/MADEUP00001.en.vtt
file: MADEUP00001.en.vtt
caption lines: 255 as written, 85 after repeats are dropped
words: 603 (7.1 per line)
words  found by a plain line search
    4  57% (114 of 200)
    6  32% (64 of 200)
    8  11% (22 of 200)
   12  0% (0 of 200)
```

The two tables differ in detail, because the talks and their line lengths differ, and agree in shape: the longer the phrase, the closer a line search gets to finding nothing.

## Search

```
python3 corpus_grep.py PATTERN --root DIR [--root DIR ...] [options]
```

Options:

| Option | Meaning |
|---|---|
| `PATTERN` | The phrase to find. Literal unless `--regex` is given. Case is ignored unless `--case-sensitive` is given. A literal pattern has its runs of whitespace turned into single spaces. |
| `--root DIR` | A folder to search, recursively. Required. May be given more than once. A folder given twice is searched once. |
| `--regex` | Treat the pattern as a Python regular expression. |
| `--case-sensitive` | Match letter case. |
| `--context N` | Characters of text shown on each side of a match. Default 260. |
| `--max N` | Number of hits printed. Default 40. The summary line still counts all hits. |
| `--list-only` | Print one line per source that has a hit, then the summary line. Two folders can give the same NAME twice. |
| `--no-collapse` | Do not drop repeated lines or repeated phrases. |
| `--no-links` | Do not print video links. |

A regular expression and its output, from the command on the first line of the block:

```
$ python3 corpus_grep.py "water the (seedlings|plants) early" --regex --root examples/captions --context 40

=== MADEUP00001 :: Window herbs, a made-up talk  [00:00:17]  https://www.youtube.com/watch?v=MADEUP00001&t=17s
    soil and a sunny window will do the job water the seedlings early in the morning before the sun gets high

=== MADEUP00001 :: Window herbs, a made-up talk  [00:03:39]  https://www.youtube.com/watch?v=MADEUP00001&t=219s
    e whole point is to enjoy what you grow water the seedlings early in the morning before the sun gets high

2 hits across 1 sources / 3 files
```

### The output, line by line

Each hit prints a header line and one indented line of context:

- `=== NAME :: LABEL  [HH:MM:SS]  LINK`. NAME is the video id when the file name carries one, otherwise the file name without its language piece and extension. LABEL is the title from a titles file when there is one, otherwise the path of the file relative to the `--root` it was found under, written with `/` between parts. For a file directly in that root the label is its file name. The time and the link appear only for cue files (see below) because plain files carry no times. The link appears only when the file name carries a video id and `--no-links` is not given.
- The context line holds the match and up to `--context` characters on each side, with the caption markup removed. Its first characters may begin in the middle of a word.
- After the hits, a blank line and a summary: `N hits across M sources / F files`, followed by ` (showing K)` when `--max` cut the list, and by `, C could not be read` when some files or folders could not be read.
- When nothing matches, one line instead: `no matches for 'PATTERN' across F files in R root(s)`.

With `--list-only` the hits are replaced by one `NAME<TAB>TITLE` line per source that has a hit, in the order of each source's first hit. Two folders can give the same NAME twice. The output of the command on the first line of the block:

```
$ python3 corpus_grep.py "basil" --root examples/captions --list-only
MADEUP00001	Window herbs, a made-up talk

2 hits across 1 sources / 3 files
```

The output of a search with no match:

```
$ python3 corpus_grep.py "no such phrase here" --root examples
no matches for 'no such phrase here' across 4 files in 1 root(s)
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | At least one hit, and nothing failed. |
| 1 | No hit, and nothing failed. |
| 2 | A usage error, a bad pattern, a `--root` that is not a folder, or a file that could not be read. The reason is one line on stderr, such as `corpus-grep: bad pattern: ...`, `corpus-grep: not a folder: PATH` or `corpus-grep: could not read PATH: REASON`. The search still runs over everything that could be read. |

### File types

- Cue files: `.vtt` and `.srt`. They are searched first. The caption markup is removed, the lines are joined, and every hit has a time. A cue file's header block, its `NOTE`, `STYLE` and `REGION` blocks and its cue identifiers are not speech and are not searched.
- Plain files: `.txt`, `.html`, `.md` and `.json`. They are searched as text, in the order of their paths, after the cue files. Hits have no time. For `.html` the tags are replaced by spaces first. An `.html` file is skipped when a `.txt` file of the same name sits in the same folder.
- A `.tsv` file is read for titles and is never searched.
- Entities such as `&amp;` and `&gt;` are decoded before searching, so a search for `tomatoes & basil` finds the text the speaker said.

### Video ids

A file name carries a video id in one of two forms:

- the name up to its first dot is exactly 11 characters from `A-Z`, `a-z`, `0-9`, `_` and `-`, as in `MADEUP00001.en.vtt`, or
- the name ends in an id in square brackets followed only by dot pieces, as in `Window herbs [MADEUP00001].en.vtt`.

The link format is `youtube.com/watch?v=ID&t=SECONDSs`, on the host `www.youtube.com` over https. The seconds are the whole seconds of the hit, hours included.

### Titles file

A tab separated file with the extension `.tsv` anywhere under a root supplies titles. The first column is the video id and the second the title. The first title seen for an id is kept, and a title equal to the id is ignored. Lines without a tab are skipped. A source with no title is labelled with the path of the file relative to the `--root` it was found under, written with `/` between parts. For a file directly in that root the label is its file name.

### Duplicates

Two files are one source when they carry the same video id anywhere, or when they have the same source name and sit in the same folder. A passage that appears in several files of one source is printed once. Two hits count as the same when the source, the matched text and the 40 characters on each side are equal. This keeps a talk that exists as a `.vtt`, an `.srt` and a `.txt` in one folder from printing three times. Because cue files are searched first, the printed copy is the one with a time. The summary counts the hits after duplicates are removed.

### Collapsing

By default two steps remove repeats. The first drops a speech line that equals the line kept just before it, which removes the repeats of a rolling caption. The second runs on the joined text of every file, plain files included, and collapses a phrase of 15 to 80 characters that is repeated directly after itself, up to five times more. `--no-collapse` switches both off. With `--root examples` the search for `gets high` gives 4 hits by default and 6 with `--no-collapse`, because the repeated copies of the caption lines are then searched too.

## Measure your own captions

```
python3 measure.py FILE [--words 4,6,8,12] [--samples 200] [--seed 1]
```

FILE is one `.vtt` or `.srt` file. `measure.py` builds the text of the file with repeats dropped and splits it into words. For each length in `--words`, in the order given, it draws `--samples` phrases: a start position chosen at random, and that many words from there, joined with single spaces. One random generator, started from `--seed`, serves the whole run, so the same seed prints the same numbers.

A phrase counts as found when at least one line of the file, exactly as it is on disk, holds it as a substring. That is what a fixed-string line search (`grep -F`) tests, and a test compares the result with the real `grep -F` on 120 phrases.

The output has the file name, the number of speech lines as written and after repeats are dropped, the number of words, and one line per length with the percentage found and the counts. The percentage is rounded half up to a whole number. The command exits 2 with a one line message on stderr when the file cannot be read, is not a `.vtt` or `.srt` file, has fewer words than the longest length, or an option value is not a positive whole number.

`measure.py` measures a plain line search only. `corpus_grep.py` finds every one of these phrases by construction, because they are drawn from the text it searches. The script reports no score for `corpus_grep.py`.

## Get caption files

Any tool that saves captions as `.vtt` or `.srt` works, and yt-dlp is one that does. Name each file with the video id first, as in `MADEUP00001.en.vtt`, to get links in the output. Use only videos whose captions you are allowed to keep.

## Tests

Two commands, run from the folder of the repository:

```
python3 -m unittest discover -s tests
python3 tests/mutate.py
```

The first runs 196 tests: unit tests for the markup removal, the repeat collapsing and the time map, end-to-end tests of the command and of `measure.py`, and tests that the sample files and the output pasted in this README equal fresh runs. Five of them run the `grep` found on your PATH to compare with a plain line search, so the tests need a `grep`; the tools themselves do not. The second makes 80 deliberate changes to a copy of the code, one at a time, and runs the test suite against each copy. A change that makes no test fail is reported as a survivor. In the last run 80 were killed and 0 survived. The run takes a few minutes.

## Limits

- The tests ran on macOS 27.2.1 with Python 3.9.6 at `/usr/bin/python3`. Other systems and Python versions were not tried.
- Each file is read whole into memory.
- Files are read as UTF-8 only. Bytes that are not valid UTF-8 are replaced by the Unicode replacement character, so text in another encoding will not match.
- A sentence a speaker really says twice in a row is collapsed like a caption repeat. `--no-collapse` shows it.
- The second collapsing step only looks at repeated phrases of 15 to 80 characters. A shorter or longer repeat is left as it is.
- Text between a `<` and the next `>` on a line is treated as markup and removed from cue files, even when it was spoken or typed as text.
- `.json` and `.html` files are searched as plain text, so keys and attribute text can match.
- Any file whose name is exactly 11 characters from the id alphabet before its first dot, such as `description.txt`, is taken to carry a video id. As a cue file it gets a link that opens nothing (`--no-links` turns links off), and two such files with the same name in two folders count as one source, so a passage they share prints once.
- With two or more `--root` folders, two files at the same path under different roots print the same `=== NAME :: LABEL` header, because the label is the path under its own root. They count as two sources unless the name carries a video id.
- Linked folders are not entered, and folders and files whose names start with a dot are skipped.
- The link format is for one video site.
- Captions belong to whoever made the video. Search copies you are allowed to hold.

## License

MIT. See `LICENSE`.

## Built at San Diego AI Studio

corpus-grep comes out of San Diego AI Studio, the builders' community in San Diego, where builders show the systems they run: https://sandiegoaistudio.com/projects

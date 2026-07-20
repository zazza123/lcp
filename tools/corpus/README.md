# Corpus diff tool

This directory holds a small measurement tool for the scanner and
generator, plus the corpus it runs against.

**This is not a test.** `snapshot.py` never fails a build — a library that
cannot be imported or scanned is recorded as an error and the run
continues — and `compare.py` always exits `0`. Nothing here gates CI.
What it produces is a report a human reads before deciding whether a
change to `src/lcp/scanner.py` or `src/lcp/generator.py` is safe, by
showing what that change actually did to a few dozen real-world packages'
manifests, not just to the unit tests.

## When to run it

Any change that touches `src/lcp/scanner.py` or `src/lcp/generator.py`.
Use the `core` tier while iterating — it installs in under a minute and
covers the scanner behaviours in `libraries.txt` (facades, missing
`__all__`, proxy objects, non-callable sentinels, UPPER_CASE value
objects, strict `__all__` discipline, ordinary mid-size surfaces). Run the
`full` tier once, before opening the PR — it adds the C-extension-heavy
and very-large-surface libraries (`numpy`, `scipy`, `pandas`, `pyarrow`,
`polars`, `pillow`, `sqlalchemy`, `boto3`, `botocore`, `aiohttp`,
`fsspec`), where the largest measured scanning risk lives, at the cost of
several minutes and a few hundred megabytes of installs.

## Setup

The corpus venv is local and gitignored; build it once. `constraints.txt`
is committed and pins every package this venv needs to an exact version —
installing with `-c constraints.txt` is what makes one person's numbers
comparable to anyone else's; skipping it means you get whatever PyPI
happens to serve today:

```bash
cd tools/corpus
python -m venv .venv   # or $(pyenv root)/versions/3.12.0/bin/python -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -c constraints.txt pydantic click jsonschema "fastmcp>=3.0,<4" docstring_parser
./.venv/bin/pip install -c constraints.txt $(awk '$1=="core" && !/^#/ {print $2}' libraries.txt)
```

This installs only the `core` tier, which is the cheap one (under a
minute). Add the `full` tier separately, when you actually need it — it
pulls in `numpy`, `scipy`, `pandas`, `pyarrow`, `polars`, `pillow` and
more, at the cost of several minutes and a few hundred megabytes:

```bash
./.venv/bin/pip install -c constraints.txt $(awk '$1=="full" && !/^#/ {print $2}' libraries.txt)
```

The `pydantic`/`click`/`jsonschema`/`fastmcp`/`docstring_parser` line
mirrors `[project].dependencies` in `pyproject.toml` — the corpus venv
needs to import the *scanned output* of `lcp`, i.e. the same runtime
dependencies `lcp` itself needs, not `lcp` itself. Update this line
whenever that dependency list changes.

`lcp` itself is never installed into this venv. `snapshot.py` is pointed
at a checkout's `src/` directory with `--src`, which is what lets the
same venv measure two different versions of the scanner without
reinstalling anything.

## Comparing before and after a change

The recipe below assumes you're back at the repo root (Setup above is run
from `tools/corpus`; `cd` back out before continuing). It uses a worktree
for the "before" side, so both snapshots come from real, unmodified
checkouts and the venv only has to be built once:

```bash
git worktree add /tmp/lcp-before main
tools/corpus/.venv/bin/python tools/corpus/snapshot.py \
    --src /tmp/lcp-before/src -o tools/corpus/before.json --tier full
tools/corpus/.venv/bin/python tools/corpus/snapshot.py \
    --src ./src -o tools/corpus/after.json --tier full
tools/corpus/.venv/bin/python tools/corpus/compare.py tools/corpus/before.json tools/corpus/after.json
git worktree remove /tmp/lcp-before
```

Point `git worktree add` at whatever ref you're diffing against — usually
`main`, but a previous commit on your own branch works too. Use `--tier
core` in place of `--tier full` while iterating, then re-run with `--tier
full` before opening the PR.

## Reading the report

A **PROVENANCE DIFFERENCES** banner prints above everything else, but only
when the two snapshots' recorded Python version or a library version
differs. It is informational, not a section to act on by itself — but it's
often the actual explanation for a diff below it (a library upgraded
between the two snapshots looks exactly like a scanner change unless you
know the corpus itself moved).

Below that, `compare.py` prints five sections, in this order:

1. **REMOVED** — symbols present before and gone after. Almost always a
   regression: something the scanner used to find, it no longer does.
2. **KIND CHANGED** — a symbol survived but its kind flipped (e.g.
   `function` to `class`). Usually a sign of a classification bug.
3. **MODULE CHANGED** — a symbol survived but its recorded `module`
   changed, grouped by library with up to three sample symbol ids. Usually
   points at an attribution regression in `generator.py`.
4. **SUMMARY CHANGED** — a symbol survived but its `summary` text changed,
   grouped the same way. Usually points at a regression in docstring
   extraction (`docstrings.py`). A library-wide spike here — most or all
   of a library's symbols changing at once — is the signature of a broad
   summary-extraction regression, not of many small, independent doc edits.
5. **ADDED** — symbols present after that weren't before, grouped by
   library and object type. Additions are usually an intended
   improvement, not a regression, but a spike in one specific object
   type (e.g. every new addition being a `constant` when the change was
   meant to touch functions) is worth reading, not just counting — this
   is how a mislabelling risk showed up in #61 while an unrelated
   regression showed up as removals.

A trailing **COVERAGE DIFFERENCES** section lists, per library, one of
five states: `only_in_before`, `only_in_after` (the library is missing
from one snapshot entirely), or `failed_in_before`, `failed_in_after`,
`failed_in_both` (the library's scan raised on that side). It is *not* a
documentation-coverage metric despite the name similarity to `lcp
coverage` — it exists specifically to catch a library that stopped
scanning, or was dropped from the corpus, before that gets misread as the
library's symbols having been silently removed. A library listed here
contributes **no** entries to any of the five sections above: seeing
`scipy failed_in_after` means scipy's scan crashed, not that scipy lost
every symbol. The section is omitted entirely when there are no such
libraries.

The ordering — removals, then kind changes, then module changes, then
summary changes, then additions — is deliberate: it puts the most
suspicious category first, since a scanner change that removes symbols
needs the fastest attention, while an addition usually just needs reading.

An empty run — every section at `(0)`, no coverage section, no
provenance banner — is the expected result of comparing two snapshots of
the *same* checkout. If two runs over identical inputs ever produce a
non-empty diff, that means some ordering in the scanner or generator is
unstable, which is a defect in its own right and not something to wave
away.

## Refreshing `constraints.txt`

This is the one place the corpus venv is installed **unpinned**, on
purpose — moving the pins forward is the entire point of this recipe.
Everywhere else in this README (Setup) installs *with* `-c
constraints.txt`; this is the deliberate exception that produces a new
one:

```bash
./.venv/bin/pip install --upgrade $(awk '!/^#/ && NF {print $2}' libraries.txt)
./.venv/bin/pip freeze > constraints.txt
```

Do this deliberately and commit it on its own, never as part of a
scanner change. A snapshot taken with an older `constraints.txt` is not
comparable to one taken after a refresh — the diff would then conflate
whatever the scanner change did with whatever the library upgrade did,
which is exactly the confusion pinning exists to prevent. Never
hand-edit `constraints.txt`; it only ever comes from `pip freeze`.

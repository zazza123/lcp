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

The corpus venv is local and gitignored; build it once:

```bash
cd tools/corpus
python -m venv .venv   # or $(pyenv root)/versions/3.12.0/bin/python -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install pydantic click jsonschema "fastmcp>=3.0,<4" docstring_parser
./.venv/bin/pip install $(awk '!/^#/ && NF {print $2}' libraries.txt)
./.venv/bin/pip freeze > constraints.txt
```

`lcp` itself is never installed into this venv. `snapshot.py` is pointed
at a checkout's `src/` directory with `--src`, which is what lets the
same venv measure two different versions of the scanner without
reinstalling anything.

## Comparing before and after a change

The standard recipe uses a worktree for the "before" side, so both
snapshots come from real, unmodified checkouts and the venv only has to
be built once:

```bash
git worktree add /tmp/lcp-before main
tools/corpus/.venv/bin/python tools/corpus/snapshot.py \
    --src /tmp/lcp-before/src -o before.json --tier full
tools/corpus/.venv/bin/python tools/corpus/snapshot.py \
    --src ./src -o after.json --tier full
tools/corpus/.venv/bin/python tools/corpus/compare.py before.json after.json
git worktree remove /tmp/lcp-before
```

Point `git worktree add` at whatever ref you're diffing against — usually
`main`, but a previous commit on your own branch works too. Use `--tier
core` in place of `--tier full` while iterating, then re-run with `--tier
full` before opening the PR.

## Reading the report

`compare.py` prints three sections, in this order:

1. **REMOVED** — symbols present before and gone after. Almost always a
   regression: something the scanner used to find, it no longer does.
2. **KIND CHANGED** — a symbol survived but its kind flipped (e.g.
   `function` to `class`). Usually a sign of a classification bug.
3. **ADDED** — symbols present after that weren't before, grouped by
   library and object type. Additions are usually an intended
   improvement, not a regression, but a spike in one specific object
   type (e.g. every new addition being a `constant` when the change was
   meant to touch functions) is worth reading, not just counting — this
   is how a mislabelling risk showed up in #61 while an unrelated
   regression showed up as removals.

A trailing **COVERAGE DIFFERENCES** section appears only when the
documentation coverage percentage for some library changed, and is
omitted entirely otherwise. The ordering — removals, then kind changes,
then additions — is deliberate: it puts the most suspicious category
first, since a scanner change that removes symbols needs the fastest
attention.

An empty run — `REMOVED (0)`, `KIND CHANGED (0)`, `ADDED (0)`, no
coverage section — is the expected result of comparing two snapshots of
the *same* checkout. If two runs over identical inputs ever produce a
non-empty diff, that means some ordering in the scanner or generator is
unstable, which is a defect in its own right and not something to wave
away.

## Refreshing `constraints.txt`

Re-run the setup's `pip freeze` step to move the corpus onto newer
library releases:

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

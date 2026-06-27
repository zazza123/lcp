---
name: lcp-configure
description: >-
  Use this skill to install, set up, fix, or configure the LCP plugin so its
  `lcp serve-all` MCP server actually starts and resolves libraries — the
  configuration side of LCP, not its lookup tools. Reach for it the moment LCP
  isn't working or needs adjusting, including right after installing the plugin
  when the user doesn't know what to do next or what belongs in its `.lcp.json`.
  Trigger it when: the lcp MCP server won't start or errors on launch (e.g.
  `-32000`, "could not resolve a runnable lcp"); LCP can't find, resolve, or
  load the user's libraries; LCP must launch from a specific lcp binary, venv,
  pyenv, conda, or Python interpreter; the user wants a private/team registry, a
  whitelist of served libraries (`expose`), or libraries preloaded at startup
  for fast first lookups. Treat "get LCP working", "set up LCP", or "fix LCP" as
  a trigger even when no config file, JSON, or `.lcp.json` is named — these are
  all configuration tasks. Do not use it for running LCP's lookup tools
  (resolving or browsing a library's API), setting an editor's Python
  interpreter, or writing code that parses the config.
---

# Configure the LCP plugin (`.lcp.json`)

The LCP plugin runs a single MCP server, `lcp serve-all`, started by
`${CLAUDE_PLUGIN_ROOT}/bin/serve.sh`. That wrapper reads a small JSON config
file — `.lcp.json` — to decide **which `lcp` to launch** and **how the server
should behave**. Most users never need to touch it (the plugin auto-detects a
runnable `lcp` and uses the official registry), but it matters when `lcp` lives
in a virtualenv that isn't on `PATH`, when a team runs a private registry, or
when someone wants to restrict or warm specific libraries.

Your job is to run a short, friendly wizard: figure out what the user needs, ask
one thing at a time, **write a valid config**, and then **verify it actually
works** so they aren't left guessing. Never block them — if a check fails, write
the best config you can and tell them exactly what to fix by hand.

## Where the config lives (precedence)

`serve.sh` looks for config in this order and uses the **first** it finds:

1. **Project:** `.lcp.json` at the project root (the session's working
   directory — `$CLAUDE_PROJECT_DIR`).
2. **Global:** `~/.lcp/config.json`.

Default target: **project `.lcp.json` when working inside a project**, otherwise
the **global** `~/.lcp/config.json`. Always let the user choose — a project file
is right for "this repo uses a private registry", a global file for "set up lcp
on my machine once". Note that a project `.lcp.json` *shadows* the global file,
so if a user has a working global config and you create an empty/partial project
file, you can accidentally hide it. Only write keys you actually set.

## The fields

These five keys are the entire schema `serve.sh` understands. Treat this table
as the source of truth; if you're unsure, open `bin/serve.sh` in the plugin and
confirm the keys it reads (`lcp_config_get`) before inventing anything.

| Field | Type | Effect |
|-------|------|--------|
| `command` | string | Full path to an `lcp` executable to launch the server with. Use when `lcp` is in a venv/pyenv/conda env not on `PATH`. |
| `python` | string | Full path to a Python interpreter that has `lcp` installed; the server runs as `<python> -m lcp`. Used only if `command` is empty/unresolvable. |
| `registries` | array of strings | Registry base URLs. **Only the first is active** (passed as `--registry`). Empty = the official registry default. |
| `expose` | array of strings | Whitelist of library names the universal server will serve. Empty = any library is allowed. |
| `preload` | array of strings | Libraries to resolve at startup so the first lookup is instant. |

`command` and `python` are mutually-prioritized launchers: `serve.sh` tries
`command` first, then `python -m lcp`, then auto-detects (project `.venv`/`venv`,
active `$VIRTUAL_ENV`, `uv`/`uvx`/`pipx`, bare `lcp` on `PATH`). **If
auto-detection already finds a runnable `lcp`, leave both empty** — an override
that later breaks is worse than no override.

## Wizard workflow

Ask one question at a time; don't dump the whole questionnaire at once. Skip
steps the user clearly doesn't need (e.g. if `lcp --version` already runs, don't
interrogate them about launcher paths — just confirm and move on).

### Step 0 — Locate and load

1. Decide the target file with the user (project vs global, per the precedence
   above). Confirm the absolute path you'll write.
2. If the file exists, **read it and parse the JSON**. Keep every existing key —
   you will *merge*, never clobber unrelated settings.
3. If it exists but is **malformed JSON**, that alone breaks the server. Show the
   user the parse error and the offending content, and offer to rewrite it
   cleanly from the values you can recover plus their answers.

### Step 1 — Launcher (`command` / `python`)

Goal: ensure `serve.sh` can find a runnable `lcp`.

1. Probe auto-detection first (see Validation below). If a candidate answers
   `--version`, tell the user which one and that **no launcher override is
   needed** — leave `command`/`python` unset.
2. If nothing resolves, ask whether they have `lcp` installed in a specific
   place. Two good outcomes:
   - They give a path to the `lcp` binary → validate `<path> --version`, set
     `command`.
   - They give a Python interpreter that has `lcp` → validate
     `<python> -m lcp --version`, set `python`.
3. If they don't have `lcp` anywhere, point them at installation
   (`pipx install lcp`, `uv tool install lcp`, or `pip install lcp` in their
   project venv), then re-probe.

### Step 2 — `registries`

1. Explain plainly: empty means the official public registry; set this only to
   point at a **team/private** registry of pre-built manifests. Only the first
   URL is used.
2. If they want one, collect the base URL(s), **check reachability** (see
   Validation), and set `registries`. A URL that 404s on the probe is usually a
   wrong base path — flag it rather than silently saving it.

### Step 3 — `expose`

1. Explain: this is a **whitelist** — when set, the universal server will only
   serve those libraries; everything else is refused. Empty = no restriction.
   This is for teams who want to limit the surface to an approved set.
2. If they want it, collect package names. Optionally sanity-check each is
   importable in the resolved environment; warn (don't block) on ones that
   aren't installed — they may be installed later.

### Step 4 — `preload`

1. Explain: listed libraries are resolved at server startup, trading a bit of
   startup time for an instant first lookup. Good for the handful of libraries a
   project leans on heavily.
2. Suggest candidates from what's installed (and from `expose` if set). Collect
   names and set `preload`.

### Step 5 — Write and verify

1. Merge the answers into the loaded config and write **valid, 2-space-indented
   JSON** to the chosen path. Only include keys that have values.
2. Verify: re-parse the file as JSON; re-run the launcher `--version` probe with
   the final `command`/`python`; re-check any registry URL.
3. Print a short summary — what was set, the file path, and which launcher won —
   then remind the user that **MCP servers reload on a new session or via
   `/mcp`**, so they should reload for changes to take effect.

## Repair mode (diagnose first)

When you're invoked because something is *broken* (server won't start, tools
can't resolve a library), don't run the full wizard. Find the failing piece and
fix only that:

- **Server won't start / `-32000` / "could not resolve a runnable lcp":** the
  launcher can't be found. Go to Step 1 — probe auto-detect, and if it fails,
  set `command`/`python` to a path that passes `--version`.
- **Malformed `.lcp.json`:** Step 0 — show the parse error, rewrite cleanly.
- **A project file is shadowing a good global one:** check whether an
  almost-empty project `.lcp.json` is hiding `~/.lcp/config.json`; offer to
  remove or complete it.
- **Library never resolves:** check whether `expose` is set and is excluding it,
  or whether the active registry URL is wrong/unreachable.

## Validation (how to actually check things)

Run these with the user's shell. They're cheap and turn "I think it's
configured" into "I confirmed it works".

- **Launcher probe** — try candidates in `serve.sh`'s order; the first that
  prints a version wins:
  - `<command> --version`
  - `<python> -m lcp --version`
  - project venv: `./.venv/bin/lcp --version` (or `./venv/bin/lcp`)
  - active venv: `"$VIRTUAL_ENV"/bin/lcp --version`
  - `lcp --version`, then `uvx lcp --version`, then `pipx run lcp --version`
- **Registry reachability** — a manifest lives at
  `{registry}/manifests/{language}/{first_letter}/{slug}/{version}.lcp.json.gz`,
  where `{slug}` is the hyphenated package name. A quick liveness check on a
  known package, e.g.:
  `curl -sI -o /dev/null -w '%{http_code}\n' "{registry}/manifests/python/r/requests/latest.json"`
  (a `2xx`/`3xx` on the base host confirms it's reachable; don't hard-fail on a
  single 404 — just surface it).
- **JSON validity** — `python3 -m json.tool <path> >/dev/null` (a non-zero exit
  means the file won't parse and the server will ignore it).

## Principles

- **Never block.** Every probe failure becomes an actionable message, not a dead
  end. Worst case: write the best config you can and tell the user what to verify.
- **Merge, don't clobber.** Preserve keys you didn't ask about.
- **Empty beats wrong.** When auto-detection works, leave launchers unset.
- **Confirm, don't assume.** Show the final file and the verification result so
  the user trusts the outcome.

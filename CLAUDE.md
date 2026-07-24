# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A GitHub Action (Marketplace-published) that builds a WordPress Playground link
(`https://playground.wordpress.net/?blueprint-url=...`) from a plugin zip that
the caller has already uploaded as a GitHub Actions artifact. It resolves the
artifact to a public URL via the third-party [nightly.link](https://nightly.link)
proxy, constructs a Playground blueprint (install/activate plugin, optional
extra plugins/theme, WP/PHP version, multisite), and can optionally post the
link as a sticky PR comment.

It intentionally does **not** handle making a zip public for private
repositories — that's a separate, harder problem (see `accessibility-checker-pro`'s
`.github/workflows/playground-link.yml` for that pattern: an orphan branch +
short-lived tokenized `raw.githubusercontent.com` URL). This action only
supports the nightly.link path, which requires a public repo/artifact.

## How callers trigger this (three modes, all documented with full working examples in README.md's "Trigger modes" section)

This action itself has no trigger of its own — it's a single step a caller's
workflow invokes. The three ways a *caller* workflow wires it up differ
mainly in **where the `run-id` comes from**, since the action needs to know
which run's artifact to point `nightly.link` at:

1. **Manual (`workflow_dispatch`)** — caller workflow declares `run_id`,
   `artifact_name`, and `pr_number` as dispatch inputs, since a manually
   dispatched run has no artifact of its own; `run-id` must be passed in
   explicitly from a prior build run's ID.
2. **Automatic (`pull_request: types: [opened, synchronize, reopened]`)** —
   the same job builds the zip, uploads the artifact, and calls this action,
   all in one run, so `run-id`/`repository` are left at their defaults (the
   current run/repo). **Caveat that matters if this doesn't seem to work**:
   GitHub gives `pull_request`-triggered workflows a **read-only**
   `GITHUB_TOKEN` when the PR is from a fork, no matter what `permissions:`
   the workflow declares — so `post-comment` silently can't write a comment
   on fork PRs under this trigger. That's a GitHub platform restriction, not
   a bug in this action.
3. **Label-triggered (`pull_request: types: [labeled]`, gated on
   `github.event.label.name == 'playground'`)** — for "build always, link on
   demand" setups. The caller workflow looks up the latest successful build
   run for the PR's head SHA via `gh api repos/{repo}/actions/runs?head_sha=...`
   (filtered by workflow name and `status=success`, `sort_by(.created_at) | last`)
   to get `run-id`, rather than taking it as an input, then removes the
   trigger label afterwards so re-adding it mints a fresh link without
   rebuilding. Same fork-PR `GITHUB_TOKEN` caveat as mode 2 applies.

If asked to add or modify a caller workflow that uses this action, check
README.md's "Trigger modes" section first — it has the complete, YAML-valid
example for each of the three above; don't invent a fourth pattern unless
none of these fit.

## Commands

```sh
# Run the Python unit tests (blueprint construction, slug inference)
python3 -m unittest discover -s tests -v
```

There is no build step — this is a composite action (bash + `python3`), not
JS/TS or Docker.

## Architecture

- `action.yml` — the composite action definition. Steps, in order: (1) refuse
  to run against a private repo, since nightly.link can't proxy it (only
  checked for the default `repository` input — see the "known limitations"
  note in the README); (2) validate `post-comment` inputs early (`pr-number`
  must be a positive integer, `github-token` must be set); (3) if
  `github-token` is set, verify via the Actions API (`gh api .../artifacts`)
  that a non-expired artifact named `artifact-name` actually exists in the
  target run, failing loudly if not — otherwise print a `::notice::` that
  verification was skipped. That step also keeps the matched artifact's ID
  and exposes it as the `artifact-id`/`artifact-download-url` outputs, since
  a download link can't be built without it and the lookup already has it.
  Two details there are load-bearing: the name is matched inside jq via
  `env.ARTIFACT_NAME` (an `--arg` flag would not work — `gh api`'s `--jq`
  doesn't proxy jq's own CLI flags), and the result is trimmed with `${IDS%%...}`
  rather than piped to `head -1`, which under `set -o pipefail` would kill
  `gh` with SIGPIPE and fail the step; (4) run `scripts/build_blueprint.py`
  to produce the `playground-url`/`zip-url`/`plugin-path` outputs; (5) if
  `post-comment` is true, an `actions/github-script` step posts/updates a
  sticky PR comment (idempotent via an HTML marker, matching the pattern from
  `accessibility-checker-pro`'s `playground-link.yml`). With
  `comment-build-details: true` that comment also carries artifact-download
  and workflow-run links, so it can stand in for a caller's own build comment;
  the artifact line is omitted (not broken) when no `github-token` was given.
  `comment-template` replaces the body outright (placeholder substitution over
  `{playground_url}` etc.) and takes precedence over `comment-build-details`.
  Two rules there exist to prevent silent breakage: the marker is force-prepended
  when a template omits it (without it the comment stops being sticky and every
  build posts a new one), and an unrecognized `{placeholder}` is left verbatim
  plus warned about rather than substituted as `undefined` — a typo should be
  visible in the posted comment, not a dead link. The regex is `[a-z_]+`, which
  deliberately does not match literal braces like `{"a":1}` in prose or code.
- `scripts/build_blueprint.py` — all the actual logic, kept out of `action.yml`'s
  inline `run:` block so it's testable. Key pieces:
  - `build_zip_url()` — constructs the `nightly.link` URL from `repository` +
    `run-id` + `artifact-name` (URL-encoding `artifact-name`, since artifact
    names may contain spaces/special characters).
  - `infer_slug()` — derives the plugin slug from the artifact name by
    stripping a trailing version/build/hash suffix (regex), since Playground
    needs the `{slug}/{slug}.php` path to activate the plugin and there's no
    reliable way to get that without downloading and unzipping the artifact.
    This is a best-effort heuristic; `plugin-slug` input overrides it.
    Deliberately conservative: it will NOT strip a bare trailing `-<digits>`
    unless there's also a dotted version or a long hex hash present, because
    several real, popular plugin slugs end in a plain number themselves (e.g.
    Contact Form 7's slug is literally `contact-form-7`) — an earlier version
    of this regex stripped that "-7" and produced a broken activation path.
  - `build_blueprint()` — assembles the Playground blueprint JSON. Verified
    against the live blueprint schema at
    `https://playground.wordpress.net/blueprint-schema.json`:
    `installPlugin`/`installTheme` take `options.activate` directly (no
    separate `activatePlugin` step needed), multisite is enabled via a
    dedicated `{"step": "enableMultisite"}` step (not a top-level flag), and
    `preferredVersions: {php, wp}` is a top-level field.
  - `build_playground_url()` — base64-encodes the blueprint as a
    `data:application/json;base64,...` URI and URL-quotes it into the
    `playground.wordpress.net` link.
  - `write_github_output()` — writes each `$GITHUB_OUTPUT` entry using the
    heredoc-style `key<<DELIM` / `DELIM` form with a random per-call
    delimiter, not a plain `key=value\n` line. A plain line breaks (and is
    a real output-injection vector) if the value contains a newline — since
    `plugin-path` is derived from `artifact-name`, an action input, a value
    like `artifact-name: "evil\nfake-output=pwned"` would otherwise forge an
    entirely separate output that GitHub Actions' runtime would parse as
    real. Confirmed exploitable against a naive `key=value` write before
    fixing it; if you ever touch this function, re-verify with a real
    reimplementation of the `$GITHUB_OUTPUT` parser (see
    `tests/test_build_blueprint.py`'s `parse_github_output()`), not a
    substring check — a substring check can't tell a forged extra key
    apart from an inert single-output value.
- `tests/test_build_blueprint.py` — plain `unittest`, no external test deps.
  Includes `parse_github_output()`, a small reimplementation of GitHub's
  actual `$GITHUB_OUTPUT` parsing logic (state machine: plain `key=value`
  lines vs. `key<<DELIM` multiline blocks) — tests use it instead of
  substring-matching the raw file, since a substring check would pass even
  on a vulnerable plain-write implementation.
- `.github/workflows/test.yml` — end-to-end check: downloads a real public
  zip (WordPress.org's Hello Dolly plugin), re-uploads it as an artifact
  (mirroring how a real caller uses this action), runs the action against it,
  and asserts on the decoded blueprint shape.
- `.github/workflows/release.yml` — on a `vX.Y.Z` tag push, force-moves the
  floating `vX` major tag to match, so callers can pin `@v0`. Has a
  `concurrency` group so two close-together tag pushes can't race each other.
- `.github/workflows/lint.yml` — runs `actionlint` against the workflow files
  in `.github/workflows/` only. It does **not** lint `action.yml`: actionlint
  parses its input as a *workflow*, so pointing it at an action definition
  produces spurious "on section is missing"/"unexpected key" errors. Nothing
  statically checks `action.yml` — the composite action's bash is covered only
  by `test.yml`'s live run and manual verification. Pinned to a commit SHA
  (not a floating tag), since it's
  a third-party action; the SHA was verified against the real tag before
  pinning (see commit history if it ever needs bumping — re-verify the new
  SHA the same way, don't just trust a new tag name).
- `.github/dependabot.yml` — weekly `github-actions` ecosystem updates with
  `directory: "/"`, which (per GitHub's own docs) covers both
  `.github/workflows/*.yml` and `action.yml` at the repo root in one entry —
  this repo's composite action lives at the root, not a subdirectory, so a
  second entry isn't needed. This exists because a manual audit (checking
  `actions/checkout`, `actions/upload-artifact`, `actions/github-script`,
  and `raven-actions/actionlint` against their real current releases) found
  several of them 2-3 majors behind with no automated alerting in place.

## Extending this action

Adding a new input touches five places — miss one and it'll look wired up
but silently do nothing:
1. `action.yml`'s `inputs:` block (with a description) and its `env:` wiring
   into the "Build the Playground link" step.
2. `scripts/build_blueprint.py`'s `main()` (read the env var) and, if it
   affects the blueprint shape, `build_blueprint()`'s parameters/body.
3. `tests/test_build_blueprint.py` — at minimum a case in `TestBuildBlueprint`
   or `TestMain`.
4. README.md's Inputs table.
5. This file, if the change affects the architecture description above or
   adds a new trigger-relevant caveat.

## Testing philosophy for this repo

The Python unit tests (`tests/test_build_blueprint.py`) are real and worth
trusting for `scripts/build_blueprint.py`. But `action.yml`'s own bash/YAML
has no unit-test layer of its own — only `.github/workflows/test.yml`'s
live end-to-end run and manual local verification cover it. Four real,
shipped bugs in this repo were only caught by actually *executing* something
rather than reading it and reasoning about correctness:
- A `${{ inputs.pr-number }}` interpolated directly into a `run:` string
  (instead of via `env:`) was a live shell-injection vuln — found by
  rendering the exact template with a malicious value and watching it run.
- `gh api --jq --arg` looks like valid jq-passthrough syntax but isn't —
  `gh api`'s `--jq` doesn't proxy jq's own CLI flags. Found by actually
  running the command.
- The slug-inference regex looked correct on the reference example but
  broke on `contact-form-7` (a real, extremely common WordPress plugin
  slug) and later on hex-only English words like `facade` — found by
  running the regex against real plugin/artifact names, not synthetic ones.
- A plain `key=value\n` write to `$GITHUB_OUTPUT` looked fine on every
  realistic input, but an `artifact-name` containing a newline could forge
  an entirely separate, fake output — found by running a real
  reimplementation of GitHub's `$GITHUB_OUTPUT` parser against the output,
  not by eyeballing the write code (a substring check of the raw file would
  have missed it, since the forged line is textually present either way;
  what mattered was *how it gets parsed*).

When touching `action.yml`'s bash/`gh api` calls or `build_blueprint.py`'s
regex/URL logic, actually run it (`bash -c`, a real `gh api` call against a
public repo, or the Python function directly) against a deliberately
adversarial or real-world input before trusting it — this codebase has a
track record of "obviously correct" code that wasn't.

## Cutting a release

1. Tag `vX.Y.Z` on `main` and push the tag — `release.yml` force-moves the
   floating `vX` tag to match automatically.
2. **First release only**: creating a GitHub Release from that tag has a
   one-time "Publish this Action to the GitHub Marketplace" checkbox in the
   UI. This is a manual step with no file/workflow representation — it can't
   be automated from within the repo, and there's nothing to grep for to
   confirm it's been done.

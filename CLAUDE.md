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
  verification was skipped; (4) run `scripts/build_blueprint.py` to produce
  the `playground-url`/`zip-url`/`plugin-path` outputs; (5) if `post-comment`
  is true, an `actions/github-script` step posts/updates a sticky PR comment
  (idempotent via an HTML marker, matching the pattern from
  `accessibility-checker-pro`'s `playground-link.yml`).
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
- `tests/test_build_blueprint.py` — plain `unittest`, no external test deps.
- `.github/workflows/test.yml` — end-to-end check: downloads a real public
  zip (WordPress.org's Hello Dolly plugin), re-uploads it as an artifact
  (mirroring how a real caller uses this action), runs the action against it,
  and asserts on the decoded blueprint shape.
- `.github/workflows/release.yml` — on a `vX.Y.Z` tag push, force-moves the
  floating `vX` major tag to match, so callers can pin `@v1`.

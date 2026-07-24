# WordPress Playground Link

A GitHub Action that turns a plugin zip you've already uploaded as a build
artifact into a one-click [WordPress Playground](https://playground.wordpress.net/)
link — no zip hosting to set up yourself.

It works by pointing [nightly.link](https://nightly.link) at your artifact
(which turns a normal, auth-gated Actions artifact into a public, CORS-enabled
URL) and building a Playground blueprint around it. Optionally, it can post
the link as a sticky comment on a pull request.

**Requirements:** your repository and the artifact must be public — nightly.link
cannot proxy private-repo artifacts. If you need a Playground link for a
private-repo PR build, this action isn't the right tool; you'll need your own
short-lived tokenised-URL flow instead.

This action fails fast if it detects the current repository is private, via
`github.event.repository.private`. That check only fires when (a) you're
using the *default* `repository` input (an overridden, different repo isn't
checked at all), and (b) the triggering event's payload actually includes a
populated `repository` object — some trigger contexts may not, in which case
the check is silently skipped. In either gap case you'll get a dead
Playground link at click time instead of an early error in the Actions log.

Boolean inputs (`activate-on-load`, `multisite`, `extra-plugins-activate`,
`extra-theme-activate`) accept `true`/`false`/`1`/`0`/`yes`/`no`/`on`/`off`
(case-insensitive) and fail the run on anything else, rather than silently
treating a typo as `false`.

## Usage

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Build plugin zip
        run: ./bin/build-zip.sh   # however you produce your plugin zip

      - uses: actions/upload-artifact@v7
        with:
          name: my-plugin
          path: my-plugin.zip

      - name: Generate Playground link
        id: playground
        uses: pattonwebz/wordpress-playground-action@v0
        with:
          artifact-name: my-plugin
          github-token: ${{ secrets.GITHUB_TOKEN }}   # optional, see "Artifact verification" below

      - run: echo "${{ steps.playground.outputs.playground-url }}"
```

### Posting a PR comment

```yaml
      - uses: pattonwebz/wordpress-playground-action@v0
        with:
          artifact-name: my-plugin
          post-comment: 'true'
          pr-number: ${{ github.event.pull_request.number }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
          expiry-note: 'This link uses a GitHub Actions artifact and will stop working after the artifact retention period (default 90 days) or if the workflow run is deleted.'
```

Requires `pull-requests: write` permission on the job/workflow.

### Artifact verification

If you pass `github-token`, the action calls the Actions API to confirm a
non-expired artifact named `artifact-name` actually exists in that run before
building a link — so a typo'd `artifact-name`, wrong `run-id`, or wrong
`repository` fails loudly in the Actions log instead of producing a dead
Playground link that only fails when someone clicks it. This needs
`actions: read` permission on the job/workflow (broader than `post-comment`'s
`pull-requests: write`, and works independently of it).

If you don't pass `github-token`, verification is skipped (with a `::notice::`
in the log) and the link is built unconditionally — the action still works,
you just lose the early failure.

## Trigger modes

These are three complete, standalone caller workflows (they live in the repo
that *uses* this action, not in this repo) covering the three ways you'd
typically want to mint a link. All three assume you already have a workflow
step that builds your plugin zip and uploads it via `actions/upload-artifact`
— only the trigger and how the run/artifact are located differ.

### 1. Manual trigger (`workflow_dispatch`)

Use this when you want to mint a link on demand for a specific past build,
without wiring up anything automatic. Because the dispatch run is a *new*
run with no artifact of its own, `run-id` must be supplied explicitly —
find it from the Actions tab of the run that uploaded the artifact.

```yaml
name: Playground Link (manual)

on:
  workflow_dispatch:
    inputs:
      run_id:
        description: 'Workflow run ID that already uploaded the plugin zip artifact (find it in the Actions tab)'
        required: true
        type: string
      artifact_name:
        description: 'Name of the uploaded artifact'
        required: true
        type: string
        default: 'my-plugin'
      pr_number:
        description: 'PR number to comment on'
        required: true
        type: string

permissions:
  actions: read
  pull-requests: write

jobs:
  playground-link:
    runs-on: ubuntu-latest
    steps:
      - name: Generate Playground link and comment
        id: playground
        uses: pattonwebz/wordpress-playground-action@v0
        with:
          artifact-name: ${{ inputs.artifact_name }}
          run-id: ${{ inputs.run_id }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
          post-comment: 'true'
          pr-number: ${{ inputs.pr_number }}

      - run: echo "${{ steps.playground.outputs.playground-url }}"
```

Trigger it with `gh workflow run "Playground Link (manual)" -f run_id=123456789 -f artifact_name=my-plugin -f pr_number=42`, or via the "Run workflow" button in the Actions tab.

### 2. Automatic on every PR

Use this when you always want a fresh link on every push to a PR. Because
the artifact is uploaded earlier in the *same* run, `run-id`/`repository`
don't need to be set — they default to the current run/repo.

```yaml
name: Playground Link (automatic)

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  build-and-link:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Build plugin zip
        run: ./bin/build-zip.sh   # however you produce your plugin zip

      - uses: actions/upload-artifact@v7
        with:
          name: my-plugin
          path: my-plugin.zip

      - name: Generate Playground link and comment
        uses: pattonwebz/wordpress-playground-action@v0
        with:
          artifact-name: my-plugin
          post-comment: 'true'
          pr-number: ${{ github.event.pull_request.number }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

**Fork PRs:** GitHub gives workflows triggered by `pull_request` a
**read-only** `GITHUB_TOKEN` when the PR comes from a fork, regardless of
the `permissions:` block above — so `post-comment` will fail on fork PRs
under this trigger specifically. This is a GitHub platform restriction, not
something this action can work around. If you need it to work for fork PRs
too, that requires `pull_request_target` and the usual care that trigger
demands (it runs with base-branch permissions against untrusted head code),
which is outside the scope of this README.

### 3. Label-triggered (mint on demand, one-shot label)

Use this when builds happen automatically but you don't want a link/comment
on *every* push — a reviewer adds a `playground` label when they actually
want to try it. This looks up the most recent successful build for the PR's
head commit instead of taking `run-id` as an input, and removes the label
again afterwards so re-adding it triggers a fresh mint.

```yaml
name: Playground Link (on-demand via label)

on:
  pull_request:
    types: [labeled]

permissions:
  actions: read
  pull-requests: write

jobs:
  playground-link:
    if: github.event.label.name == 'playground'
    runs-on: ubuntu-latest
    steps:
      - name: Find the latest successful build for this PR's head commit
        id: find-run
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          set -euo pipefail
          RUN_ID=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs?head_sha=${HEAD_SHA}&status=success&per_page=100" \
            --jq '[.workflow_runs[] | select(.name | test("Build"))] | sort_by(.created_at) | last | .id // empty')
          if [ -z "$RUN_ID" ]; then
            echo "::error::No successful build run found for ${HEAD_SHA}. Run the build workflow first, then re-add the playground label."
            exit 1
          fi
          echo "run-id=${RUN_ID}" >> "$GITHUB_OUTPUT"

      - name: Generate Playground link and comment
        uses: pattonwebz/wordpress-playground-action@v0
        with:
          artifact-name: my-plugin
          run-id: ${{ steps.find-run.outputs.run-id }}
          post-comment: 'true'
          pr-number: ${{ github.event.pull_request.number }}
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Remove the trigger label
        if: always()
        uses: actions/github-script@v9
        with:
          script: |
            try {
              await github.rest.issues.removeLabel({
                ...context.repo,
                issue_number: context.payload.pull_request.number,
                name: 'playground',
              });
            } catch (e) {
              core.info(`Could not remove 'playground' label: ${e.message}`);
            }
```

Adjust the `test("Build")` name pattern to match whatever your actual build
workflow is called — it's matching on the *workflow run's display name*, not
this workflow's own name. The same fork-PR `GITHUB_TOKEN` read-only caveat
from mode 2 applies here too, for the same reason.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `artifact-name` | yes | – | Name of the `actions/upload-artifact` artifact holding the plugin zip. |
| `run-id` | no | current run | Run whose artifact to link to. |
| `repository` | no | current repo | `owner/repo` the artifact belongs to. |
| `plugin-slug` | no | `''` | Override for the inferred `{slug}/{slug}.php` activation path. |
| `activate-on-load` | no | `true` | Auto-activate the plugin after install. |
| `landing-page` | no | `/wp-admin/plugins.php` | Admin path Playground lands on. |
| `wp-version` | no | `latest` | Preferred WordPress core version. |
| `php-version` | no | `latest` | Preferred PHP version. |
| `multisite` | no | `false` | Set up the site as a multisite network. |
| `extra-plugins` | no | `[]` | JSON array of additional plugin zip URLs to install. |
| `extra-plugins-activate` | no | `true` | Activate each of `extra-plugins` after install. |
| `extra-theme-url` | no | `''` | Optional theme zip URL to install. |
| `extra-theme-activate` | no | `true` | Activate the extra theme after install. |
| `post-comment` | no | `false` | Post/update a sticky PR comment with the link. |
| `pr-number` | no | `''` | PR to comment on. Required if `post-comment` is `true`. |
| `github-token` | no | `''` | Verifies the artifact exists (skipped if empty) and/or posts the PR comment. Required if `post-comment` is `true`. |
| `comment-marker` | no | `<!-- PLAYGROUND-LINK -->` | Marker used to find/update the sticky comment. |
| `comment-build-details` | no | `false` | Also link the artifact download and the workflow run in the comment. The artifact link needs `github-token` and is omitted without it. |
| `expiry-note` | no | `''` | Freeform text appended to the PR comment. |

## Outputs

| Output | Description |
|---|---|
| `playground-url` | The generated `https://playground.wordpress.net/?blueprint-url=...` link. |
| `zip-url` | The derived `nightly.link` URL for the artifact. |
| `plugin-path` | The `{slug}/{slug}.php` path used for activation. |
| `comment-url` | URL of the created/updated PR comment, if `post-comment` was `true`. |
| `artifact-id` | Numeric ID of the verified artifact. Empty without `github-token`. |
| `artifact-download-url` | Browser URL for downloading the verified artifact. Empty without `github-token`. |

## Plugin slug inference

The plugin's activation path (`{slug}/{slug}.php`) is inferred from
`artifact-name` by stripping a trailing version/build-number/commit-hash
suffix (e.g. `my-plugin-2.2.0-826-7a385380` → `my-plugin`). If your artifact
naming doesn't fit that pattern, set `plugin-slug` explicitly. The inferred
slug is always echoed as a workflow warning so you can spot a bad guess in
the logs.

## Development

```sh
python3 -m unittest discover -s tests -v
```

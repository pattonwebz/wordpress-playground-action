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
      - uses: actions/checkout@v4

      - name: Build plugin zip
        run: ./bin/build-zip.sh   # however you produce your plugin zip

      - uses: actions/upload-artifact@v4
        with:
          name: my-plugin
          path: my-plugin.zip

      - name: Generate Playground link
        id: playground
        uses: equalizedigital/wordpress-playground-action@v1
        with:
          artifact-name: my-plugin
          github-token: ${{ secrets.GITHUB_TOKEN }}   # optional, see "Artifact verification" below

      - run: echo "${{ steps.playground.outputs.playground-url }}"
```

### Posting a PR comment

```yaml
      - uses: equalizedigital/wordpress-playground-action@v1
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
| `php-version` | no | `8.2` | Preferred PHP version. |
| `multisite` | no | `false` | Set up the site as a multisite network. |
| `extra-plugins` | no | `[]` | JSON array of additional plugin zip URLs to install. |
| `extra-plugins-activate` | no | `true` | Activate each of `extra-plugins` after install. |
| `extra-theme-url` | no | `''` | Optional theme zip URL to install. |
| `extra-theme-activate` | no | `true` | Activate the extra theme after install. |
| `post-comment` | no | `false` | Post/update a sticky PR comment with the link. |
| `pr-number` | no | `''` | PR to comment on. Required if `post-comment` is `true`. |
| `github-token` | no | `''` | Verifies the artifact exists (skipped if empty) and/or posts the PR comment. Required if `post-comment` is `true`. |
| `comment-marker` | no | `<!-- PLAYGROUND-LINK -->` | Marker used to find/update the sticky comment. |
| `expiry-note` | no | `''` | Freeform text appended to the PR comment. |

## Outputs

| Output | Description |
|---|---|
| `playground-url` | The generated `https://playground.wordpress.net/?blueprint-url=...` link. |
| `zip-url` | The derived `nightly.link` URL for the artifact. |
| `plugin-path` | The `{slug}/{slug}.php` path used for activation. |
| `comment-url` | URL of the created/updated PR comment, if `post-comment` was `true`. |

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

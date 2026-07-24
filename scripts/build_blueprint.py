#!/usr/bin/env python3
"""Build a WordPress Playground link from a nightly.link-hosted plugin artifact.

Reads configuration from environment variables (set by action.yml) and writes
`playground-url`, `zip-url`, and `plugin-path` to $GITHUB_OUTPUT.
"""
import base64
import json
import os
import re
import sys
import urllib.parse

SUFFIX_RE = re.compile(r"-\d+(\.\d+)*(-\d+)?(-[0-9a-f]{6,40})?$")


def infer_slug(artifact_name: str) -> str:
    """Derive a plugin slug from an upload-artifact name.

    Strips a trailing version/build-number/commit-hash suffix, e.g.
    "accessibility-checker-pro-2.2.0-826-7a385380" -> "accessibility-checker-pro".
    A bare name with no such suffix passes through unchanged.
    """
    return SUFFIX_RE.sub("", artifact_name)


def build_zip_url(repository: str, run_id: str, artifact_name: str) -> str:
    # upload-artifact names may contain spaces or other characters that need
    # encoding to form a valid URL path segment (repository/run_id are not
    # user-facing free text, so only artifact_name needs it).
    return (
        f"https://nightly.link/{repository}/actions/runs/{run_id}/"
        f"{urllib.parse.quote(artifact_name, safe='')}.zip"
    )


def str_to_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def build_blueprint(*, zip_url, activate_on_load, landing_page,
                     wp_version, php_version, multisite,
                     extra_plugins, extra_plugins_activate,
                     extra_theme_url, extra_theme_activate):
    steps = [{"step": "login"}]

    if multisite:
        steps.append({"step": "enableMultisite"})

    steps.append({
        "step": "installPlugin",
        "pluginZipFile": {"resource": "url", "url": zip_url},
        "options": {"activate": activate_on_load},
    })

    for url in extra_plugins:
        steps.append({
            "step": "installPlugin",
            "pluginZipFile": {"resource": "url", "url": url},
            "options": {"activate": extra_plugins_activate},
        })

    if extra_theme_url:
        steps.append({
            "step": "installTheme",
            "themeZipFile": {"resource": "url", "url": extra_theme_url},
            "options": {"activate": extra_theme_activate},
        })

    return {
        "landingPage": landing_page,
        "preferredVersions": {"php": php_version, "wp": wp_version},
        "steps": steps,
    }


def build_playground_url(blueprint: dict) -> str:
    data_uri = "data:application/json;base64," + base64.b64encode(
        json.dumps(blueprint, separators=(",", ":")).encode()
    ).decode()
    return "https://playground.wordpress.net/?blueprint-url=" + urllib.parse.quote(data_uri, safe="")


def main():
    repository = os.environ["REPOSITORY"]
    run_id = os.environ["RUN_ID"]
    artifact_name = os.environ["ARTIFACT_NAME"]
    plugin_slug_override = os.environ.get("PLUGIN_SLUG", "").strip()
    activate_on_load = str_to_bool(os.environ.get("ACTIVATE_ON_LOAD", "true"))
    landing_page = os.environ.get("LANDING_PAGE", "/wp-admin/plugins.php")
    wp_version = os.environ.get("WP_VERSION", "latest")
    php_version = os.environ.get("PHP_VERSION", "8.2")
    multisite = str_to_bool(os.environ.get("MULTISITE", "false"))
    extra_plugins_activate = str_to_bool(os.environ.get("EXTRA_PLUGINS_ACTIVATE", "true"))
    extra_theme_url = os.environ.get("EXTRA_THEME_URL", "").strip()
    extra_theme_activate = str_to_bool(os.environ.get("EXTRA_THEME_ACTIVATE", "true"))

    extra_plugins_raw = os.environ.get("EXTRA_PLUGINS", "[]").strip() or "[]"
    try:
        extra_plugins = json.loads(extra_plugins_raw)
        if not isinstance(extra_plugins, list) or not all(isinstance(u, str) for u in extra_plugins):
            raise ValueError("extra-plugins must be a JSON array of strings")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"::error::Invalid extra-plugins input (must be a JSON array of URL strings): {exc}")
        sys.exit(1)

    slug = plugin_slug_override or infer_slug(artifact_name)
    if not plugin_slug_override:
        print(f"::warning::Inferred plugin slug '{slug}' from artifact name '{artifact_name}'. "
              f"If this is wrong, set the plugin-slug input to override it.")
    plugin_path = f"{slug}/{slug}.php"

    zip_url = build_zip_url(repository, run_id, artifact_name)

    blueprint = build_blueprint(
        zip_url=zip_url,
        activate_on_load=activate_on_load,
        landing_page=landing_page,
        wp_version=wp_version,
        php_version=php_version,
        multisite=multisite,
        extra_plugins=extra_plugins,
        extra_plugins_activate=extra_plugins_activate,
        extra_theme_url=extra_theme_url,
        extra_theme_activate=extra_theme_activate,
    )

    playground_url = build_playground_url(blueprint)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"playground-url={playground_url}\n")
            fh.write(f"zip-url={zip_url}\n")
            fh.write(f"plugin-path={plugin_path}\n")
    else:
        print(json.dumps({
            "playground-url": playground_url,
            "zip-url": zip_url,
            "plugin-path": plugin_path,
        }, indent=2))


if __name__ == "__main__":
    main()

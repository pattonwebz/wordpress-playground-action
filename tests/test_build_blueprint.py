import base64
import json
import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_blueprint as bb  # noqa: E402


class TestInferSlug(unittest.TestCase):
    def test_bare_name_passthrough(self):
        self.assertEqual(bb.infer_slug("accessibility-checker-pro"), "accessibility-checker-pro")

    def test_strips_version_build_hash_suffix(self):
        self.assertEqual(
            bb.infer_slug("accessibility-checker-pro-2.2.0-826-7a385380"),
            "accessibility-checker-pro",
        )

    def test_strips_simple_version_suffix(self):
        self.assertEqual(bb.infer_slug("my-plugin-1.4"), "my-plugin")


class TestBuildZipUrl(unittest.TestCase):
    def test_shape(self):
        url = bb.build_zip_url("owner/repo", "12345", "my-plugin")
        self.assertEqual(url, "https://nightly.link/owner/repo/actions/runs/12345/my-plugin.zip")

    def test_encodes_special_characters_in_artifact_name(self):
        url = bb.build_zip_url("owner/repo", "12345", "my plugin build #1")
        self.assertEqual(
            url,
            "https://nightly.link/owner/repo/actions/runs/12345/my%20plugin%20build%20%231.zip",
        )


class TestNormalizeLandingPage(unittest.TestCase):
    def test_passthrough_when_absolute(self):
        self.assertEqual(bb.normalize_landing_page("/wp-admin/plugins.php"), "/wp-admin/plugins.php")

    def test_prepends_missing_leading_slash(self):
        self.assertEqual(bb.normalize_landing_page("wp-admin/plugins.php"), "/wp-admin/plugins.php")

    def test_empty_stays_empty(self):
        self.assertEqual(bb.normalize_landing_page(""), "")


class TestBuildBlueprint(unittest.TestCase):
    def base_kwargs(self, **overrides):
        kwargs = dict(
            zip_url="https://nightly.link/owner/repo/actions/runs/1/plugin.zip",
            activate_on_load=True,
            landing_page="/wp-admin/plugins.php",
            wp_version="latest",
            php_version="8.2",
            multisite=False,
            extra_plugins=[],
            extra_plugins_activate=True,
            extra_theme_url="",
            extra_theme_activate=True,
        )
        kwargs.update(overrides)
        return kwargs

    def test_basic_shape(self):
        blueprint = bb.build_blueprint(**self.base_kwargs())
        self.assertEqual(blueprint["landingPage"], "/wp-admin/plugins.php")
        self.assertEqual(blueprint["preferredVersions"], {"php": "8.2", "wp": "latest"})
        self.assertEqual(blueprint["steps"][0], {"step": "login"})
        install_step = blueprint["steps"][1]
        self.assertEqual(install_step["step"], "installPlugin")
        self.assertEqual(install_step["pluginZipFile"]["url"], self.base_kwargs()["zip_url"])
        self.assertTrue(install_step["options"]["activate"])
        self.assertEqual(len(blueprint["steps"]), 2)

    def test_activate_on_load_false(self):
        blueprint = bb.build_blueprint(**self.base_kwargs(activate_on_load=False))
        install_step = blueprint["steps"][1]
        self.assertFalse(install_step["options"]["activate"])

    def test_multisite_injects_step_after_login(self):
        blueprint = bb.build_blueprint(**self.base_kwargs(multisite=True))
        self.assertEqual(blueprint["steps"][0], {"step": "login"})
        self.assertEqual(blueprint["steps"][1], {"step": "enableMultisite"})
        self.assertEqual(blueprint["steps"][2]["step"], "installPlugin")

    def test_extra_plugins(self):
        blueprint = bb.build_blueprint(**self.base_kwargs(
            extra_plugins=["https://example.com/a.zip", "https://example.com/b.zip"],
            extra_plugins_activate=False,
        ))
        extra_steps = [s for s in blueprint["steps"] if s["step"] == "installPlugin"]
        self.assertEqual(len(extra_steps), 3)  # main + 2 extras
        for step in extra_steps[1:]:
            self.assertFalse(step["options"]["activate"])

    def test_extra_theme(self):
        blueprint = bb.build_blueprint(**self.base_kwargs(
            extra_theme_url="https://example.com/theme.zip",
            extra_theme_activate=True,
        ))
        theme_steps = [s for s in blueprint["steps"] if s["step"] == "installTheme"]
        self.assertEqual(len(theme_steps), 1)
        self.assertEqual(theme_steps[0]["themeZipFile"]["url"], "https://example.com/theme.zip")
        self.assertTrue(theme_steps[0]["options"]["activate"])

    def test_no_extra_theme_step_when_url_empty(self):
        blueprint = bb.build_blueprint(**self.base_kwargs(extra_theme_url=""))
        theme_steps = [s for s in blueprint["steps"] if s["step"] == "installTheme"]
        self.assertEqual(len(theme_steps), 0)


class TestBuildPlaygroundUrl(unittest.TestCase):
    def test_round_trip(self):
        blueprint = {"landingPage": "/wp-admin/plugins.php", "steps": [{"step": "login"}]}
        url = bb.build_playground_url(blueprint)
        self.assertTrue(url.startswith("https://playground.wordpress.net/?blueprint-url="))

        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        data_uri = query["blueprint-url"][0]
        self.assertTrue(data_uri.startswith("data:application/json;base64,"))

        encoded = data_uri.split(",", 1)[1]
        decoded = json.loads(base64.b64decode(encoded))
        self.assertEqual(decoded, blueprint)


class TestStrToBool(unittest.TestCase):
    def test_true_values(self):
        for v in ["true", "True", "1", "yes", "on"]:
            self.assertTrue(bb.str_to_bool("some-input", v))

    def test_false_values(self):
        for v in ["false", "False", "0", "no", "off"]:
            self.assertFalse(bb.str_to_bool("some-input", v))

    def test_invalid_value_exits_with_error(self):
        with self.assertRaises(SystemExit):
            bb.str_to_bool("some-input", "definitely not a boolean")


if __name__ == "__main__":
    unittest.main()

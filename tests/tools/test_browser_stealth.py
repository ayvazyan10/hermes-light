"""Tests for browser_stealth module — fingerprint generation and stealth scripts."""

import pytest
from tools.browser_stealth import (
    generate_fingerprint,
    build_stealth_scripts,
    get_stealth_init_script,
    get_context_options,
    BrowserFingerprint,
)


class TestFingerprintGeneration:
    def test_generates_fingerprint(self):
        fp = generate_fingerprint()
        assert isinstance(fp, BrowserFingerprint)
        assert fp.user_agent
        assert fp.platform in ("Win32", "MacIntel", "Linux x86_64")
        assert fp.hardware_concurrency > 0
        assert fp.screen_width > 0
        assert fp.screen_height > 0

    def test_seed_produces_consistent_fingerprint(self):
        fp1 = generate_fingerprint(seed="test_session_123")
        fp2 = generate_fingerprint(seed="test_session_123")
        assert fp1 == fp2

    def test_different_seeds_produce_different_fingerprints(self):
        fp1 = generate_fingerprint(seed="session_a")
        fp2 = generate_fingerprint(seed="session_b")
        assert fp1 != fp2

    def test_fingerprint_immutable(self):
        fp = generate_fingerprint(seed="frozen")
        with pytest.raises(Exception):
            fp.user_agent = "modified"  # type: ignore

    def test_languages_is_tuple(self):
        fp = generate_fingerprint()
        assert isinstance(fp.languages, tuple)
        assert len(fp.languages) >= 1


class TestStealthScripts:
    def test_builds_scripts_list(self):
        fp = generate_fingerprint(seed="test")
        scripts = build_stealth_scripts(fp)
        assert isinstance(scripts, list)
        assert len(scripts) >= 10

    def test_scripts_contain_webdriver_patch(self):
        fp = generate_fingerprint(seed="test")
        scripts = build_stealth_scripts(fp)
        combined = "\n".join(scripts)
        assert "webdriver" in combined
        assert "undefined" in combined

    def test_scripts_contain_webgl_spoofing(self):
        fp = generate_fingerprint(seed="test")
        scripts = build_stealth_scripts(fp)
        combined = "\n".join(scripts)
        assert "37445" in combined
        assert "37446" in combined
        assert fp.webgl_vendor in combined

    def test_scripts_contain_canvas_noise(self):
        fp = generate_fingerprint(seed="test")
        scripts = build_stealth_scripts(fp)
        combined = "\n".join(scripts)
        assert "toDataURL" in combined
        assert "toBlob" in combined
        assert str(fp.canvas_noise_seed) in combined

    def test_scripts_contain_rtc_block(self):
        fp = generate_fingerprint(seed="test")
        scripts = build_stealth_scripts(fp)
        combined = "\n".join(scripts)
        assert "RTCPeerConnection" in combined

    def test_scripts_contain_chrome_runtime(self):
        fp = generate_fingerprint(seed="test")
        scripts = build_stealth_scripts(fp)
        combined = "\n".join(scripts)
        assert "window.chrome" in combined or "chrome" in combined

    def test_init_script_combines_all(self):
        fp = generate_fingerprint(seed="test")
        init_script = get_stealth_init_script(fp)
        assert isinstance(init_script, str)
        assert len(init_script) > 1000
        assert "webdriver" in init_script
        assert "37445" in init_script


class TestContextOptions:
    def test_returns_dict_with_required_keys(self):
        fp = generate_fingerprint(seed="test")
        opts = get_context_options(fp)
        assert "user_agent" in opts
        assert "viewport" in opts
        assert "timezone_id" in opts
        assert "locale" in opts

    def test_viewport_dimensions_reasonable(self):
        fp = generate_fingerprint(seed="test")
        opts = get_context_options(fp)
        vp = opts["viewport"]
        assert 800 <= vp["width"] <= 3840
        assert 500 <= vp["height"] <= 2160

    def test_user_agent_matches_fingerprint(self):
        fp = generate_fingerprint(seed="test")
        opts = get_context_options(fp)
        assert opts["user_agent"] == fp.user_agent

    def test_timezone_matches_fingerprint(self):
        fp = generate_fingerprint(seed="test")
        opts = get_context_options(fp)
        assert opts["timezone_id"] == fp.timezone

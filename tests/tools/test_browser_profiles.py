"""Tests for browser_profiles module — persistent session management."""

import json
import pytest
import tempfile
from pathlib import Path
from tools.browser_profiles import ProfileManager, BrowserProfile


@pytest.fixture
def profile_manager(tmp_path):
    return ProfileManager(base_dir=str(tmp_path))


class TestProfileCreation:
    def test_create_profile(self, profile_manager):
        profile = profile_manager.create_profile(name="test_profile")
        assert profile.profile_id
        assert profile.name == "test_profile"
        assert profile.created_at > 0
        assert profile.visit_count == 0

    def test_create_profile_generates_id(self, profile_manager):
        p1 = profile_manager.create_profile(name="a")
        p2 = profile_manager.create_profile(name="b")
        assert p1.profile_id != p2.profile_id

    def test_create_profile_default_name(self, profile_manager):
        profile = profile_manager.create_profile()
        assert profile.name.startswith("profile_")

    def test_create_profile_with_tags(self, profile_manager):
        profile = profile_manager.create_profile(name="tagged", tags=["work", "dev"])
        assert profile.tags == ["work", "dev"]

    def test_create_profile_with_seed(self, profile_manager):
        profile = profile_manager.create_profile(fingerprint_seed="my_seed")
        assert profile.fingerprint_seed == "my_seed"


class TestProfileRetrieval:
    def test_get_existing_profile(self, profile_manager):
        created = profile_manager.create_profile(name="findme")
        found = profile_manager.get_profile(created.profile_id)
        assert found is not None
        assert found.name == "findme"
        assert found.profile_id == created.profile_id

    def test_get_nonexistent_profile(self, profile_manager):
        found = profile_manager.get_profile("nonexistent_id")
        assert found is None

    def test_list_profiles_empty(self, profile_manager):
        profiles = profile_manager.list_profiles()
        assert profiles == []

    def test_list_profiles_returns_all(self, profile_manager):
        profile_manager.create_profile(name="one")
        profile_manager.create_profile(name="two")
        profile_manager.create_profile(name="three")
        profiles = profile_manager.list_profiles()
        assert len(profiles) == 3

    def test_list_profiles_sorted_by_last_used(self, profile_manager):
        import time
        p1 = profile_manager.create_profile(name="old")
        time.sleep(0.01)
        p2 = profile_manager.create_profile(name="new")
        profiles = profile_manager.list_profiles()
        assert profiles[0].name == "new"


class TestProfileUpdate:
    def test_update_usage(self, profile_manager):
        profile = profile_manager.create_profile(name="usage_test")
        original_time = profile.last_used_at
        import time
        time.sleep(0.01)
        profile_manager.update_profile_usage(profile.profile_id)
        updated = profile_manager.get_profile(profile.profile_id)
        assert updated.visit_count == 1
        assert updated.last_used_at > original_time

    def test_mark_warmup_complete(self, profile_manager):
        profile = profile_manager.create_profile(name="warmup_test")
        assert not profile.warmup_complete
        profile_manager.mark_warmup_complete(profile.profile_id)
        updated = profile_manager.get_profile(profile.profile_id)
        assert updated.warmup_complete


class TestProfileDeletion:
    def test_delete_profile(self, profile_manager):
        profile = profile_manager.create_profile(name="deleteme")
        assert profile_manager.delete_profile(profile.profile_id)
        assert profile_manager.get_profile(profile.profile_id) is None

    def test_delete_nonexistent_profile(self, profile_manager):
        assert not profile_manager.delete_profile("nonexistent")

    def test_cleanup_old_profiles(self, profile_manager):
        import time
        profile = profile_manager.create_profile(name="old")
        # Artificially age the profile
        meta_path = profile_manager.get_profile_dir(profile.profile_id) / "profile_meta.json"
        data = json.loads(meta_path.read_text())
        data["last_used_at"] = time.time() - (31 * 86400)
        meta_path.write_text(json.dumps(data))

        removed = profile_manager.cleanup_old_profiles(max_age_days=30)
        assert removed == 1


class TestStorageState:
    def test_save_and_load_storage_state(self, profile_manager):
        profile = profile_manager.create_profile(name="state_test")
        state = {
            "cookies": [{"name": "session", "value": "abc123", "domain": ".example.com"}],
            "origins": [{"origin": "https://example.com", "localStorage": [{"name": "key", "value": "val"}]}],
        }
        profile_manager.save_storage_state(profile.profile_id, state)
        loaded = profile_manager.load_storage_state(profile.profile_id)
        assert loaded == state

    def test_load_nonexistent_storage_state(self, profile_manager):
        profile = profile_manager.create_profile(name="no_state")
        loaded = profile_manager.load_storage_state(profile.profile_id)
        assert loaded is None


class TestProfileClone:
    def test_clone_profile(self, profile_manager):
        original = profile_manager.create_profile(name="original")
        state = {"cookies": [{"name": "test", "value": "data"}]}
        profile_manager.save_storage_state(original.profile_id, state)

        clone = profile_manager.clone_profile(original.profile_id, "cloned")
        assert clone is not None
        assert clone.profile_id != original.profile_id
        assert clone.name == "cloned"

        clone_state = profile_manager.load_storage_state(clone.profile_id)
        assert clone_state == state

    def test_clone_nonexistent_profile(self, profile_manager):
        result = profile_manager.clone_profile("nonexistent")
        assert result is None

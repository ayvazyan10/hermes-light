"""
Browser Profiles Module — Persistent Session & Identity Management

Manages browser profiles for maintaining consistent identity across sessions:
- Cookie and localStorage persistence
- Login state preservation across restarts
- Profile rotation for multi-account scenarios
- Session warmup with browsing history
- Fingerprint consistency per profile
"""

import json
import hashlib
import logging
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BrowserProfile:
    """Persistent browser profile with identity and state."""
    profile_id: str
    name: str = ""
    fingerprint_seed: str = ""
    created_at: float = 0.0
    last_used_at: float = 0.0
    visit_count: int = 0
    warmup_complete: bool = False
    tags: list[str] = field(default_factory=list)
    notes: str = ""


class ProfileManager:
    """Manages persistent browser profiles on disk."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self._base_dir = Path(base_dir).expanduser()
        else:
            from hermes_constants import get_hermes_home
            self._base_dir = get_hermes_home() / "browser_profiles"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def list_profiles(self) -> list[BrowserProfile]:
        """List all saved profiles."""
        profiles = []
        for meta_file in self._base_dir.glob("*/profile_meta.json"):
            try:
                data = json.loads(meta_file.read_text())
                profiles.append(BrowserProfile(**data))
            except Exception as e:
                logger.debug("Failed to load profile from %s: %s", meta_file, e)
        profiles.sort(key=lambda p: p.last_used_at, reverse=True)
        return profiles

    def get_profile(self, profile_id: str) -> Optional[BrowserProfile]:
        """Get a specific profile by ID."""
        meta_path = self._profile_dir(profile_id) / "profile_meta.json"
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text())
            return BrowserProfile(**data)
        except Exception:
            return None

    def create_profile(self, name: str = "", tags: Optional[list[str]] = None,
                       fingerprint_seed: Optional[str] = None) -> BrowserProfile:
        """Create a new browser profile."""
        profile_id = hashlib.sha256(
            f"{name}_{time.time()}_{id(self)}".encode()
        ).hexdigest()[:16]

        profile = BrowserProfile(
            profile_id=profile_id,
            name=name or f"profile_{profile_id[:8]}",
            fingerprint_seed=fingerprint_seed or profile_id,
            created_at=time.time(),
            last_used_at=time.time(),
            tags=tags or [],
        )

        profile_dir = self._profile_dir(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._save_meta(profile)

        logger.info("Created browser profile: %s (%s)", profile.name, profile_id)
        return profile

    def update_profile_usage(self, profile_id: str) -> None:
        """Update last_used_at and visit_count for a profile."""
        profile = self.get_profile(profile_id)
        if not profile:
            return

        updated = BrowserProfile(
            profile_id=profile.profile_id,
            name=profile.name,
            fingerprint_seed=profile.fingerprint_seed,
            created_at=profile.created_at,
            last_used_at=time.time(),
            visit_count=profile.visit_count + 1,
            warmup_complete=profile.warmup_complete,
            tags=profile.tags,
            notes=profile.notes,
        )
        self._save_meta(updated)

    def mark_warmup_complete(self, profile_id: str) -> None:
        """Mark profile warmup as complete."""
        profile = self.get_profile(profile_id)
        if not profile:
            return

        updated = BrowserProfile(
            profile_id=profile.profile_id,
            name=profile.name,
            fingerprint_seed=profile.fingerprint_seed,
            created_at=profile.created_at,
            last_used_at=profile.last_used_at,
            visit_count=profile.visit_count,
            warmup_complete=True,
            tags=profile.tags,
            notes=profile.notes,
        )
        self._save_meta(updated)

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile and all its data."""
        profile_dir = self._profile_dir(profile_id)
        if not profile_dir.exists():
            return False
        try:
            shutil.rmtree(profile_dir)
            logger.info("Deleted browser profile: %s", profile_id)
            return True
        except Exception as e:
            logger.warning("Failed to delete profile %s: %s", profile_id, e)
            return False

    def get_storage_state_path(self, profile_id: str) -> Path:
        """Get path to storage state file for a profile."""
        return self._profile_dir(profile_id) / "storage_state.json"

    def load_storage_state(self, profile_id: str) -> Optional[dict]:
        """Load storage state (cookies, localStorage) for a profile."""
        state_path = self.get_storage_state_path(profile_id)
        if not state_path.exists():
            return None
        try:
            return json.loads(state_path.read_text())
        except Exception as e:
            logger.debug("Failed to load storage state for %s: %s", profile_id, e)
            return None

    def save_storage_state(self, profile_id: str, state: dict) -> None:
        """Save storage state for a profile."""
        state_path = self.get_storage_state_path(profile_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    def get_profile_dir(self, profile_id: str) -> Path:
        """Get the directory for a profile (for Playwright persistent context)."""
        profile_dir = self._profile_dir(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    def clone_profile(self, source_id: str, new_name: str = "") -> Optional[BrowserProfile]:
        """Clone an existing profile (for multi-account scenarios)."""
        source_dir = self._profile_dir(source_id)
        if not source_dir.exists():
            return None

        new_profile = self.create_profile(
            name=new_name or f"clone_of_{source_id[:8]}",
            fingerprint_seed=f"clone_{source_id}_{time.time()}",
        )

        new_dir = self._profile_dir(new_profile.profile_id)
        # Copy storage state
        source_state = source_dir / "storage_state.json"
        if source_state.exists():
            shutil.copy2(source_state, new_dir / "storage_state.json")

        return new_profile

    def cleanup_old_profiles(self, max_age_days: int = 30) -> int:
        """Remove profiles not used within max_age_days."""
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0

        for profile in self.list_profiles():
            if profile.last_used_at < cutoff:
                if self.delete_profile(profile.profile_id):
                    removed += 1

        if removed:
            logger.info("Cleaned up %d old browser profiles", removed)
        return removed

    def _profile_dir(self, profile_id: str) -> Path:
        return self._base_dir / profile_id

    def _save_meta(self, profile: BrowserProfile) -> None:
        meta_path = self._profile_dir(profile.profile_id) / "profile_meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(asdict(profile), indent=2))

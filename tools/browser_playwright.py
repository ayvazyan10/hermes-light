"""
Browser Playwright Engine — Direct Playwright Integration with Full Stealth

Replaces agent-browser CLI with native Python Playwright for maximum control:
- Full stealth patches (fingerprint, navigator, WebGL, canvas)
- Human-like mouse/keyboard/scroll behavior
- Persistent browser profiles with cookie/localStorage inheritance
- Warm-up browsing sequences for session credibility
- Accessibility tree extraction for LLM consumption
- Screenshot and vision support
- CDP session access for advanced operations

Configuration (config.yaml):
    browser:
      engine: "playwright"  # Activate this engine
      playwright:
        headless: true
        profile_dir: "~/.hermes/browser_profiles"
        stealth_level: "maximum"  # minimum | standard | maximum
        humanize: true
        humanize_profile: "default"  # default | fast | careful
        warmup_enabled: true
        warmup_urls: ["https://google.com", "https://wikipedia.org"]
        proxy: null  # "socks5://user:pass@host:port"
        block_resources: ["font", "media"]  # resource types to block for speed
        persist_sessions: true

Environment Variables:
    PLAYWRIGHT_STEALTH_LEVEL: override stealth level
    PLAYWRIGHT_HEADLESS: "true" or "false"
    PLAYWRIGHT_PROXY: proxy URL
    BROWSER_PROFILE_SEED: seed for consistent fingerprint generation
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_playwright_instance = None
_browser_instance = None
_contexts: dict[str, Any] = {}
_pages: dict[str, Any] = {}
_profiles: dict[str, Path] = {}
_mouse_positions: dict[str, tuple[float, float]] = {}
_lock = threading.Lock()


@dataclass
class PlaywrightConfig:
    """Configuration for the Playwright engine."""
    headless: bool = True
    profile_dir: str = ""
    stealth_level: str = "maximum"
    humanize: bool = True
    humanize_profile: str = "default"
    warmup_enabled: bool = True
    warmup_urls: list[str] = field(default_factory=lambda: [
        "https://www.google.com",
        "https://en.wikipedia.org",
    ])
    proxy: Optional[str] = None
    block_resources: list[str] = field(default_factory=list)
    persist_sessions: bool = True
    browser_type: str = "chromium"
    channel: Optional[str] = None
    slow_mo: int = 0


def _load_config() -> PlaywrightConfig:
    """Load Playwright config from hermes config.yaml and environment."""
    config = PlaywrightConfig()

    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config()
        browser_cfg = cfg.get("browser", {})
        if isinstance(browser_cfg, dict):
            pw_cfg = browser_cfg.get("playwright", {})
            if isinstance(pw_cfg, dict):
                config.headless = pw_cfg.get("headless", True)
                config.profile_dir = pw_cfg.get("profile_dir", "")
                config.stealth_level = pw_cfg.get("stealth_level", "maximum")
                config.humanize = pw_cfg.get("humanize", True)
                config.humanize_profile = pw_cfg.get("humanize_profile", "default")
                config.warmup_enabled = pw_cfg.get("warmup_enabled", True)
                config.warmup_urls = pw_cfg.get("warmup_urls", config.warmup_urls)
                config.proxy = pw_cfg.get("proxy")
                config.block_resources = pw_cfg.get("block_resources", [])
                config.persist_sessions = pw_cfg.get("persist_sessions", True)
                config.browser_type = pw_cfg.get("browser_type", "chromium")
                config.channel = pw_cfg.get("channel")
                config.slow_mo = pw_cfg.get("slow_mo", 0)
    except Exception as e:
        logger.debug("Could not load playwright config: %s", e)

    # Environment overrides
    if os.getenv("PLAYWRIGHT_STEALTH_LEVEL"):
        config.stealth_level = os.getenv("PLAYWRIGHT_STEALTH_LEVEL")
    if os.getenv("PLAYWRIGHT_HEADLESS"):
        config.headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
    if os.getenv("PLAYWRIGHT_PROXY"):
        config.proxy = os.getenv("PLAYWRIGHT_PROXY")

    if not config.profile_dir:
        from hermes_constants import get_hermes_home
        config.profile_dir = str(get_hermes_home() / "browser_profiles")

    return config


def _get_profile_dir(task_id: str, config: PlaywrightConfig) -> Path:
    """Get or create profile directory for persistent sessions."""
    base_dir = Path(config.profile_dir).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)

    profile_hash = hashlib.sha256(task_id.encode()).hexdigest()[:12]
    profile_path = base_dir / f"profile_{profile_hash}"
    profile_path.mkdir(parents=True, exist_ok=True)

    return profile_path


def _get_humanize_profile():
    """Get the appropriate humanize profile based on config."""
    from tools.browser_humanize import DEFAULT_PROFILE, FAST_PROFILE, CAREFUL_PROFILE

    config = _load_config()
    profiles = {
        "default": DEFAULT_PROFILE,
        "fast": FAST_PROFILE,
        "careful": CAREFUL_PROFILE,
    }
    return profiles.get(config.humanize_profile, DEFAULT_PROFILE)


async def _ensure_playwright():
    """Ensure Playwright is initialized (singleton)."""
    global _playwright_instance, _browser_instance

    if _playwright_instance is not None and _browser_instance is not None:
        return _browser_instance

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is not installed. Install with: "
            "pip install playwright && playwright install chromium"
        )

    config = _load_config()

    _playwright_instance = await async_playwright().start()

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
        "--disable-web-security",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-service-autorun",
        "--password-store=basic",
        "--use-mock-keychain",
        "--force-color-profile=srgb",
    ]

    if os.geteuid() == 0:
        launch_args.append("--no-sandbox")

    launch_kwargs: dict[str, Any] = {
        "headless": config.headless,
        "args": launch_args,
        "slow_mo": config.slow_mo,
    }

    if config.channel:
        launch_kwargs["channel"] = config.channel

    if config.proxy:
        launch_kwargs["proxy"] = {"server": config.proxy}

    browser_launcher = getattr(_playwright_instance, config.browser_type, _playwright_instance.chromium)
    _browser_instance = await browser_launcher.launch(**launch_kwargs)

    logger.info(
        "Playwright browser launched: type=%s headless=%s stealth=%s humanize=%s",
        config.browser_type, config.headless, config.stealth_level, config.humanize,
    )

    return _browser_instance


async def _get_or_create_context(task_id: str) -> tuple[Any, Any]:
    """Get or create a browser context + page for the given task."""
    if task_id in _pages:
        return _contexts[task_id], _pages[task_id]

    browser = await _ensure_playwright()
    config = _load_config()

    # Generate fingerprint
    from tools.browser_stealth import generate_fingerprint, get_stealth_init_script, get_context_options

    seed = os.getenv("BROWSER_PROFILE_SEED", task_id)
    fingerprint = generate_fingerprint(seed)

    # Context options from fingerprint
    context_opts = get_context_options(fingerprint)

    # Persistent profile storage
    if config.persist_sessions:
        profile_dir = _get_profile_dir(task_id, config)
        _profiles[task_id] = profile_dir
        context_opts["storage_state"] = _load_storage_state(profile_dir)

    # Create context
    context = await browser.new_context(**context_opts)

    # Apply stealth patches
    if config.stealth_level != "none":
        stealth_script = get_stealth_init_script(fingerprint)
        await context.add_init_script(stealth_script)

    # Block unwanted resource types
    if config.block_resources:
        blocked = set(config.block_resources)
        await context.route("**/*", lambda route: (
            route.abort() if route.request.resource_type in blocked
            else route.continue_()
        ))

    # Create page
    page = await context.new_page()

    # Remove Playwright-specific markers from page
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        delete window.__playwright;
        delete window.__pw_manual;
    """)

    _contexts[task_id] = context
    _pages[task_id] = page
    _mouse_positions[task_id] = (0.0, 0.0)

    # Warmup browsing
    if config.warmup_enabled and config.warmup_urls:
        await _warmup_session(page, config, task_id)

    return context, page


def _load_storage_state(profile_dir: Path) -> Optional[dict]:
    """Load saved storage state (cookies, localStorage) from profile."""
    state_file = profile_dir / "storage_state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception as e:
            logger.debug("Failed to load storage state: %s", e)
    return None


async def _save_storage_state(task_id: str) -> None:
    """Save current storage state to profile directory."""
    if task_id not in _contexts or task_id not in _profiles:
        return
    try:
        context = _contexts[task_id]
        profile_dir = _profiles[task_id]
        state = await context.storage_state()
        state_file = profile_dir / "storage_state.json"
        state_file.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.debug("Failed to save storage state for %s: %s", task_id, e)


async def _warmup_session(page, config: PlaywrightConfig, task_id: str) -> None:
    """Perform warmup browsing to establish session credibility."""
    from tools.browser_humanize import human_scroll, human_wait, human_page_dwell

    profile = _get_humanize_profile()

    import random
    urls = list(config.warmup_urls)
    random.shuffle(urls)
    warmup_count = min(len(urls), 2)

    for url in urls[:warmup_count]:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await human_wait(800, 2000)

            # Simulate looking at the page
            if config.humanize:
                await human_page_dwell(page, profile)

        except Exception as e:
            logger.debug("Warmup navigation to %s failed (non-fatal): %s", url, e)
            continue


# ============================================================================
# Public API — Drop-in replacement functions for browser_tool.py
# ============================================================================


async def pw_navigate(url: str, task_id: str = "default") -> dict[str, Any]:
    """Navigate to URL with human-like behavior."""
    config = _load_config()
    _, page = await _get_or_create_context(task_id)

    if config.humanize:
        from tools.browser_humanize import random_pre_action_delay
        await random_pre_action_delay(_get_humanize_profile())

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        if config.humanize:
            from tools.browser_humanize import human_wait
            await human_wait(300, 1000)

        # Auto-save storage state
        if config.persist_sessions:
            await _save_storage_state(task_id)

        status = response.status if response else 0
        title = await page.title()

        # Bot detection check
        bot_warning = _check_bot_detection(title, await page.content())

        result: dict[str, Any] = {
            "success": True,
            "url": page.url,
            "title": title,
            "status": status,
        }
        if bot_warning:
            result["bot_detection_warning"] = bot_warning

        # Get accessibility snapshot
        snapshot = await _get_accessibility_snapshot(page)
        if snapshot:
            result["snapshot"] = snapshot

        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


async def pw_snapshot(task_id: str = "default", full: bool = False) -> dict[str, Any]:
    """Get accessibility tree snapshot of current page."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    page = _pages[task_id]

    try:
        snapshot = await _get_accessibility_snapshot(page, full=full)
        title = await page.title()

        return {
            "success": True,
            "url": page.url,
            "title": title,
            "snapshot": snapshot,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def pw_click(ref: str, task_id: str = "default") -> dict[str, Any]:
    """Click element with human-like mouse movement."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    config = _load_config()
    page = _pages[task_id]

    try:
        selector = _ref_to_selector(ref)
        element = page.locator(selector).first

        if not await element.is_visible():
            await element.scroll_into_view_if_needed()
            if config.humanize:
                from tools.browser_humanize import human_wait
                await human_wait(100, 300)

        box = await element.bounding_box()
        if not box:
            # Fallback to direct click
            await element.click()
            return {"success": True, "clicked": ref}

        # Target center with slight randomization
        target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

        if config.humanize:
            from tools.browser_humanize import human_click
            start_pos = _mouse_positions.get(task_id, (0.0, 0.0))
            await human_click(page, target_x, target_y, _get_humanize_profile(), start_pos=start_pos)
            _mouse_positions[task_id] = (target_x, target_y)
        else:
            await page.mouse.click(target_x, target_y)

        if config.persist_sessions:
            await _save_storage_state(task_id)

        return {"success": True, "clicked": ref}

    except Exception as e:
        return {"success": False, "error": f"Failed to click {ref}: {e}"}


async def pw_type(ref: str, text: str, task_id: str = "default") -> dict[str, Any]:
    """Type text into element with human-like typing patterns."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    config = _load_config()
    page = _pages[task_id]

    try:
        selector = _ref_to_selector(ref)
        element = page.locator(selector).first

        if not await element.is_visible():
            await element.scroll_into_view_if_needed()

        if config.humanize:
            from tools.browser_humanize import human_type, random_pre_action_delay
            await random_pre_action_delay(_get_humanize_profile())
            await human_type(page, element, text, _get_humanize_profile())
        else:
            await element.fill(text)

        if config.persist_sessions:
            await _save_storage_state(task_id)

        return {"success": True, "typed": text, "element": ref}

    except Exception as e:
        return {"success": False, "error": f"Failed to type into {ref}: {e}"}


async def pw_scroll(direction: str = "down", task_id: str = "default") -> dict[str, Any]:
    """Scroll page with human-like momentum."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    config = _load_config()
    page = _pages[task_id]

    try:
        if config.humanize:
            from tools.browser_humanize import human_scroll
            await human_scroll(page, direction, profile=_get_humanize_profile())
        else:
            delta = -500 if direction == "up" else 500
            await page.mouse.wheel(0, delta)

        return {"success": True, "direction": direction}

    except Exception as e:
        return {"success": False, "error": f"Scroll failed: {e}"}


async def pw_back(task_id: str = "default") -> dict[str, Any]:
    """Navigate back in history."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    page = _pages[task_id]

    try:
        from tools.browser_humanize import human_wait
        config = _load_config()
        if config.humanize:
            await human_wait(100, 300)

        await page.go_back(wait_until="domcontentloaded", timeout=15000)

        return {"success": True, "url": page.url, "title": await page.title()}

    except Exception as e:
        return {"success": False, "error": f"Back navigation failed: {e}"}


async def pw_press(key: str, task_id: str = "default") -> dict[str, Any]:
    """Press keyboard key with natural timing."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    config = _load_config()
    page = _pages[task_id]

    try:
        if config.humanize:
            from tools.browser_humanize import random_pre_action_delay
            await random_pre_action_delay(_get_humanize_profile())

        await page.keyboard.press(key)

        return {"success": True, "key": key}

    except Exception as e:
        return {"success": False, "error": f"Key press failed: {e}"}


async def pw_screenshot(task_id: str = "default", full_page: bool = False) -> dict[str, Any]:
    """Take screenshot of current page."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    page = _pages[task_id]

    try:
        screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
        import base64
        encoded = base64.b64encode(screenshot_bytes).decode()

        return {
            "success": True,
            "screenshot_base64": encoded,
            "url": page.url,
            "title": await page.title(),
        }

    except Exception as e:
        return {"success": False, "error": f"Screenshot failed: {e}"}


async def pw_evaluate(expression: str, task_id: str = "default") -> dict[str, Any]:
    """Evaluate JavaScript expression in page context."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    page = _pages[task_id]

    try:
        result = await page.evaluate(expression)
        return {"success": True, "result": result}

    except Exception as e:
        return {"success": False, "error": f"Eval failed: {e}"}


async def pw_get_cookies(task_id: str = "default") -> dict[str, Any]:
    """Get all cookies from the current context."""
    if task_id not in _contexts:
        return {"success": False, "error": "No active browser session"}

    context = _contexts[task_id]

    try:
        cookies = await context.cookies()
        return {"success": True, "cookies": cookies}

    except Exception as e:
        return {"success": False, "error": f"Failed to get cookies: {e}"}


async def pw_set_cookies(cookies: list[dict], task_id: str = "default") -> dict[str, Any]:
    """Set cookies in the current context."""
    if task_id not in _contexts:
        return {"success": False, "error": "No active browser session"}

    context = _contexts[task_id]

    try:
        await context.add_cookies(cookies)
        if task_id in _profiles:
            await _save_storage_state(task_id)
        return {"success": True, "count": len(cookies)}

    except Exception as e:
        return {"success": False, "error": f"Failed to set cookies: {e}"}


async def pw_wait_for_selector(selector: str, task_id: str = "default",
                               timeout: int = 10000) -> dict[str, Any]:
    """Wait for a selector to appear on page."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    page = _pages[task_id]

    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return {"success": True, "selector": selector}

    except Exception as e:
        return {"success": False, "error": f"Wait for selector failed: {e}"}


async def pw_get_page_content(task_id: str = "default") -> dict[str, Any]:
    """Get full HTML content of current page."""
    if task_id not in _pages:
        return {"success": False, "error": "No active browser session"}

    page = _pages[task_id]

    try:
        content = await page.content()
        return {"success": True, "content": content, "url": page.url}

    except Exception as e:
        return {"success": False, "error": f"Failed to get content: {e}"}


async def pw_close_session(task_id: str = "default") -> dict[str, Any]:
    """Close browser session and save state."""
    config = _load_config()

    if config.persist_sessions and task_id in _contexts:
        await _save_storage_state(task_id)

    if task_id in _pages:
        try:
            await _pages[task_id].close()
        except Exception:
            pass
        del _pages[task_id]

    if task_id in _contexts:
        try:
            await _contexts[task_id].close()
        except Exception:
            pass
        del _contexts[task_id]

    _mouse_positions.pop(task_id, None)

    return {"success": True}


async def pw_close_all() -> None:
    """Close all sessions and shut down Playwright."""
    global _playwright_instance, _browser_instance

    for task_id in list(_pages.keys()):
        await pw_close_session(task_id)

    if _browser_instance:
        try:
            await _browser_instance.close()
        except Exception:
            pass
        _browser_instance = None

    if _playwright_instance:
        try:
            await _playwright_instance.stop()
        except Exception:
            pass
        _playwright_instance = None


# ============================================================================
# Synchronous Wrappers (for integration with existing sync browser_tool.py)
# ============================================================================


def _get_event_loop():
    """Get or create an event loop for sync wrappers."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return None  # Signal to use run_in_executor
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def _run_async(coro):
    """Run async coroutine synchronously, handling nested event loops."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
    except RuntimeError:
        pass

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def navigate(url: str, task_id: str = "default") -> str:
    """Sync wrapper for pw_navigate."""
    result = _run_async(pw_navigate(url, task_id))
    return json.dumps(result, ensure_ascii=False)


def snapshot(task_id: str = "default", full: bool = False) -> str:
    """Sync wrapper for pw_snapshot."""
    result = _run_async(pw_snapshot(task_id, full))
    return json.dumps(result, ensure_ascii=False)


def click(ref: str, task_id: str = "default") -> str:
    """Sync wrapper for pw_click."""
    result = _run_async(pw_click(ref, task_id))
    return json.dumps(result, ensure_ascii=False)


def type_text(ref: str, text: str, task_id: str = "default") -> str:
    """Sync wrapper for pw_type."""
    result = _run_async(pw_type(ref, text, task_id))
    return json.dumps(result, ensure_ascii=False)


def scroll(direction: str = "down", task_id: str = "default") -> str:
    """Sync wrapper for pw_scroll."""
    result = _run_async(pw_scroll(direction, task_id))
    return json.dumps(result, ensure_ascii=False)


def back(task_id: str = "default") -> str:
    """Sync wrapper for pw_back."""
    result = _run_async(pw_back(task_id))
    return json.dumps(result, ensure_ascii=False)


def press(key: str, task_id: str = "default") -> str:
    """Sync wrapper for pw_press."""
    result = _run_async(pw_press(key, task_id))
    return json.dumps(result, ensure_ascii=False)


def screenshot(task_id: str = "default", full_page: bool = False) -> str:
    """Sync wrapper for pw_screenshot."""
    result = _run_async(pw_screenshot(task_id, full_page))
    return json.dumps(result, ensure_ascii=False)


def evaluate(expression: str, task_id: str = "default") -> str:
    """Sync wrapper for pw_evaluate."""
    result = _run_async(pw_evaluate(expression, task_id))
    return json.dumps(result, ensure_ascii=False)


def close_session(task_id: str = "default") -> str:
    """Sync wrapper for pw_close_session."""
    result = _run_async(pw_close_session(task_id))
    return json.dumps(result, ensure_ascii=False)


def close_all() -> None:
    """Sync wrapper for pw_close_all."""
    _run_async(pw_close_all())


# ============================================================================
# Accessibility Tree Extraction
# ============================================================================


async def _get_accessibility_snapshot(page, full: bool = False) -> str:
    """Extract accessibility tree from page for LLM consumption."""
    try:
        # Use Playwright's built-in accessibility snapshot
        snapshot = await page.accessibility.snapshot()
        if not snapshot:
            return ""

        lines: list[str] = []
        _ref_counter = [0]

        def _walk_tree(node: dict, depth: int = 0) -> None:
            role = node.get("role", "")
            name = node.get("name", "")
            value = node.get("value", "")

            # Skip generic/presentation nodes unless they have content
            if role in ("none", "presentation") and not name:
                for child in node.get("children", []):
                    _walk_tree(child, depth)
                return

            # Assign ref to interactive elements
            ref_str = ""
            if role in ("link", "button", "textbox", "checkbox", "radio",
                        "combobox", "menuitem", "tab", "switch", "slider",
                        "searchbox", "spinbutton", "option"):
                _ref_counter[0] += 1
                ref_str = f" @e{_ref_counter[0]}"

            # Build line
            indent = "  " * depth
            parts = [indent, f"[{role}]"]
            if ref_str:
                parts.append(ref_str)
            if name:
                parts.append(f" \"{name}\"")
            if value and value != name:
                parts.append(f" value=\"{value}\"")

            # Additional properties
            checked = node.get("checked")
            if checked is not None:
                parts.append(f" checked={checked}")
            disabled = node.get("disabled")
            if disabled:
                parts.append(" disabled")
            expanded = node.get("expanded")
            if expanded is not None:
                parts.append(f" expanded={expanded}")

            line = "".join(parts).rstrip()
            if line.strip():
                lines.append(line)

            # Recurse children
            for child in node.get("children", []):
                _walk_tree(child, depth + 1)

        _walk_tree(snapshot, 0)

        # Truncate if not full mode
        if not full and len(lines) > 200:
            lines = lines[:200]
            lines.append("... (truncated, use full=true for complete snapshot)")

        return "\n".join(lines)

    except Exception as e:
        logger.debug("Accessibility snapshot failed: %s", e)
        # Fallback: extract text content
        try:
            text = await page.inner_text("body")
            if len(text) > 5000:
                text = text[:5000] + "..."
            return f"[page text]\n{text}"
        except Exception:
            return ""


# ============================================================================
# Bot Detection Analysis
# ============================================================================

import random

_BOT_DETECTION_PATTERNS = (
    "captcha",
    "are you a robot",
    "verify you are human",
    "access denied",
    "blocked",
    "cloudflare",
    "just a moment",
    "checking your browser",
    "please verify",
    "unusual traffic",
    "bot detection",
    "automated access",
    "security check",
    "ray id",
)


def _check_bot_detection(title: str, content: str) -> Optional[str]:
    """Check if page content indicates bot detection."""
    combined = (title + " " + content[:3000]).lower()

    detected = [p for p in _BOT_DETECTION_PATTERNS if p in combined]
    if detected:
        indicators = ", ".join(detected[:3])
        return (
            f"Possible bot detection triggered (indicators: {indicators}). "
            "Consider: enabling proxy, increasing stealth_level, "
            "adding warmup_urls, or reducing action speed."
        )
    return None


def _ref_to_selector(ref: str) -> str:
    """Convert @eN reference to a CSS selector using aria snapshot ordering."""
    # Strip @ prefix and 'e' character
    ref_clean = ref.lstrip("@").lstrip("e")
    try:
        index = int(ref_clean) - 1
        # Use nth-match on interactive elements
        interactive_selector = (
            "a, button, input, textarea, select, "
            "[role='button'], [role='link'], [role='textbox'], "
            "[role='checkbox'], [role='radio'], [role='combobox'], "
            "[role='menuitem'], [role='tab'], [role='switch'], "
            "[role='slider'], [role='searchbox'], [role='spinbutton'], "
            "[role='option'], [tabindex]"
        )
        return f":nth-match({interactive_selector}, {index + 1})"
    except (ValueError, IndexError):
        return ref


# ============================================================================
# Engine Detection — Used by browser_tool.py to check if playwright mode
# ============================================================================


def is_playwright_mode() -> bool:
    """Return True if Playwright engine is configured as the browser backend."""
    try:
        from hermes_cli.config import read_raw_config
        cfg = read_raw_config()
        browser_cfg = cfg.get("browser", {})
        if isinstance(browser_cfg, dict):
            engine = browser_cfg.get("engine", "auto")
            return engine == "playwright"
    except Exception:
        pass
    return os.getenv("BROWSER_ENGINE", "").lower() == "playwright"

"""
Browser Humanize Module — Human-like Behavior Simulation

Provides realistic human interaction patterns:
- Bezier curve mouse movements with variable speed
- Natural typing with random delays, corrections, and rhythm
- Organic scroll patterns with momentum and variable distance
- Page dwell time simulation
- Random micro-movements and idle behavior
- Focus/blur event simulation
"""

import asyncio
import math
import random
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HumanProfile:
    """Behavioral profile parameters for human simulation."""
    typing_speed_wpm: int = 65
    typing_error_rate: float = 0.02
    mouse_speed_factor: float = 1.0
    scroll_speed_factor: float = 1.0
    min_action_delay_ms: int = 80
    max_action_delay_ms: int = 400
    click_delay_ms: tuple[int, int] = (50, 150)
    double_click_interval_ms: tuple[int, int] = (80, 140)
    hesitation_probability: float = 0.05
    overshoot_probability: float = 0.15


DEFAULT_PROFILE = HumanProfile()

FAST_PROFILE = HumanProfile(
    typing_speed_wpm=90,
    typing_error_rate=0.01,
    mouse_speed_factor=1.5,
    scroll_speed_factor=1.5,
    min_action_delay_ms=40,
    max_action_delay_ms=200,
    click_delay_ms=(30, 80),
    hesitation_probability=0.02,
    overshoot_probability=0.08,
)

CAREFUL_PROFILE = HumanProfile(
    typing_speed_wpm=40,
    typing_error_rate=0.005,
    mouse_speed_factor=0.7,
    scroll_speed_factor=0.6,
    min_action_delay_ms=150,
    max_action_delay_ms=800,
    click_delay_ms=(80, 250),
    hesitation_probability=0.12,
    overshoot_probability=0.20,
)


def _bezier_point(t: float, p0: tuple[float, float], p1: tuple[float, float],
                  p2: tuple[float, float], p3: tuple[float, float]) -> tuple[float, float]:
    """Calculate point on cubic bezier curve at parameter t."""
    u = 1.0 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t

    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return (x, y)


def _generate_control_points(start: tuple[float, float], end: tuple[float, float],
                             overshoot: bool = False) -> tuple[tuple[float, float], tuple[float, float]]:
    """Generate natural-looking bezier control points for mouse movement."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dist = math.sqrt(dx * dx + dy * dy)

    spread = max(dist * 0.3, 20)

    cp1 = (
        start[0] + dx * random.uniform(0.2, 0.4) + random.gauss(0, spread * 0.3),
        start[1] + dy * random.uniform(0.2, 0.4) + random.gauss(0, spread * 0.3),
    )

    if overshoot:
        overshoot_factor = random.uniform(1.05, 1.15)
        cp2 = (
            start[0] + dx * overshoot_factor + random.gauss(0, spread * 0.2),
            start[1] + dy * overshoot_factor + random.gauss(0, spread * 0.2),
        )
    else:
        cp2 = (
            start[0] + dx * random.uniform(0.6, 0.8) + random.gauss(0, spread * 0.3),
            start[1] + dy * random.uniform(0.6, 0.8) + random.gauss(0, spread * 0.3),
        )

    return cp1, cp2


def generate_mouse_path(start: tuple[float, float], end: tuple[float, float],
                        profile: HumanProfile = DEFAULT_PROFILE) -> list[tuple[float, float, float]]:
    """Generate human-like mouse path as list of (x, y, delay_ms) tuples."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.sqrt(dx * dx + dy * dy)

    if distance < 2:
        return [(end[0], end[1], random.randint(5, 15))]

    overshoot = random.random() < profile.overshoot_probability and distance > 50
    cp1, cp2 = _generate_control_points(start, end, overshoot=overshoot)

    num_steps = max(int(distance / (3.0 * profile.mouse_speed_factor)), 8)
    num_steps = min(num_steps, 150)

    points: list[tuple[float, float, float]] = []

    for i in range(num_steps):
        t = (i + 1) / num_steps
        # Ease-out timing: faster at start, slower at end
        eased_t = 1.0 - (1.0 - t) ** 2.2

        point = _bezier_point(eased_t, start, cp1, cp2, end)

        # Variable speed: slower near target
        progress_to_end = 1.0 - abs(t - 1.0)
        base_delay = 4 + 8 * progress_to_end ** 2
        jitter = random.gauss(0, 1.5)
        delay = max(2, base_delay + jitter) / profile.mouse_speed_factor

        points.append((point[0], point[1], delay))

    if overshoot:
        # Add correction movement back to target
        correction_start = points[-1][:2]
        correction_cp1 = (
            correction_start[0] + (end[0] - correction_start[0]) * 0.5 + random.gauss(0, 3),
            correction_start[1] + (end[1] - correction_start[1]) * 0.5 + random.gauss(0, 3),
        )
        correction_steps = random.randint(4, 8)
        for i in range(correction_steps):
            t = (i + 1) / correction_steps
            x = correction_start[0] + (end[0] - correction_start[0]) * t + random.gauss(0, 0.5)
            y = correction_start[1] + (end[1] - correction_start[1]) * t + random.gauss(0, 0.5)
            points.append((x, y, random.uniform(6, 14) / profile.mouse_speed_factor))

    # Ensure final point is exact target
    points.append((end[0], end[1], random.uniform(2, 5)))

    return points


async def human_mouse_move(page, target_x: float, target_y: float,
                           profile: HumanProfile = DEFAULT_PROFILE,
                           start_pos: Optional[tuple[float, float]] = None) -> None:
    """Move mouse to target position with human-like bezier curve trajectory."""
    if start_pos is None:
        start_pos = (
            random.uniform(target_x * 0.3, target_x * 0.7) if target_x > 100 else random.uniform(10, 200),
            random.uniform(target_y * 0.3, target_y * 0.7) if target_y > 100 else random.uniform(10, 200),
        )

    path = generate_mouse_path(start_pos, (target_x, target_y), profile)

    for x, y, delay_ms in path:
        await page.mouse.move(x, y)
        await asyncio.sleep(delay_ms / 1000.0)


async def human_click(page, x: float, y: float,
                      profile: HumanProfile = DEFAULT_PROFILE,
                      button: str = "left",
                      start_pos: Optional[tuple[float, float]] = None) -> None:
    """Click at position with human-like mouse movement and timing."""
    await human_mouse_move(page, x, y, profile, start_pos)

    # Pre-click hesitation
    if random.random() < profile.hesitation_probability:
        await asyncio.sleep(random.uniform(0.3, 0.8))

    # Click with natural delay
    click_delay = random.randint(*profile.click_delay_ms) / 1000.0
    await asyncio.sleep(click_delay)

    await page.mouse.down(button=button)
    # Hold duration varies
    hold_ms = random.uniform(50, 120)
    await asyncio.sleep(hold_ms / 1000.0)
    await page.mouse.up(button=button)

    # Post-click settle time
    await asyncio.sleep(random.uniform(0.05, 0.15))


async def human_type(page, selector_or_element, text: str,
                     profile: HumanProfile = DEFAULT_PROFILE,
                     clear_first: bool = True) -> None:
    """Type text with human-like rhythm, delays, and occasional corrections."""
    element = selector_or_element
    if isinstance(element, str):
        element = page.locator(element)

    if clear_first:
        await element.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.keyboard.press("Control+a" if random.random() > 0.3 else "Meta+a")
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.keyboard.press("Backspace")
        await asyncio.sleep(random.uniform(0.1, 0.3))

    # Calculate base delay per character from WPM
    chars_per_minute = profile.typing_speed_wpm * 5
    base_delay_ms = 60000.0 / chars_per_minute

    i = 0
    while i < len(text):
        char = text[i]

        # Simulate typo and correction
        if random.random() < profile.typing_error_rate and i < len(text) - 1:
            wrong_char = chr(ord(char) + random.choice([-1, 1, -2, 2]))
            if wrong_char.isprintable():
                await page.keyboard.type(wrong_char, delay=0)
                await asyncio.sleep(random.uniform(0.1, 0.4))
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.2))

        await page.keyboard.type(char, delay=0)

        # Variable inter-key delay
        if char == " ":
            delay = base_delay_ms * random.uniform(1.2, 2.5)
        elif char in ".,;:!?":
            delay = base_delay_ms * random.uniform(1.5, 3.0)
        elif char == "\n":
            delay = base_delay_ms * random.uniform(2.0, 4.0)
        else:
            delay = base_delay_ms * random.uniform(0.6, 1.8)

        # Occasional burst typing (faster sequence)
        if random.random() < 0.1:
            delay *= 0.4

        # Occasional pause (thinking)
        if random.random() < 0.02:
            delay += random.uniform(300, 800)

        await asyncio.sleep(delay / 1000.0)
        i += 1


async def human_scroll(page, direction: str = "down",
                       distance: Optional[int] = None,
                       profile: HumanProfile = DEFAULT_PROFILE) -> None:
    """Scroll with human-like variable speed, momentum, and pauses."""
    if distance is None:
        distance = random.randint(200, 600)

    sign = -1 if direction == "up" else 1
    remaining = distance
    scroll_events: list[tuple[int, float]] = []

    # Generate scroll chunks with momentum
    while remaining > 0:
        # Variable chunk size (like flicking a trackpad)
        if remaining > 200:
            chunk = random.randint(40, 120)
        elif remaining > 50:
            chunk = random.randint(20, 60)
        else:
            chunk = remaining

        chunk = min(chunk, remaining)
        remaining -= chunk

        # Delay between scroll events (momentum feel)
        if remaining > distance * 0.5:
            delay = random.uniform(15, 40)  # Fast in the middle
        else:
            delay = random.uniform(30, 80)  # Slow at start/end

        delay /= profile.scroll_speed_factor
        scroll_events.append((chunk * sign, delay))

    for delta, delay_ms in scroll_events:
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(delay_ms / 1000.0)

    # Post-scroll settle
    await asyncio.sleep(random.uniform(0.1, 0.4))


async def human_wait(min_ms: int = 500, max_ms: int = 2000) -> None:
    """Wait a random human-like duration (simulates reading/thinking)."""
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000.0)


async def human_page_dwell(page, profile: HumanProfile = DEFAULT_PROFILE) -> None:
    """Simulate a human looking at a page: random scrolls, mouse jitter, pauses."""
    actions = random.randint(1, 4)

    for _ in range(actions):
        action = random.choice(["idle", "scroll", "jitter"])

        if action == "idle":
            await asyncio.sleep(random.uniform(0.5, 2.5))
        elif action == "scroll":
            direction = random.choice(["down", "down", "down", "up"])
            await human_scroll(page, direction, random.randint(50, 200), profile)
        elif action == "jitter":
            # Small mouse micro-movement
            vw = page.viewport_size.get("width", 1280) if page.viewport_size else 1280
            vh = page.viewport_size.get("height", 720) if page.viewport_size else 720
            x = random.uniform(vw * 0.2, vw * 0.8)
            y = random.uniform(vh * 0.2, vh * 0.8)
            await page.mouse.move(x, y, steps=random.randint(3, 8))
            await asyncio.sleep(random.uniform(0.1, 0.5))


async def random_pre_action_delay(profile: HumanProfile = DEFAULT_PROFILE) -> None:
    """Random delay before performing an action (simulates decision time)."""
    delay = random.randint(profile.min_action_delay_ms, profile.max_action_delay_ms)
    await asyncio.sleep(delay / 1000.0)


def get_random_viewport_offset() -> tuple[int, int]:
    """Return small random offset to add to viewport size for uniqueness."""
    return (random.randint(-20, 20), random.randint(-10, 10))

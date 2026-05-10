"""Tests for browser_humanize module — human-like behavior simulation."""

import pytest
import math
from tools.browser_humanize import (
    generate_mouse_path,
    HumanProfile,
    DEFAULT_PROFILE,
    FAST_PROFILE,
    CAREFUL_PROFILE,
    get_random_viewport_offset,
)


class TestMousePath:
    def test_generates_path_with_points(self):
        path = generate_mouse_path((0, 0), (500, 300))
        assert len(path) > 5
        assert all(len(p) == 3 for p in path)

    def test_path_ends_near_target(self):
        target = (800.0, 600.0)
        path = generate_mouse_path((0, 0), target)
        last_x, last_y, _ = path[-1]
        assert abs(last_x - target[0]) < 2.0
        assert abs(last_y - target[1]) < 2.0

    def test_path_has_positive_delays(self):
        path = generate_mouse_path((100, 100), (500, 500))
        for _, _, delay in path:
            assert delay > 0

    def test_short_distance_generates_fewer_points(self):
        short_path = generate_mouse_path((100, 100), (105, 105))
        long_path = generate_mouse_path((0, 0), (1000, 800))
        assert len(short_path) < len(long_path)

    def test_zero_distance_generates_single_point(self):
        path = generate_mouse_path((100, 100), (100, 100))
        assert len(path) == 1

    def test_fast_profile_shorter_delays(self):
        path_normal = generate_mouse_path((0, 0), (500, 500), DEFAULT_PROFILE)
        path_fast = generate_mouse_path((0, 0), (500, 500), FAST_PROFILE)

        avg_delay_normal = sum(d for _, _, d in path_normal) / len(path_normal)
        avg_delay_fast = sum(d for _, _, d in path_fast) / len(path_fast)
        assert avg_delay_fast < avg_delay_normal

    def test_path_not_straight_line(self):
        start = (0.0, 0.0)
        end = (1000.0, 0.0)
        path = generate_mouse_path(start, end)
        y_values = [p[1] for p in path]
        assert any(abs(y) > 5 for y in y_values)

    def test_different_calls_produce_different_paths(self):
        path1 = generate_mouse_path((0, 0), (500, 500))
        path2 = generate_mouse_path((0, 0), (500, 500))
        # Paths should differ due to randomness
        points1 = [(round(x, 1), round(y, 1)) for x, y, _ in path1]
        points2 = [(round(x, 1), round(y, 1)) for x, y, _ in path2]
        assert points1 != points2


class TestHumanProfile:
    def test_default_profile_values(self):
        p = DEFAULT_PROFILE
        assert p.typing_speed_wpm == 65
        assert 0 < p.typing_error_rate < 0.1
        assert p.mouse_speed_factor == 1.0

    def test_fast_profile_is_faster(self):
        assert FAST_PROFILE.typing_speed_wpm > DEFAULT_PROFILE.typing_speed_wpm
        assert FAST_PROFILE.mouse_speed_factor > DEFAULT_PROFILE.mouse_speed_factor
        assert FAST_PROFILE.min_action_delay_ms < DEFAULT_PROFILE.min_action_delay_ms

    def test_careful_profile_is_slower(self):
        assert CAREFUL_PROFILE.typing_speed_wpm < DEFAULT_PROFILE.typing_speed_wpm
        assert CAREFUL_PROFILE.mouse_speed_factor < DEFAULT_PROFILE.mouse_speed_factor
        assert CAREFUL_PROFILE.min_action_delay_ms > DEFAULT_PROFILE.min_action_delay_ms

    def test_profile_is_frozen(self):
        with pytest.raises(Exception):
            DEFAULT_PROFILE.typing_speed_wpm = 100  # type: ignore


class TestViewportOffset:
    def test_returns_tuple_of_two_ints(self):
        offset = get_random_viewport_offset()
        assert isinstance(offset, tuple)
        assert len(offset) == 2
        assert isinstance(offset[0], int)
        assert isinstance(offset[1], int)

    def test_offset_within_bounds(self):
        for _ in range(100):
            x, y = get_random_viewport_offset()
            assert -20 <= x <= 20
            assert -10 <= y <= 10

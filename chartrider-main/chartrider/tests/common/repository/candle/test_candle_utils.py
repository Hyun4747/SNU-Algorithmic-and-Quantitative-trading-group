import numpy as np

from chartrider.core.common.repository.candle.utils import find_holes


def test_find_holes_1():
    holes = find_holes(np.array([0, 1, 2, 3, 4, 5]))
    assert holes == []


def test_find_hole_ranges_2():
    holes = find_holes(np.array([0, 1, 3, 4, 5]))
    assert holes == [(1, 3)]


def test_find_hole_ranges_3():
    holes = find_holes(np.array([0, 1, 3, 4, 5, 7, 8, 9]))
    assert holes == [(1, 3), (5, 7)]


def test_find_hole_ranges_4():
    holes = find_holes(np.array([0, 1, 3, 4, 5, 7, 8, 9, 11, 12]))
    assert holes == [(1, 3), (5, 7), (9, 11)]


def test_find_hole_ranges_5():
    holes = find_holes(np.array([5, 6]))
    assert holes == []


def test_find_hole_ranges_6():
    holes = find_holes(np.array([]))
    assert holes == []


def test_find_hole_ranges_7():
    holes = find_holes(np.array([5]))
    assert holes == []


def test_find_hole_ranges_8():
    holes = find_holes(np.array([5, 10, 15]))
    assert holes == [(5, 10), (10, 15)]


def test_find_hole_ranges_9():
    holes = find_holes(np.array([10, 9, 4]))
    assert holes == []


def test_find_hole_ranges_10():
    holes = find_holes(np.array([10, 11, 12, 5, 13]))
    assert holes == []

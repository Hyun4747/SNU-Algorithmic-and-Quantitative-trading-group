import numpy as np
from numpy.typing import NDArray


def find_holes(array: NDArray[np.int_], normalize_factor: int = 1) -> list[tuple[int, int]]:
    array = array // normalize_factor
    gaps = array[1:] - array[:-1]

    if np.any(gaps < 0):
        # Should be sorted
        return []

    holes: list[tuple[int, int]] = []
    indices = np.where(gaps > 1)[0]
    for i in indices:
        hole_start = int(array[i]) * normalize_factor
        hole_end = int(array[i + 1]) * normalize_factor
        holes.append((hole_start, hole_end))
    return holes

"use strict";

/**
 * Renderer will assign a unique id to `$id` for each figure.
 */
const timerName = "$id";

clearTimeout(window[timerName]);

window[timerName] = setTimeout(function () {
  /**
   * @variable `cb_obj` - x_range of the figure.
   * @variable `high` - high values of the ohlc. Plain volume if volume chart.
   * @variable `low` - low values of the ohlc. None if volume chart.
   * @variable `resample_freq_min` - resample frequency in minutes.
   * @variable `y_range` - y_range of the figure to scale.
   * @variable `min_timestamp` - The first timestamp of the data.
   */

  const denominator = 1000 * 60 * resample_freq_min;

  // Convert timestamp to index
  const i = Math.max(
    Math.floor((cb_obj.start - min_timestamp) / denominator),
    0
  );
  const j = Math.min(
    Math.ceil((cb_obj.end - min_timestamp) / denominator),
    high.length
  );

  if (i > j) {
    return; // Avoids executing the rest of the code if range is invalid
  }

  const rangeHigh = high.slice(i, j);
  const rangeLow = low ? low.slice(i, j) : [];

  const maxHigh = rangeHigh.reduce(
    (max, value) => Math.max(max, value),
    -Infinity
  );
  const minLow =
    rangeLow.length > 0
      ? rangeLow.reduce((min, value) => Math.min(min, value), Infinity)
      : 0;

  const pad = (maxHigh - minLow) * 0.05;
  y_range.start = minLow - pad;
  y_range.end = maxHigh + pad;
}, 5);

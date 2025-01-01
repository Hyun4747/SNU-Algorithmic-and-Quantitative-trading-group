const endsWith = "$endsWith";

const findElementsInShadowRoot = (selector) => {
  const elements = [];
  const shadowRoots = [document];

  while (shadowRoots.length) {
    const currentRoot = shadowRoots.pop();
    if (currentRoot.shadowRoot) {
      shadowRoots.push(currentRoot.shadowRoot);
    }

    currentRoot.querySelectorAll("div").forEach((el) => {
      if (el.matches(selector)) {
        elements.push(el);
      } else if (el.shadowRoot) {
        shadowRoots.push(el.shadowRoot);
      }
    });
  }
  return elements;
};

const stackTooltips = () => {
  const tooltips = findElementsInShadowRoot(".bk-Tooltip");
  if (!tooltips.length) {
    return;
  }
  let currentTopOffset = tooltips[0].offsetTop;
  tooltips.forEach((tooltip, index) => {
    tooltip.style.top = `${currentTopOffset}px`;
    currentTopOffset += tooltip.offsetHeight;
  });
};

stackTooltips();

if (cb_data.index.indices.length > 0) {
  const index = cb_data.index.indices[0];
  const createTooltips = (source, index) =>
    Object.keys(source)
      .filter((key) => key.endsWith(endsWith))
      .filter(
        (key) => index < source[key].length && source[key][index] !== null
      )
      .map((key) => [key.slice(0, -endsWith.length), `@${key}`])
      // snake_case to human readable text with capitalization
      .map(([key, value]) => [
        key
          .split("_")
          .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
          .join(" "),
        value,
      ])
      // sort by key's length, tiebreak lexicographically
      .sort((a, b) => {
        if (a[0].length !== b[0].length) {
          return a[0].length - b[0].length;
        }
        return a[0].localeCompare(b[0]);
      });

  const tooltips = createTooltips(source.data, index);
  hover.tooltips = tooltips;
}

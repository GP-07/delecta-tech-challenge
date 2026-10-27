// jsdom has no layout: charts need a ResizeObserver to mount (they render empty, which is enough here).
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

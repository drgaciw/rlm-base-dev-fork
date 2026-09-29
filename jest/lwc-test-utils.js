// Shared helpers for the LWC Jest suites. Import as '@rlm/lwc-test-utils'
// (mapped in jest.config.js).
import { createElement } from "lwc";

// Creates `<tag>` from `Ctor`, applies `props` as public properties, attaches
// it to the document and returns the element.
export function mountComponent(tag, Ctor, props = {}) {
  const el = createElement(tag, { is: Ctor });
  Object.assign(el, props);
  document.body.appendChild(el);
  return el;
}

// Lets pending promise callbacks (wire emissions, imperative Apex) settle and
// the component re-render.
export async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
}

// Use as `afterEach(clearDocument)` so components never leak between tests.
export function clearDocument() {
  while (document.body.firstChild) {
    document.body.removeChild(document.body.firstChild);
  }
}

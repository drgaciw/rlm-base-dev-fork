// Test wire adapters are emitted directly, which the LWC lint rule flags.
/* eslint-disable @lwc/lwc/no-unexpected-wire-adapter-usages */
import { createElement } from "lwc";
import RlmLearningAppDetailParent from "c/rlmLearningAppDetailParent";
import { CurrentPageReference } from "lightning/navigation";

jest.mock(
  "lightning/modal",
  () => {
    const { LightningElement } = jest.requireActual("lwc");
    class LightningModal extends LightningElement {}
    LightningModal.open = jest.fn(() => Promise.resolve());
    return { __esModule: true, default: LightningModal };
  },
  { virtual: true }
);

const TAG = "c-rlm-learning-app-detail-parent";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningAppDetailParent });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-app-detail-parent", () => {
  afterEach(() => {
    while (document.body.firstChild) {
      document.body.removeChild(document.body.firstChild);
    }
  });

  it("renders without throwing", async () => {
    const el = mount();
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    CurrentPageReference.emit({ state: {} });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

// Test wire adapters are emitted directly, which the LWC lint rule flags.
/* eslint-disable @lwc/lwc/no-unexpected-wire-adapter-usages */
import RlmLearningAppDetailParent from "c/rlmLearningAppDetailParent";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
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

const mount = (props = {}) =>
  mountComponent(TAG, RlmLearningAppDetailParent, { ...{}, ...props });

describe("c-rlm-learning-app-detail-parent", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    CurrentPageReference.emit({ state: {} });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

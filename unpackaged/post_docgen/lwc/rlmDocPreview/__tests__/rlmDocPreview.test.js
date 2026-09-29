import RlmDocPreview from "c/rlmDocPreview";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-doc-preview";

const mount = (props = {}) =>
  mountComponent(TAG, RlmDocPreview, { ...{}, ...props });

describe("c-rlm-doc-preview", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

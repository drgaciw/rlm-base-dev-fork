import RlmRebuildSearchIndex from "c/rlmRebuildSearchIndex";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-rebuild-search-index";

const mount = (props = {}) =>
  mountComponent(TAG, RlmRebuildSearchIndex, { ...{}, ...props });

describe("c-rlm-rebuild-search-index", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

import RlmSetUpQuoteHierarchyTree from "c/rlmSetUpQuoteHierarchyTree";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-set-up-quote-hierarchy-tree";

const mount = (props = {}) =>
  mountComponent(TAG, RlmSetUpQuoteHierarchyTree, { ...{}, ...props });

describe("c-rlm-set-up-quote-hierarchy-tree", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

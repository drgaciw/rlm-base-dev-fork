import RlmCollectionRuleBuilder from "c/rlmCollectionRuleBuilder";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-collection-rule-builder";

const mount = (props = {}) =>
  mountComponent(TAG, RlmCollectionRuleBuilder, { ...{}, ...props });

describe("c-rlm-collection-rule-builder", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

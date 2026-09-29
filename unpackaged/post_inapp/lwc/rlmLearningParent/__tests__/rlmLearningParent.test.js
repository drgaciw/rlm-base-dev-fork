import RlmLearningParent from "c/rlmLearningParent";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-learning-parent";

const mount = (props = {}) =>
  mountComponent(TAG, RlmLearningParent, { ...{}, ...props });

describe("c-rlm-learning-parent", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

import RlmLearningRightContainer from "c/rlmLearningRightContainer";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-learning-right-container";

const mount = (props = {}) =>
  mountComponent(TAG, RlmLearningRightContainer, { ...{}, ...props });

describe("c-rlm-learning-right-container", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

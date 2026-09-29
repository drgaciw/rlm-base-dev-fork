import RlmUsageOrchestration from "c/rlmUsageOrchestration";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-usage-orchestration";

const mount = (props = {}) =>
  mountComponent(TAG, RlmUsageOrchestration, { ...{}, ...props });

describe("c-rlm-usage-orchestration", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

import RlmDecisionTableManager from "c/rlmDecisionTableManager";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-decision-table-manager";

const mount = (props = {}) =>
  mountComponent(TAG, RlmDecisionTableManager, { ...{}, ...props });

describe("c-rlm-decision-table-manager", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

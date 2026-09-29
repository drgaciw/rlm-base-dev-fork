import RlmOrderRedirect from "c/rlmOrderRedirect";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-order-redirect";

const mount = (props = {}) =>
  mountComponent(TAG, RlmOrderRedirect, { ...{}, ...props });

describe("c-rlm-order-redirect", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

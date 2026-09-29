import RlmQuoteRedirect from "c/rlmQuoteRedirect";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-quote-redirect";

const mount = (props = {}) =>
  mountComponent(TAG, RlmQuoteRedirect, { ...{}, ...props });

describe("c-rlm-quote-redirect", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

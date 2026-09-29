import RlmSetUpQuoteWizard from "c/rlmSetUpQuoteWizard";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-set-up-quote-wizard";

const mount = (props = {}) =>
  mountComponent(TAG, RlmSetUpQuoteWizard, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-set-up-quote-wizard", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

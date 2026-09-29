// Test wire adapters are emitted directly, which the LWC lint rule flags.
/* eslint-disable @lwc/lwc/no-unexpected-wire-adapter-usages */
import RlmRefundButton from "c/rlmRefundButton";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import { getRecord } from "lightning/uiRecordApi";

const TAG = "c-rlm-refund-button";

const mount = (props = {}) =>
  mountComponent(TAG, RlmRefundButton, {
    ...{ objectApiName: "Payment", recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-refund-button", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getRecord.emit({ fields: { Balance: { value: 25 } } });
    await flushPromises();
    expect(el.shadowRoot.querySelector("lightning-button").disabled).toBe(
      false
    );
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getRecord.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.shadowRoot.querySelector("lightning-button").disabled).toBe(true);
  });
});

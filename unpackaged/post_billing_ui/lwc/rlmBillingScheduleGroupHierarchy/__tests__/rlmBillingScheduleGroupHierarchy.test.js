// Test wire adapters are emitted directly, which the LWC lint rule flags.
/* eslint-disable @lwc/lwc/no-unexpected-wire-adapter-usages */
import RlmBillingScheduleGroupHierarchy from "c/rlmBillingScheduleGroupHierarchy";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import { getRecord } from "lightning/uiRecordApi";

const TAG = "c-rlm-billing-schedule-group-hierarchy";

const mount = (props = {}) =>
  mountComponent(TAG, RlmBillingScheduleGroupHierarchy, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-billing-schedule-group-hierarchy", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getRecord.emit({ fields: {} });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getRecord.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

// Test wire adapters are emitted directly, which the LWC lint rule flags.
/* eslint-disable @lwc/lwc/no-unexpected-wire-adapter-usages */
import { createElement } from "lwc";
import RlmBillingScheduleGroupHierarchy from "c/rlmBillingScheduleGroupHierarchy";
import { getRecord } from "lightning/uiRecordApi";

const TAG = "c-rlm-billing-schedule-group-hierarchy";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmBillingScheduleGroupHierarchy });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-billing-schedule-group-hierarchy", () => {
  afterEach(() => {
    while (document.body.firstChild) {
      document.body.removeChild(document.body.firstChild);
    }
  });

  it("renders without throwing", async () => {
    const el = mount();
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getRecord.emit({ fields: {} });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getRecord.emitError({ body: { message: "boom" }, status: 500 });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

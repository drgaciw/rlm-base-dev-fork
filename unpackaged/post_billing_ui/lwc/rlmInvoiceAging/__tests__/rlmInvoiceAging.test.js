import RlmInvoiceAging from "c/rlmInvoiceAging";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getInvoiceAgingData from "@salesforce/apex/RLM_InvoiceAgingController.getInvoiceAgingData";

jest.mock(
  "@salesforce/apex/RLM_InvoiceAgingController.getInvoiceAgingData",
  () => {
    const { createApexTestWireAdapter } = jest.requireActual(
      "@salesforce/sfdx-lwc-jest"
    );
    return {
      default: createApexTestWireAdapter(jest.fn(() => Promise.resolve()))
    };
  },
  { virtual: true }
);

const TAG = "c-rlm-invoice-aging";

const mount = (props = {}) =>
  mountComponent(TAG, RlmInvoiceAging, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-invoice-aging", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getInvoiceAgingData.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getInvoiceAgingData.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

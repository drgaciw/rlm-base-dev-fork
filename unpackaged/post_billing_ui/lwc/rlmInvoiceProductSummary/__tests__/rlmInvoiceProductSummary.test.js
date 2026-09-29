import RlmInvoiceProductSummary from "c/rlmInvoiceProductSummary";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getInvoiceProductSummary from "@salesforce/apex/RLM_InvoiceProductSummaryController.getInvoiceProductSummary";

jest.mock(
  "@salesforce/apex/RLM_InvoiceProductSummaryController.getInvoiceProductSummary",
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

const TAG = "c-rlm-invoice-product-summary";

const mount = (props = {}) =>
  mountComponent(TAG, RlmInvoiceProductSummary, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-invoice-product-summary", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getInvoiceProductSummary.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getInvoiceProductSummary.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

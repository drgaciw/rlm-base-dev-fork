import RlmInvoiceTaxSummary from "c/rlmInvoiceTaxSummary";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getTaxSummaryByInvoice from "@salesforce/apex/RLM_InvoiceTaxSummaryController.getTaxSummaryByInvoice";

jest.mock(
  "@salesforce/apex/RLM_InvoiceTaxSummaryController.getTaxSummaryByInvoice",
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

const TAG = "c-rlm-invoice-tax-summary";

const mount = (props = {}) =>
  mountComponent(TAG, RlmInvoiceTaxSummary, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-invoice-tax-summary", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getTaxSummaryByInvoice.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getTaxSummaryByInvoice.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

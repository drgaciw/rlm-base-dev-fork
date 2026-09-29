import { createElement } from "lwc";
import RlmInvoiceTaxSummary from "c/rlmInvoiceTaxSummary";
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

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmInvoiceTaxSummary });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-invoice-tax-summary", () => {
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
    getTaxSummaryByInvoice.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getTaxSummaryByInvoice.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

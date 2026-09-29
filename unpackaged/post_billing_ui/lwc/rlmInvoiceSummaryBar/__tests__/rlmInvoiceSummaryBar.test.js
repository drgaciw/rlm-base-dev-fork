import { createElement } from "lwc";
import RlmInvoiceSummaryBar from "c/rlmInvoiceSummaryBar";
import getInvoiceSummary from "@salesforce/apex/RLM_InvoiceSummaryController.getInvoiceSummary";
import getBillingSummary from "@salesforce/apex/RLM_OnAccountBillingController.getBillingSummary";

jest.mock(
  "@salesforce/apex/RLM_InvoiceSummaryController.getInvoiceSummary",
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

jest.mock(
  "@salesforce/apex/RLM_OnAccountBillingController.getBillingSummary",
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

const TAG = "c-rlm-invoice-summary-bar";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmInvoiceSummaryBar });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-invoice-summary-bar", () => {
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
    getInvoiceSummary.emit([]);
    getBillingSummary.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getInvoiceSummary.emitError({ body: { message: "boom" }, status: 500 });
    getBillingSummary.emitError({ body: { message: "boom" }, status: 500 });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

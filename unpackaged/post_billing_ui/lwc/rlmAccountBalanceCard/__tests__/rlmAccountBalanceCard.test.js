import RlmAccountBalanceCard from "c/rlmAccountBalanceCard";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
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

const TAG = "c-rlm-account-balance-card";

const mount = (props = {}) =>
  mountComponent(TAG, RlmAccountBalanceCard, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-account-balance-card", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getInvoiceSummary.emit([]);
    getBillingSummary.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getInvoiceSummary.emitError({ body: { message: "boom" }, status: 500 });
    getBillingSummary.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

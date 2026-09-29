import RlmInvoiceTransactionJournals from "c/rlmInvoiceTransactionJournals";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getByInvoice from "@salesforce/apex/RLM_TxnJournalRelatedListController.getByInvoice";

jest.mock(
  "@salesforce/apex/RLM_TxnJournalRelatedListController.getByInvoice",
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

const TAG = "c-rlm-invoice-transaction-journals";

const mount = (props = {}) =>
  mountComponent(TAG, RlmInvoiceTransactionJournals, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-invoice-transaction-journals", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getByInvoice.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getByInvoice.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

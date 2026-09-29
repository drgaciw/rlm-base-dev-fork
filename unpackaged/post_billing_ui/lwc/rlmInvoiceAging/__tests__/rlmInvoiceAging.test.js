import { createElement } from "lwc";
import RlmInvoiceAging from "c/rlmInvoiceAging";
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

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmInvoiceAging });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-invoice-aging", () => {
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
    getInvoiceAgingData.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getInvoiceAgingData.emitError({ body: { message: "boom" }, status: 500 });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

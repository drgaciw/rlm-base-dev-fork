import { createElement } from "lwc";
import RlmPaymentsData from "c/rlmPaymentsData";
import getPaymentScheduleItems from "@salesforce/apex/RLM_PaymentsDataController.getPaymentScheduleItems";
import getAccountOptions from "@salesforce/apex/RLM_PaymentsDataController.getAccountOptions";

jest.mock(
  "@salesforce/apex/RLM_PaymentsDataController.getPaymentScheduleItems",
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
  "@salesforce/apex/RLM_PaymentsDataController.getAccountOptions",
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

const TAG = "c-rlm-payments-data";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmPaymentsData });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-payments-data", () => {
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
    getAccountOptions.emit([]);
    getPaymentScheduleItems.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getAccountOptions.emitError({ body: { message: "boom" }, status: 500 });
    getPaymentScheduleItems.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

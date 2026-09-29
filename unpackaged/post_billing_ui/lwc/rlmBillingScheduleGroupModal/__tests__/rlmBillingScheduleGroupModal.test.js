import { createElement } from "lwc";
import RlmBillingScheduleGroupModal from "c/rlmBillingScheduleGroupModal";
import getAccountBillingInfo from "@salesforce/apex/RLM_BillingScheduleGroupService.getAccountBillingInfo";
import getLegalEntities from "@salesforce/apex/RLM_BillingScheduleGroupService.getLegalEntities";
import getTaxTreatments from "@salesforce/apex/RLM_BillingScheduleGroupService.getTaxTreatments";
import getProducts from "@salesforce/apex/RLM_BillingScheduleGroupService.getProducts";

jest.mock(
  "@salesforce/apex/RLM_BillingScheduleGroupService.getAccountBillingInfo",
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
  "@salesforce/apex/RLM_BillingScheduleGroupService.getLegalEntities",
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
  "@salesforce/apex/RLM_BillingScheduleGroupService.getTaxTreatments",
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
  "@salesforce/apex/RLM_BillingScheduleGroupService.getProducts",
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
  "lightning/actions",
  () => ({
    CloseActionScreenEvent: class CloseActionScreenEvent extends CustomEvent {
      constructor() {
        super("close");
      }
    }
  }),
  { virtual: true }
);

const TAG = "c-rlm-billing-schedule-group-modal";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmBillingScheduleGroupModal });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-billing-schedule-group-modal", () => {
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
    getAccountBillingInfo.emit([]);
    getLegalEntities.emit([]);
    getTaxTreatments.emit([]);
    getProducts.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getAccountBillingInfo.emitError({ body: { message: "boom" }, status: 500 });
    getLegalEntities.emitError({ body: { message: "boom" }, status: 500 });
    getTaxTreatments.emitError({ body: { message: "boom" }, status: 500 });
    getProducts.emitError({ body: { message: "boom" }, status: 500 });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

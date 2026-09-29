import RlmBillingScheduleGroupModal from "c/rlmBillingScheduleGroupModal";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
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

const mount = (props = {}) =>
  mountComponent(TAG, RlmBillingScheduleGroupModal, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-billing-schedule-group-modal", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getAccountBillingInfo.emit([]);
    getLegalEntities.emit([]);
    getTaxTreatments.emit([]);
    getProducts.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getAccountBillingInfo.emitError({ body: { message: "boom" }, status: 500 });
    getLegalEntities.emitError({ body: { message: "boom" }, status: 500 });
    getTaxTreatments.emitError({ body: { message: "boom" }, status: 500 });
    getProducts.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

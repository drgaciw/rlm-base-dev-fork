import RlmCollectionsDashboard from "c/rlmCollectionsDashboard";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getDashboardCards from "@salesforce/apex/RLM_CollectionsDashboardController.getDashboardCards";
import getWorklist from "@salesforce/apex/RLM_CollectionsDashboardController.getWorklist";
import getCollectionPlanTasks from "@salesforce/apex/RLM_CollectionsDashboardController.getCollectionPlanTasks";
import getPaymentPromiseSummary from "@salesforce/apex/RLM_CollectionsDashboardController.getPaymentPromiseSummary";
import getMyCollectionPlans from "@salesforce/apex/RLM_CollectionsDashboardController.getMyCollectionPlans";
import getCollectionsProgress from "@salesforce/apex/RLM_CollectionsDashboardController.getCollectionsProgress";

jest.mock(
  "@salesforce/apex/RLM_CollectionsDashboardController.getDashboardCards",
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
  "@salesforce/apex/RLM_CollectionsDashboardController.getWorklist",
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
  "@salesforce/apex/RLM_CollectionsDashboardController.getCollectionPlanTasks",
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
  "@salesforce/apex/RLM_CollectionsDashboardController.getPaymentPromiseSummary",
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
  "@salesforce/apex/RLM_CollectionsDashboardController.getMyCollectionPlans",
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
  "@salesforce/apex/RLM_CollectionsDashboardController.getCollectionsProgress",
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

const TAG = "c-rlm-collections-dashboard";

const mount = (props = {}) =>
  mountComponent(TAG, RlmCollectionsDashboard, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-collections-dashboard", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getDashboardCards.emit([]);
    getCollectionPlanTasks.emit([]);
    getPaymentPromiseSummary.emit([]);
    getMyCollectionPlans.emit([]);
    getCollectionsProgress.emit([]);
    getWorklist.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getDashboardCards.emitError({ body: { message: "boom" }, status: 500 });
    getCollectionPlanTasks.emitError({
      body: { message: "boom" },
      status: 500
    });
    getPaymentPromiseSummary.emitError({
      body: { message: "boom" },
      status: 500
    });
    getMyCollectionPlans.emitError({ body: { message: "boom" }, status: 500 });
    getCollectionsProgress.emitError({
      body: { message: "boom" },
      status: 500
    });
    getWorklist.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

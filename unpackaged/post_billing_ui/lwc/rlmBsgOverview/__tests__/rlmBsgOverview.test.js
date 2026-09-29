import RlmBsgOverview from "c/rlmBsgOverview";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getBillingScheduleGroupData from "@salesforce/apex/RLM_BSGTimelineController.getBillingScheduleGroupData";
import getConsolidatedTimeline from "@salesforce/apex/RLM_BSGTimelineController.getConsolidatedTimeline";

jest.mock(
  "@salesforce/apex/RLM_BSGTimelineController.getBillingScheduleGroupData",
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
  "@salesforce/apex/RLM_BSGTimelineController.getConsolidatedTimeline",
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

const TAG = "c-rlm-bsg-overview";

const mount = (props = {}) =>
  mountComponent(TAG, RlmBsgOverview, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-bsg-overview", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getBillingScheduleGroupData.emit([]);
    getConsolidatedTimeline.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getBillingScheduleGroupData.emitError({
      body: { message: "boom" },
      status: 500
    });
    getConsolidatedTimeline.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

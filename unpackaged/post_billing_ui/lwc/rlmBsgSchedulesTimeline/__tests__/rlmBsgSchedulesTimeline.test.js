import RlmBsgSchedulesTimeline from "c/rlmBsgSchedulesTimeline";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getBillingScheduleGroupData from "@salesforce/apex/RLM_BSGTimelineController.getBillingScheduleGroupData";

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

const TAG = "c-rlm-bsg-schedules-timeline";

const mount = (props = {}) =>
  mountComponent(TAG, RlmBsgSchedulesTimeline, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-bsg-schedules-timeline", () => {
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
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

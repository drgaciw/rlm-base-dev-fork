import RlmBillingCaseMetrics from "c/rlmBillingCaseMetrics";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getMetrics from "@salesforce/apex/RLM_BillingCaseMetricsController.getMetrics";

jest.mock(
  "@salesforce/apex/RLM_BillingCaseMetricsController.getMetrics",
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

const TAG = "c-rlm-billing-case-metrics";

const mount = (props = {}) =>
  mountComponent(TAG, RlmBillingCaseMetrics, { ...{}, ...props });

describe("c-rlm-billing-case-metrics", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getMetrics.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getMetrics.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

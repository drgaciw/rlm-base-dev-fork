import RlmExpressionSetManager from "c/rlmExpressionSetManager";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getContextDefinitions from "@salesforce/apex/RLM_ExpressionSetManagerController.getContextDefinitions";

jest.mock(
  "@salesforce/apex/RLM_ExpressionSetManagerController.getContextDefinitions",
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

const TAG = "c-rlm-expression-set-manager";

const mount = (props = {}) =>
  mountComponent(TAG, RlmExpressionSetManager, { ...{}, ...props });

describe("c-rlm-expression-set-manager", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getContextDefinitions.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getContextDefinitions.emitError({ body: { message: "boom" }, status: 500 });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

import RlmCollectionsConsole from "c/rlmCollectionsConsole";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getHighValueDelinquents from "@salesforce/apex/RLM_CollectionsConsoleController.getHighValueDelinquents";

jest.mock(
  "@salesforce/apex/RLM_CollectionsConsoleController.getHighValueDelinquents",
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

const TAG = "c-rlm-collections-console";

const mount = (props = {}) =>
  mountComponent(TAG, RlmCollectionsConsole, { ...{}, ...props });

describe("c-rlm-collections-console", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getHighValueDelinquents.emit([]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getHighValueDelinquents.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

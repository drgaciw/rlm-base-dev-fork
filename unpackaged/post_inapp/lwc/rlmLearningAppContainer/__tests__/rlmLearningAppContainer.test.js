import RlmLearningAppContainer from "c/rlmLearningAppContainer";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getSectionsWithBlocksByType from "@salesforce/apex/RLM_Learning_SectionBlockController.getSectionsWithBlocksByType";

jest.mock(
  "@salesforce/apex/RLM_Learning_SectionBlockController.getSectionsWithBlocksByType",
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

const TAG = "c-rlm-learning-app-container";

const mount = (props = {}) =>
  mountComponent(TAG, RlmLearningAppContainer, { ...{}, ...props });

describe("c-rlm-learning-app-container", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getSectionsWithBlocksByType.emit([
      { section: { Id: "a0", RLM_Learning_Header__c: "Container" }, blocks: [] }
    ]);
    await flushPromises();
    expect(el.shadowRoot.textContent).toContain("Container");
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getSectionsWithBlocksByType.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flushPromises();
    expect(el.shadowRoot.querySelector('[role="alert"]').textContent).toContain(
      "boom"
    );
  });
});

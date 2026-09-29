import RlmLearningAppOverview from "c/rlmLearningAppOverview";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import getSectionsWithBlocksByPageId from "@salesforce/apex/RLM_Learning_SectionBlockController.getSectionsWithBlocksByPageId";

jest.mock(
  "@salesforce/apex/RLM_Learning_SectionBlockController.getSectionsWithBlocksByPageId",
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

const TAG = "c-rlm-learning-app-overview";

const mount = (props = {}) =>
  mountComponent(TAG, RlmLearningAppOverview, {
    ...{ pageId: "a00000000000001AAA" },
    ...props
  });

describe("c-rlm-learning-app-overview", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getSectionsWithBlocksByPageId.emit([
      { section: { Id: "a0", RLM_Learning_Header__c: "Overview" }, blocks: [] }
    ]);
    await flushPromises();
    expect(el.shadowRoot.textContent).toContain("Overview");
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getSectionsWithBlocksByPageId.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flushPromises();
    expect(el.shadowRoot.querySelector('[role="alert"]').textContent).toContain(
      "boom"
    );
  });
});

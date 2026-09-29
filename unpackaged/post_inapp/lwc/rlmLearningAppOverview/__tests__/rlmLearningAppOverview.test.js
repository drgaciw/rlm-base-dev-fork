import { createElement } from "lwc";
import RlmLearningAppOverview from "c/rlmLearningAppOverview";
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

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningAppOverview });
  Object.assign(el, { pageId: "a00000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-app-overview", () => {
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
    getSectionsWithBlocksByPageId.emit([
      { section: { Id: "a0", RLM_Learning_Header__c: "Overview" }, blocks: [] }
    ]);
    await flush();
    expect(el.shadowRoot.textContent).toContain("Overview");
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getSectionsWithBlocksByPageId.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flush();
    expect(el.shadowRoot.querySelector('[role="alert"]').textContent).toContain(
      "boom"
    );
  });
});

import { createElement } from "lwc";
import RlmLearningReleaseNote from "c/rlmLearningReleaseNote";
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

const TAG = "c-rlm-learning-release-note";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningReleaseNote });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-release-note", () => {
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
    getSectionsWithBlocksByType.emit([
      {
        section: { Id: "a0", RLM_Learning_Header__c: "Release notes" },
        blocks: []
      }
    ]);
    await flush();
    expect(el.shadowRoot.textContent).toContain("Release notes");
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getSectionsWithBlocksByType.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flush();
    expect(el.shadowRoot.querySelector('[role="alert"]').textContent).toContain(
      "boom"
    );
  });
});

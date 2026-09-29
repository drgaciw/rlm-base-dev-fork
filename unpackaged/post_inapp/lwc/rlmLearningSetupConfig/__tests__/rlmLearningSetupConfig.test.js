import { createElement } from "lwc";
import RlmLearningSetupConfig from "c/rlmLearningSetupConfig";
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

jest.mock(
  "lightning/modal",
  () => {
    const { LightningElement } = jest.requireActual("lwc");
    class LightningModal extends LightningElement {}
    LightningModal.open = jest.fn(() => Promise.resolve());
    return { __esModule: true, default: LightningModal };
  },
  { virtual: true }
);

const TAG = "c-rlm-learning-setup-config";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningSetupConfig });
  Object.assign(el, { pageId: "a00000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-setup-config", () => {
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
    getSectionsWithBlocksByPageId.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getSectionsWithBlocksByPageId.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flush();
    expect(el.isConnected).toBe(true);
  });
});

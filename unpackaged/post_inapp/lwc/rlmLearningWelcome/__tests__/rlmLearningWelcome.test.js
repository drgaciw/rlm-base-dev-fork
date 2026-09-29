import { createElement } from "lwc";
import RlmLearningWelcome from "c/rlmLearningWelcome";
import getSectionsWithBlocksByType from "@salesforce/apex/RLM_Learning_SectionBlockController.getSectionsWithBlocksByType";
import getName from "@salesforce/apex/RLM_Learning_UserInformation.getName";
import getExpiryDays from "@salesforce/apex/RLM_Learning_UserInformation.getExpiryDays";

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

jest.mock(
  "@salesforce/apex/RLM_Learning_UserInformation.getName",
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
  "@salesforce/apex/RLM_Learning_UserInformation.getExpiryDays",
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

const TAG = "c-rlm-learning-welcome";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningWelcome });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-welcome", () => {
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
    getName.emit([]);
    getExpiryDays.emit([]);
    getSectionsWithBlocksByType.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getName.emitError({ body: { message: "boom" }, status: 500 });
    getExpiryDays.emitError({ body: { message: "boom" }, status: 500 });
    getSectionsWithBlocksByType.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

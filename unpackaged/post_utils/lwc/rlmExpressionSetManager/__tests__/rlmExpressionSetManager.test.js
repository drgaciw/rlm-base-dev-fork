import { createElement } from "lwc";
import RlmExpressionSetManager from "c/rlmExpressionSetManager";
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

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmExpressionSetManager });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-expression-set-manager", () => {
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
    getContextDefinitions.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getContextDefinitions.emitError({ body: { message: "boom" }, status: 500 });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

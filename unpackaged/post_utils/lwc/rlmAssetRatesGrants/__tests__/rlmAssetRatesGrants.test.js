import { createElement } from "lwc";
import RlmAssetRatesGrants from "c/rlmAssetRatesGrants";
import getRatesForAsset from "@salesforce/apex/RLM_UsageUploaderController.getRatesForAsset";
import getGrantsForAsset from "@salesforce/apex/RLM_UsageUploaderController.getGrantsForAsset";

jest.mock(
  "@salesforce/apex/RLM_UsageUploaderController.getRatesForAsset",
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
  "@salesforce/apex/RLM_UsageUploaderController.getGrantsForAsset",
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

const TAG = "c-rlm-asset-rates-grants";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmAssetRatesGrants });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-asset-rates-grants", () => {
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
    getRatesForAsset.emit([]);
    getGrantsForAsset.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getRatesForAsset.emitError({ body: { message: "boom" }, status: 500 });
    getGrantsForAsset.emitError({ body: { message: "boom" }, status: 500 });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

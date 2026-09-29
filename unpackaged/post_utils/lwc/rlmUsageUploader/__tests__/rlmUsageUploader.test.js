import { createElement } from "lwc";
import RlmUsageUploader from "c/rlmUsageUploader";
import getAssetsForAccount from "@salesforce/apex/RLM_UsageUploaderController.getAssetsForAccount";
import getUsageResourcesForAsset from "@salesforce/apex/RLM_UsageUploaderController.getUsageResourcesForAsset";

jest.mock(
  "@salesforce/apex/RLM_UsageUploaderController.getAssetsForAccount",
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
  "@salesforce/apex/RLM_UsageUploaderController.getUsageResourcesForAsset",
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

const TAG = "c-rlm-usage-uploader";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmUsageUploader });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-usage-uploader", () => {
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
    getAssetsForAccount.emit([]);
    getUsageResourcesForAsset.emit([]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    getAssetsForAccount.emitError({ body: { message: "boom" }, status: 500 });
    getUsageResourcesForAsset.emitError({
      body: { message: "boom" },
      status: 500
    });
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

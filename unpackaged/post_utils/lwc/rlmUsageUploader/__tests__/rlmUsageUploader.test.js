import RlmUsageUploader from "c/rlmUsageUploader";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
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

const mount = (props = {}) =>
  mountComponent(TAG, RlmUsageUploader, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-usage-uploader", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    getAssetsForAccount.emit([]);
    getUsageResourcesForAsset.emit([]);
    await flushPromises();
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
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

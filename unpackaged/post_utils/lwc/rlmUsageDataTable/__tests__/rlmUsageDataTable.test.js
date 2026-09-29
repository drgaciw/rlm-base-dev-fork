import RlmUsageDataTable from "c/rlmUsageDataTable";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-usage-data-table";

const mount = (props = {}) =>
  mountComponent(TAG, RlmUsageDataTable, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-usage-data-table", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

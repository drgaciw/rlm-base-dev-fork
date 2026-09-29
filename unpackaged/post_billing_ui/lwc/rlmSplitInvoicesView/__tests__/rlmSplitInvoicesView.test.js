import RlmSplitInvoicesView from "c/rlmSplitInvoicesView";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import { graphql } from "lightning/graphql";

const TAG = "c-rlm-split-invoices-view";

const mount = (props = {}) =>
  mountComponent(TAG, RlmSplitInvoicesView, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-split-invoices-view", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    graphql.emit({});
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    graphql.emitErrors([{ message: "boom" }]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.childElementCount).toBeGreaterThan(0);
  });
});

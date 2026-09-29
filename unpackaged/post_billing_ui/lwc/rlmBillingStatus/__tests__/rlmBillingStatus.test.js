import RlmBillingStatus from "c/rlmBillingStatus";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import { graphql } from "lightning/graphql";

const TAG = "c-rlm-billing-status";

const mount = (props = {}) =>
  mountComponent(TAG, RlmBillingStatus, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-billing-status", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });

  it("renders after every wire emits data", async () => {
    const el = mount();
    graphql.emit({
      uiapi: {
        query: {
          BillingAccount: {
            edges: [
              {
                node: {
                  Id: "0",
                  BillingSuspensionDate: { value: "2020-01-01" },
                  BillingResumptionDate: { value: "2999-01-01" }
                }
              }
            ]
          }
        }
      }
    });
    await flushPromises();
    expect(el.shadowRoot.querySelector(".pill-text").textContent).toBe(
      "Billing Suspended"
    );
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    graphql.emitErrors([{ message: "boom" }]);
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.querySelector(".status-pill")).toBeNull();
  });
});

import { createElement } from "lwc";
import RlmBillingStatus from "c/rlmBillingStatus";
import { graphql } from "lightning/graphql";

const TAG = "c-rlm-billing-status";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmBillingStatus });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-billing-status", () => {
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
    await flush();
    expect(el.shadowRoot.querySelector(".pill-text").textContent).toBe(
      "Billing Suspended"
    );
  });

  it("survives every wire reporting an error", async () => {
    const el = mount();
    graphql.emitErrors([{ message: "boom" }]);
    await flush();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot.querySelector(".status-pill")).toBeNull();
  });
});

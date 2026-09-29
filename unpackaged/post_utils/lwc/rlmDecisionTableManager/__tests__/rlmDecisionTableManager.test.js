import { createElement } from "lwc";
import RlmDecisionTableManager from "c/rlmDecisionTableManager";

const TAG = "c-rlm-decision-table-manager";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmDecisionTableManager });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-decision-table-manager", () => {
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
});

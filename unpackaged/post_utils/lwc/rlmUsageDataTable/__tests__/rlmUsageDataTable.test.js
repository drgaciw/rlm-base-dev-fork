import { createElement } from "lwc";
import RlmUsageDataTable from "c/rlmUsageDataTable";

const TAG = "c-rlm-usage-data-table";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmUsageDataTable });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-usage-data-table", () => {
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

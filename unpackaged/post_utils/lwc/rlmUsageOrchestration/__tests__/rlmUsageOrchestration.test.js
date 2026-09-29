import { createElement } from "lwc";
import RlmUsageOrchestration from "c/rlmUsageOrchestration";

const TAG = "c-rlm-usage-orchestration";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmUsageOrchestration });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-usage-orchestration", () => {
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

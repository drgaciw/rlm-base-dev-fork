import { createElement } from "lwc";
import RlmRebuildSearchIndex from "c/rlmRebuildSearchIndex";

const TAG = "c-rlm-rebuild-search-index";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmRebuildSearchIndex });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-rebuild-search-index", () => {
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

import { createElement } from "lwc";
import RlmSetUpQuoteHierarchyTree from "c/rlmSetUpQuoteHierarchyTree";

const TAG = "c-rlm-set-up-quote-hierarchy-tree";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmSetUpQuoteHierarchyTree });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-set-up-quote-hierarchy-tree", () => {
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

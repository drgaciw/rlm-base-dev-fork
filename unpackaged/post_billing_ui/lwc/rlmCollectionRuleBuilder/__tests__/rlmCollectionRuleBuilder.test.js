import { createElement } from "lwc";
import RlmCollectionRuleBuilder from "c/rlmCollectionRuleBuilder";

const TAG = "c-rlm-collection-rule-builder";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmCollectionRuleBuilder });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-collection-rule-builder", () => {
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

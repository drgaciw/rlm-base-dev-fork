import { createElement } from "lwc";
import RlmOrderRedirect from "c/rlmOrderRedirect";

const TAG = "c-rlm-order-redirect";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmOrderRedirect });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-order-redirect", () => {
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

import { createElement } from "lwc";
import RlmQuoteRedirect from "c/rlmQuoteRedirect";

const TAG = "c-rlm-quote-redirect";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmQuoteRedirect });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-quote-redirect", () => {
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

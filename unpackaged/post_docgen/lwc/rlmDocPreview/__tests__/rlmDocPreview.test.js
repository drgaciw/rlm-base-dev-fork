import { createElement } from "lwc";
import RlmDocPreview from "c/rlmDocPreview";

const TAG = "c-rlm-doc-preview";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmDocPreview });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-doc-preview", () => {
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

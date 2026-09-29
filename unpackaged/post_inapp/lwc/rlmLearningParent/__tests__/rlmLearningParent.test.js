import { createElement } from "lwc";
import RlmLearningParent from "c/rlmLearningParent";

const TAG = "c-rlm-learning-parent";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningParent });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-parent", () => {
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

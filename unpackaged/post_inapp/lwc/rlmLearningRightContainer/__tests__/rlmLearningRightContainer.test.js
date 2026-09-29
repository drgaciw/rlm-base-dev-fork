import { createElement } from "lwc";
import RlmLearningRightContainer from "c/rlmLearningRightContainer";

const TAG = "c-rlm-learning-right-container";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningRightContainer });
  Object.assign(el, {}, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-right-container", () => {
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

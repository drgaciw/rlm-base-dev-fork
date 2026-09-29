import { createElement } from "lwc";
import RlmLearningReorderableList from "c/rlmLearningReorderableList";

jest.mock(
  "lightning/actions",
  () => ({
    CloseActionScreenEvent: class CloseActionScreenEvent extends CustomEvent {
      constructor() {
        super("close");
      }
    }
  }),
  { virtual: true }
);

const TAG = "c-rlm-learning-reorderable-list";

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningReorderableList });
  Object.assign(el, { recordId: "001000000000001AAA" }, props);
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-reorderable-list", () => {
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

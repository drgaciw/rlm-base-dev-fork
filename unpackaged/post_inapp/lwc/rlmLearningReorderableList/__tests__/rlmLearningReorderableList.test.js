import RlmLearningReorderableList from "c/rlmLearningReorderableList";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

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

const mount = (props = {}) =>
  mountComponent(TAG, RlmLearningReorderableList, {
    ...{ recordId: "001000000000001AAA" },
    ...props
  });

describe("c-rlm-learning-reorderable-list", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

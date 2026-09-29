import RlmPreProcessOrderAction from "c/rlmPreProcessOrderAction";
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

const TAG = "c-rlm-pre-process-order-action";

const mount = (props = {}) =>
  mountComponent(TAG, RlmPreProcessOrderAction, { ...{}, ...props });

describe("c-rlm-pre-process-order-action", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

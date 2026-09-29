import RlmLearningSectionDetailModal from "c/rlmLearningSectionDetailModal";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

jest.mock(
  "lightning/modal",
  () => {
    const { LightningElement } = jest.requireActual("lwc");
    class LightningModal extends LightningElement {}
    LightningModal.open = jest.fn(() => Promise.resolve());
    return { __esModule: true, default: LightningModal };
  },
  { virtual: true }
);

const TAG = "c-rlm-learning-section-detail-modal";

const mount = (props = {}) =>
  mountComponent(TAG, RlmLearningSectionDetailModal, {
    ...{ header: "Header", subHeader: "Sub", description: "<p>Body</p>" },
    ...props
  });

describe("c-rlm-learning-section-detail-modal", () => {
  afterEach(clearDocument);

  it("renders without throwing", async () => {
    const el = mount();
    await flushPromises();
    expect(el.isConnected).toBe(true);
    expect(el.shadowRoot).not.toBeNull();
  });
});

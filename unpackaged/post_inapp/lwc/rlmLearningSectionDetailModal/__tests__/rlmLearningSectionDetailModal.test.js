import { createElement } from "lwc";
import RlmLearningSectionDetailModal from "c/rlmLearningSectionDetailModal";

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

function mount(props = {}) {
  const el = createElement(TAG, { is: RlmLearningSectionDetailModal });
  Object.assign(
    el,
    { header: "Header", subHeader: "Sub", description: "<p>Body</p>" },
    props
  );
  document.body.appendChild(el);
  return el;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("c-rlm-learning-section-detail-modal", () => {
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

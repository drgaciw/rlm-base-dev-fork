/* eslint-disable no-await-in-loop -- sequential awaits are intentional: each step must settle before the next */
// Shared harness for the rlmSetUpQuoteWizard behavioral suites. It lives in
// __mocks__ because jest.config.js ignores that folder for test discovery and
// coverage, and it is mostly mock registration. Import it BEFORE
// `c/rlmSetUpQuoteWizard` so the jest.mock calls below are in place when the
// component loads.
import RlmSetUpQuoteWizard from "c/rlmSetUpQuoteWizard";
import { mountComponent } from "@rlm/lwc-test-utils";
import runSetUpQuoteFromLWC from "@salesforce/apex/RLM_SetUpQuoteInvocable.runSetUpQuoteFromLWC";
import getSetUpQuoteStatus from "@salesforce/apex/RLM_SetUpQuoteInvocable.getSetUpQuoteStatus";
import getQuotesForModify from "@salesforce/apex/RLM_SetUpQuoteInvocable.getQuotesForModify";
import getQuoteHierarchy from "@salesforce/apex/RLM_SetUpQuoteInvocable.getQuoteHierarchy";
import detectQuoteProductSetMode from "@salesforce/apex/RLM_SetUpQuoteInvocable.detectQuoteProductSetMode";
import getRecentQuotesForRepeatBuy from "@salesforce/apex/RLM_SetUpQuoteInvocable.getRecentQuotesForRepeatBuy";
import getAccountsForRepeatBuy from "@salesforce/apex/RLM_SetUpQuoteInvocable.getAccountsForRepeatBuy";
import getRepeatBuyLines from "@salesforce/apex/RLM_SetUpQuoteInvocable.getRepeatBuyLines";
import getSetUpQuoteUiConfig from "@salesforce/apex/RLM_SetUpQuoteInvocable.getSetUpQuoteUiConfig";
import previewQuoteLineCounts from "@salesforce/apex/RLM_SetUpQuoteLinePreview.previewQuoteLineCounts";
import { __navigate } from "lightning/navigation";

// Every imperative Apex method the wizard imports becomes a bare jest.fn.
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.runSetUpQuoteFromLWC",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.getSetUpQuoteStatus",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.getQuotesForModify",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.getQuoteHierarchy",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.detectQuoteProductSetMode",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.getRecentQuotesForRepeatBuy",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.getAccountsForRepeatBuy",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.getRepeatBuyLines",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteInvocable.getSetUpQuoteUiConfig",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_SetUpQuoteLinePreview.previewQuoteLineCounts",
  () => ({ default: jest.fn() }),
  { virtual: true }
);

// The stock lightning/navigation stub's Navigate is a no-op; capture calls so
// tests can assert the page reference the wizard navigates to.
jest.mock(
  "lightning/navigation",
  () => {
    const Navigate = Symbol("Navigate");
    const mockNavigate = jest.fn();
    const NavigationMixin = (Base) =>
      class extends Base {
        [Navigate](...args) {
          mockNavigate(...args);
        }
      };
    NavigationMixin.Navigate = Navigate;
    return { NavigationMixin, __navigate: mockNavigate };
  },
  { virtual: true }
);

export const apex = {
  runSetUpQuoteFromLWC,
  getSetUpQuoteStatus,
  getQuotesForModify,
  getQuoteHierarchy,
  detectQuoteProductSetMode,
  getRecentQuotesForRepeatBuy,
  getAccountsForRepeatBuy,
  getRepeatBuyLines,
  getSetUpQuoteUiConfig,
  previewQuoteLineCounts
};
export const navigate = __navigate;

export const ACCOUNT_ID = "001000000000001AAA";
export const NEW_QUOTE_ID = "0Q0000000000001AAA";
export const PREVIEW = {
  currentTotal: 10,
  projectedTotal: 13,
  linesRemovedFromDeletes: 0,
  netExistingGroupDelta: 0,
  newLinesFromHierarchy: 3
};

// Call from beforeEach: fake timers plus fresh, successful Apex defaults.
export function resetWizardMocks() {
  jest.useFakeTimers();
  Object.values(apex).forEach((fn) => fn.mockReset());
  apex.getSetUpQuoteUiConfig.mockResolvedValue({
    showProductSetSelector: false,
    transactionTypes: []
  });
  apex.previewQuoteLineCounts.mockResolvedValue(PREVIEW);
  apex.runSetUpQuoteFromLWC.mockResolvedValue({
    quoteId: NEW_QUOTE_ID,
    success: true
  });
}

// Call from afterEach (after clearDocument).
export function restoreTimers() {
  jest.clearAllTimers();
  jest.useRealTimers();
}

// Lets awaited Apex promises settle and the component re-render. With fake
// timers, `ms` also fires the wizard's debounce / poll timers.
export const settle = async (ms = 0) => {
  await jest.advanceTimersByTimeAsync(ms);
  for (let i = 0; i < 50; i++) await Promise.resolve();
};

export const mountWizard = async (props = {}) => {
  const el = mountComponent("c-rlm-set-up-quote-wizard", RlmSetUpQuoteWizard, {
    recordId: ACCOUNT_ID,
    objectApiName: "Account",
    ...props
  });
  await settle();
  return el;
};

export const q = (el, selector) => el.shadowRoot.querySelector(selector);
export const qa = (el, selector) => [
  ...el.shadowRoot.querySelectorAll(selector)
];
export const text = (el) => el.shadowRoot.textContent.replace(/\s+/g, " ");
export const footerButton = (el, label) =>
  qa(el, "lightning-button").find((b) => b.label === label);
export const clickButton = async (el, label) => {
  footerButton(el, label).click();
  await settle();
};
export const clickSelector = async (el, selector) => {
  q(el, selector).click();
  await settle();
};
export const activeStepLabel = (el) =>
  q(el, ".step-dot-active")?.parentElement.querySelector(".step-label")
    .textContent;
export const change = async (target, value, extra = {}) => {
  if (value !== undefined) target.value = value;
  target.dispatchEvent(
    new CustomEvent("change", { detail: { value, ...extra } })
  );
  await settle();
};
export const setNumber = (el, selector, value) =>
  change(q(el, selector), String(value));
export const nameQuote = (el, name) =>
  change(q(el, 'lightning-input[data-step="quote-name"]'), name);
export const payloadSentToApex = (callIndex = 0) =>
  JSON.parse(apex.runSetUpQuoteFromLWC.mock.calls[callIndex][0].inputJson);

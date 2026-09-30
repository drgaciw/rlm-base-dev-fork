/* eslint-disable no-await-in-loop -- sequential awaits are intentional: each step must settle before the next */
/* eslint-disable jest/no-mocks-import -- the shared harness lives in __mocks__ so jest ignores it for test discovery */
import {
  ACCOUNT_ID,
  NEW_QUOTE_ID,
  activeStepLabel,
  apex,
  clickButton,
  clickSelector,
  footerButton,
  mountWizard,
  nameQuote,
  navigate,
  payloadSentToApex,
  q,
  qa,
  resetWizardMocks,
  restoreTimers,
  setNumber,
  settle,
  text
} from "../__mocks__/wizardHarness";
import { clearDocument } from "@rlm/lwc-test-utils";

beforeEach(resetWizardMocks);
afterEach(() => {
  clearDocument();
  restoreTimers();
});

describe("c-rlm-set-up-quote-wizard: initial render and config", () => {
  it("opens on the Create or Modify step with the seven-step indicator", async () => {
    const el = await mountWizard();

    expect(apex.getSetUpQuoteUiConfig).toHaveBeenCalledTimes(1);
    expect(text(el)).toContain("Create a new quote");
    expect(text(el)).toContain("Modify an existing quote");
    expect(activeStepLabel(el)).toBe("Create/Modify");
    expect(qa(el, ".step-indicator-item")).toHaveLength(7);
    expect(footerButton(el, "Cancel")).toBeTruthy();
    expect(footerButton(el, "Back")).toBeUndefined();
  });

  it("shows the pricing selector when Apex config supplies transaction types", async () => {
    apex.getSetUpQuoteUiConfig.mockResolvedValue(
      JSON.stringify({
        showProductSetSelector: true,
        defaultTransactionType: "Standard",
        transactionTypes: [
          { label: "Standard", value: "Standard" },
          { label: "Tax free", value: "TaxFree" }
        ]
      })
    );
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');

    const selector = q(el, 'lightning-combobox[data-step="transaction-type"]');
    expect(selector).not.toBeNull();
    expect(selector.value).toBe("Standard");
    expect(selector.options).toHaveLength(2);
    expect(
      qa(el, "lightning-radio-group").find((r) => r.label === "Product set")
    ).toBeTruthy();
  });

  it("falls back to the first type when the configured default is unknown, then honours a user change", async () => {
    apex.getSetUpQuoteUiConfig.mockResolvedValue({
      defaultTransactionType: "Gone",
      transactionTypes: [
        { label: "Standard", value: "Standard" },
        { label: "Tax free", value: "TaxFree" }
      ]
    });
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');

    const selector = q(el, 'lightning-combobox[data-step="transaction-type"]');
    expect(selector.value).toBe("Standard");
    selector.dispatchEvent(
      new CustomEvent("change", { detail: { value: "TaxFree" } })
    );
    await settle();
    expect(selector.value).toBe("TaxFree");
  });

  it("hides the pricing selector and logs when the config call fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    apex.getSetUpQuoteUiConfig.mockRejectedValue({
      body: { message: "denied" }
    });
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');

    expect(
      q(el, 'lightning-combobox[data-step="transaction-type"]')
    ).toBeNull();
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining("getSetUpQuoteUiConfig failed"),
      expect.anything()
    );
    errorSpy.mockRestore();
  });
});

describe("c-rlm-set-up-quote-wizard: navigation events", () => {
  it("Cancel and the close icon navigate to the Quote list page", async () => {
    const el = await mountWizard();

    await clickButton(el, "Cancel");
    expect(navigate).toHaveBeenLastCalledWith({
      type: "standard__objectPage",
      attributes: { objectApiName: "Quote", actionName: "list" }
    });

    await clickSelector(el, "lightning-button-icon.close-btn");
    expect(navigate).toHaveBeenCalledTimes(2);
  });

  it("Back returns from the quote step to Create/Modify", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    expect(activeStepLabel(el)).toBe("Quote");

    await clickButton(el, "Back");
    expect(activeStepLabel(el)).toBe("Create/Modify");
  });
});

describe("c-rlm-set-up-quote-wizard: create from scratch", () => {
  it("blocks Next on the quote step until a name is entered", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    const nameInput = q(el, 'lightning-input[data-step="quote-name"]');
    const validity = jest.spyOn(nameInput, "setCustomValidity");

    await clickButton(el, "Next");

    expect(validity).toHaveBeenCalledWith("New quote name is required.");
    expect(activeStepLabel(el)).toBe("Quote");
  });

  it("runs the full wizard, sends the built payload and navigates to the new quote on Done", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "  Big Deal  ");
    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Hierarchy");

    // No groups added: the wizard skips straight to the ungrouped count input.
    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Product counts");
    expect(text(el)).toContain("No groups were added");
    await setNumber(
      el,
      'lightning-input[data-step="ungrouped-product-count"]',
      25
    );

    // Preview is debounced by 320 ms and rendered once Apex resolves.
    expect(text(el)).toContain("Calculating quote line estimate");
    await settle(400);
    expect(apex.previewQuoteLineCounts).toHaveBeenCalled();
    expect(text(el)).toContain("Estimated total after Run:");

    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Large Deal");
    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Confirm");
    expect(text(el)).toContain("Create from scratch");
    expect(text(el)).toContain("Big Deal");
    expect(text(el)).toContain("25 ungrouped product(s)");

    await clickButton(el, "Run");
    expect(apex.runSetUpQuoteFromLWC).toHaveBeenCalledTimes(1);
    const payload = payloadSentToApex();
    expect(payload).toMatchObject({
      isCreate: true,
      quoteId: null,
      newQuoteName: "Big Deal",
      largeDeal: false,
      ungroupedProductCount: 25,
      productSetMode: "QUANTUMBIT",
      quoteAccountId: ACCOUNT_ID,
      groupsToDeleteJson: null,
      repeatBuyAssignmentsJson: null
    });

    expect(activeStepLabel(el)).toBe("Result");
    expect(text(el)).toContain(`Quote Id: ${NEW_QUOTE_ID}`);

    await clickButton(el, "Done");
    expect(navigate).toHaveBeenLastCalledWith({
      type: "standard__recordPage",
      attributes: {
        recordId: NEW_QUOTE_ID,
        objectApiName: "Quote",
        actionName: "view"
      }
    });
    // Reset back to the first step for the next run.
    expect(text(el)).toContain("Create a new quote");
  });

  it("shows the Apex error on the Result step and offers Done to the quote list", async () => {
    apex.runSetUpQuoteFromLWC.mockRejectedValue({
      body: { message: "Insufficient access" }
    });
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "Doomed");
    await clickButton(el, "Next");
    await clickButton(el, "Next");
    await clickButton(el, "Next");
    await clickButton(el, "Next");
    await clickButton(el, "Run");

    expect(activeStepLabel(el)).toBe("Result");
    expect(text(el)).toContain("Failed");
    expect(text(el)).toContain("Insufficient access");

    await clickButton(el, "Done");
    expect(navigate).toHaveBeenLastCalledWith({
      type: "standard__objectPage",
      attributes: { objectApiName: "Quote", actionName: "list" }
    });
  });

  it("reports a failed result returned by Apex without navigating to a record", async () => {
    apex.runSetUpQuoteFromLWC.mockResolvedValue(
      JSON.stringify({ success: false, errorMessage: "Duplicate quote name" })
    );
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "Dup");
    for (let i = 0; i < 4; i++) await clickButton(el, "Next");
    await clickButton(el, "Run");

    expect(text(el)).toContain("Duplicate quote name");
  });

  it("forces the Large Deal box when the projected line count reaches 500", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "Huge");
    await clickButton(el, "Next");
    await clickButton(el, "Next");
    await setNumber(
      el,
      'lightning-input[data-step="ungrouped-product-count"]',
      750
    );
    await clickButton(el, "Next");

    expect(activeStepLabel(el)).toBe("Large Deal");
    const box = q(el, 'lightning-input[data-step="large-deal"]');
    expect(box.checked).toBe(true);
    expect(box.disabled).toBe(true);
    expect(text(el)).toContain("Large Deal is required at 500+ lines");

    await clickButton(el, "Next");
    expect(text(el)).toContain("Yes");
  });
});

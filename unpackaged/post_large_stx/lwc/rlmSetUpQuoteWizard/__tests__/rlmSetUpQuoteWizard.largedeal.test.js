/* eslint-disable jest/no-mocks-import -- the shared harness lives in __mocks__ so jest ignores it for test discovery */
import {
  NEW_QUOTE_ID,
  activeStepLabel,
  apex,
  change,
  clickButton,
  clickSelector,
  footerButton,
  mountWizard,
  nameQuote,
  payloadSentToApex,
  q,
  qa,
  resetWizardMocks,
  restoreTimers,
  settle,
  text
} from "../__mocks__/wizardHarness";
import { clearDocument } from "@rlm/lwc-test-utils";

const CSV = [
  "Group 1,Group 2,Group 3,Group 4,Group 5,Bundle Product,Product,Quantity",
  "Alpha,Beta,,,,,QB-X,2",
  "Gamma,,,,,,QB-Y,"
].join("\n");

const READY = {
  success: true,
  qliCount: 0,
  groupCount: 0,
  pendingAsyncCount: 0,
  calculationStatus: "Completed"
};

const bind = (extra = {}) => ({ ...READY, ...extra });

// Create -> name -> Next -> Next (no groups) -> ungrouped count -> Next
// (Large Deal step) so a test can tick the box or go straight to Run.
const reachLargeDealStep = async (count) => {
  const el = await mountWizard();
  await clickSelector(el, 'button[data-choice="create"]');
  await nameQuote(el, "Deal");
  await clickButton(el, "Next");
  await clickButton(el, "Next");
  await change(
    q(el, 'lightning-input[data-step="ungrouped-product-count"]'),
    String(count)
  );
  await clickButton(el, "Next");
  return el;
};

// CSV create -> Large Deal step, with the "Large Deal" box ticked.
const reachCsvLargeDeal = async () => {
  const el = await mountWizard();
  await clickSelector(el, 'button[data-choice="create"]');
  await nameQuote(el, "CSV Deal");
  await clickSelector(el, 'button[data-mode="CSV"]');
  await settle(400);
  await clickButton(el, "Next");
  const input = q(el, 'input[type="file"]');
  Object.defineProperty(input, "files", {
    value: [new File([CSV], "deal.csv")],
    configurable: true
  });
  input.dispatchEvent(new CustomEvent("change"));
  await settle(50);
  await settle(50);
  await clickButton(el, "Next");
  const box = q(el, 'lightning-input[data-step="large-deal"]');
  box.checked = true;
  await clickButton(el, "Next");
  return el;
};

const run = async (el) => {
  footerButton(el, "Run").click();
  await settle();
};
const resultText = (el) => text(el);

beforeEach(resetWizardMocks);
afterEach(() => {
  clearDocument();
  restoreTimers();
});

describe("c-rlm-set-up-quote-wizard: large deal - create in two steps (CSV)", () => {
  it("creates an empty quote, waits for hydration, adds the CSV content and polls until lines persist", async () => {
    apex.runSetUpQuoteFromLWC
      .mockResolvedValueOnce({ success: true, quoteId: NEW_QUOTE_ID })
      .mockResolvedValueOnce({ success: true, quoteId: NEW_QUOTE_ID });
    apex.getSetUpQuoteStatus
      // hydration wait after step 1: nothing expected yet
      .mockResolvedValueOnce(bind())
      // persistence wait after step 2: three groups (Alpha, Beta, Gamma) and
      // two lines expected
      .mockResolvedValueOnce(
        bind({ groupCount: 1, qliCount: 1, pendingAsyncCount: 2 })
      )
      .mockResolvedValueOnce(bind({ groupCount: 3, qliCount: 2 }));
    const el = await reachCsvLargeDeal();
    expect(text(el)).toContain("Yes");

    await run(el);
    expect(text(el)).toContain(
      "Waiting for Large Deal lines to persist (1/3 groups, 1/2 lines, 2 async pending)"
    );

    await settle(3000);
    expect(activeStepLabel(el)).toBe("Result");
    expect(resultText(el)).toContain(
      "Large Deal two-step setup completed: 3 group(s), 2 line item(s)."
    );
    expect(resultText(el)).not.toContain("Note: created");

    const [first, second] = [payloadSentToApex(0), payloadSentToApex(1)];
    expect(first).toMatchObject({
      isCreate: true,
      largeDeal: true,
      hierarchyJson: '{"parents":[]}',
      csvImportLineItemsJson: null
    });
    expect(second).toMatchObject({
      isCreate: false,
      quoteId: NEW_QUOTE_ID,
      newQuoteName: null,
      largeDeal: true
    });
    expect(JSON.parse(second.csvImportLineItemsJson)).toHaveLength(2);
  }, 15000);

  it("finishes with a note when the quote settles below the estimate", async () => {
    apex.runSetUpQuoteFromLWC.mockResolvedValue({
      success: true,
      quoteId: NEW_QUOTE_ID
    });
    apex.getSetUpQuoteStatus
      .mockResolvedValueOnce(bind())
      .mockResolvedValue(bind({ groupCount: 3, qliCount: 1 }));
    const el = await reachCsvLargeDeal();

    await run(el);
    // Poll 1 sets the baseline; polls 2-4 are "stable", which settles.
    await settle(9000);

    expect(resultText(el)).toContain(
      "Note: created 1 of ~2 estimated line item(s)"
    );
  }, 15000);

  it("returns the failure when creating the empty quote fails", async () => {
    apex.runSetUpQuoteFromLWC.mockResolvedValueOnce({
      success: false,
      errorMessage: "Name already used"
    });
    const el = await reachCsvLargeDeal();

    await run(el);

    expect(apex.runSetUpQuoteFromLWC).toHaveBeenCalledTimes(1);
    expect(apex.getSetUpQuoteStatus).not.toHaveBeenCalled();
    expect(resultText(el)).toContain("Name already used");
  }, 15000);

  it("returns the failure when adding lines to the new quote fails", async () => {
    apex.runSetUpQuoteFromLWC
      .mockResolvedValueOnce({ success: true, quoteId: NEW_QUOTE_ID })
      .mockResolvedValueOnce({
        success: false,
        errorMessage: "Line creation failed upstream"
      });
    apex.getSetUpQuoteStatus.mockResolvedValue(bind());
    const el = await reachCsvLargeDeal();

    await run(el);

    expect(resultText(el)).toContain("Line creation failed upstream");
  }, 15000);

  it("reports async failures found while polling instead of waiting forever", async () => {
    apex.runSetUpQuoteFromLWC.mockResolvedValue({
      success: true,
      quoteId: NEW_QUOTE_ID
    });
    apex.getSetUpQuoteStatus
      .mockResolvedValueOnce(bind())
      .mockResolvedValue(bind({ failedAsyncCount: 1 }));
    const el = await reachCsvLargeDeal();

    await run(el);

    expect(activeStepLabel(el)).toBe("Result");
    expect(resultText(el)).toContain(
      `Large Deal processing failed. Quote ${NEW_QUOTE_ID} has failed async work`
    );
  }, 15000);

  it("surfaces the status call's own error message when it reports failure", async () => {
    apex.runSetUpQuoteFromLWC.mockResolvedValue({
      success: true,
      quoteId: NEW_QUOTE_ID
    });
    apex.getSetUpQuoteStatus.mockResolvedValue(
      JSON.stringify({ success: false, errorMessage: "Status unavailable" })
    );
    const el = await reachCsvLargeDeal();

    await run(el);

    expect(resultText(el)).toContain("Status unavailable");
  }, 15000);

  it("times out after 50 polls and includes the last status", async () => {
    apex.runSetUpQuoteFromLWC.mockResolvedValue({
      success: true,
      quoteId: NEW_QUOTE_ID
    });
    apex.getSetUpQuoteStatus
      .mockResolvedValueOnce(bind())
      .mockResolvedValue(
        bind({ pendingAsyncCount: 1, qliCount: 1, groupCount: 1 })
      );
    const el = await reachCsvLargeDeal();

    await run(el);
    await settle(50 * 3000 + 1000);

    expect(activeStepLabel(el)).toBe("Result");
    expect(resultText(el)).toContain(
      "Timed out waiting for Large Deal processing. Last status:"
    );
    expect(resultText(el)).toContain('"pendingAsyncCount":1');
  }, 15000);
});

describe("c-rlm-set-up-quote-wizard: large deal - batched line creation", () => {
  it("creates an empty quote then splits 2,500 ungrouped lines into 500-line batches", async () => {
    apex.runSetUpQuoteFromLWC.mockResolvedValue({
      success: true,
      quoteId: NEW_QUOTE_ID
    });
    // Lines on the quote grow by 500 with every batch call after the first
    // (empty) creation call.
    apex.getSetUpQuoteStatus.mockImplementation(async () => {
      const batchesDone = Math.max(
        apex.runSetUpQuoteFromLWC.mock.calls.length - 1,
        0
      );
      return bind({ qliCount: batchesDone * 500 });
    });
    const el = await reachLargeDealStep(2500);
    expect(q(el, 'lightning-input[data-step="large-deal"]').disabled).toBe(
      true
    );
    await clickButton(el, "Next");

    await run(el);

    // 1 create + 5 batches of 500.
    expect(apex.runSetUpQuoteFromLWC).toHaveBeenCalledTimes(6);
    expect(payloadSentToApex(0)).toMatchObject({
      isCreate: true,
      hierarchyJson: '{"parents":[]}',
      ungroupedProductCount: 0
    });
    const batches = [1, 2, 3, 4, 5].map((i) => payloadSentToApex(i));
    expect(batches.map((b) => b.ungroupedProductCount)).toEqual([
      500, 500, 500, 500, 500
    ]);
    batches.forEach((b) => {
      expect(b).toMatchObject({
        isCreate: false,
        quoteId: NEW_QUOTE_ID,
        productCountsJson: "{}"
      });
    });
    expect(resultText(el)).toContain(
      "Large Deal batched setup completed: 2500 line item(s)."
    );
  }, 15000);

  it("stops at the first failing batch and returns its error", async () => {
    apex.runSetUpQuoteFromLWC
      .mockResolvedValueOnce({ success: true, quoteId: NEW_QUOTE_ID })
      .mockResolvedValueOnce({ success: true, quoteId: NEW_QUOTE_ID })
      .mockResolvedValueOnce({
        success: false,
        errorMessage: "Batch limit exceeded"
      });
    apex.getSetUpQuoteStatus.mockImplementation(async () => {
      const done = Math.max(apex.runSetUpQuoteFromLWC.mock.calls.length - 1, 0);
      return bind({ qliCount: done * 500 });
    });
    const el = await reachLargeDealStep(2500);
    await clickButton(el, "Next");

    await run(el);

    expect(apex.runSetUpQuoteFromLWC).toHaveBeenCalledTimes(3);
    expect(resultText(el)).toContain("Batch limit exceeded");
  }, 15000);
});

describe("c-rlm-set-up-quote-wizard: large deal - modify a quote that is already a Large Deal", () => {
  it("batches large per-group counts and reports the batched result", async () => {
    apex.getQuotesForModify.mockResolvedValue([
      { value: "0QLD", label: "Large", isLargeDeal: "true" }
    ]);
    apex.getQuoteHierarchy.mockResolvedValue({
      parents: [{ id: "0QG1", name: "Root", lineItemCount: 10, children: [] }]
    });
    // 10 lines on the quote to begin with, +500 and +300 per batch.
    apex.getSetUpQuoteStatus.mockImplementation(async () => {
      const runs = apex.runSetUpQuoteFromLWC.mock.calls.length;
      return bind({ qliCount: [10, 510, 810][runs] });
    });
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="modify"]');
    await change(q(el, 'lightning-combobox[data-step="quote-id"]'), "0QLD");
    await clickButton(el, "Next");
    await clickButton(el, "Next");
    const counts = q(
      el,
      'c-rlm-set-up-quote-hierarchy-tree[data-step="product-counts-existing"]'
    );
    await change(qa(counts, "lightning-input.tree-count-input")[0], "800");
    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Confirm");
    expect(text(el)).toContain("Yes (already set on quote)");

    await run(el);

    expect(apex.runSetUpQuoteFromLWC).toHaveBeenCalledTimes(2);
    expect(apex.getSetUpQuoteStatus.mock.calls[0][0]).toEqual({
      quoteId: "0QLD"
    });
    const batchCounts = [0, 1].map((i) =>
      JSON.parse(payloadSentToApex(i).existingGroupCountsJson)
    );
    expect(batchCounts).toEqual([{ "0QG1": 500 }, { "0QG1": 300 }]);
    expect(resultText(el)).toContain(
      "Large Deal batched setup completed: 800 line item(s)."
    );
  }, 15000);
});

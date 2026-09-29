/* eslint-disable no-await-in-loop -- sequential awaits are intentional: each step must settle before the next */
/* eslint-disable jest/no-mocks-import -- the shared harness lives in __mocks__ so jest ignores it for test discovery */
import {
  NEW_QUOTE_ID,
  activeStepLabel,
  apex,
  change,
  clickButton,
  clickSelector,
  mountWizard,
  navigate,
  payloadSentToApex,
  q,
  qa,
  resetWizardMocks,
  restoreTimers,
  settle,
  text
} from "../__mocks__/wizardHarness";
import { clearDocument } from "@rlm/lwc-test-utils";

const ROOT_ID = "0QG000000000001AAA";
const CHILD_ID = "0QG000000000002AAA";
const QUOTE_ID = "0Q0000000000010AAA";
const LARGE_DEAL_QUOTE_ID = "0Q0000000000020AAA";

const HIERARCHY = {
  parents: [
    {
      id: ROOT_ID,
      name: "Root",
      lineItemCount: 3,
      children: [
        { id: CHILD_ID, name: "Child", lineItemCount: 1, children: [] }
      ]
    }
  ]
};

const QUOTE_OPTIONS = [
  { value: QUOTE_ID, label: "Q-0010", isLargeDeal: "false" },
  {
    value: LARGE_DEAL_QUOTE_ID,
    label: "Q-0020 (Large Deal)",
    isLargeDeal: "true"
  }
];

const existingTree = (el) =>
  q(
    el,
    'c-rlm-set-up-quote-hierarchy-tree[data-step="existing-hierarchy-tree"]'
  );
const treeLabels = (tree) =>
  qa(tree, ".tree-label").map((n) => n.textContent.trim());
const quoteCombobox = (el) => q(el, 'lightning-combobox[data-step="quote-id"]');

// Create -> Modify -> pick a quote -> Next, landing on the hierarchy step.
const openHierarchyFor = async (quoteId, hierarchy = HIERARCHY) => {
  apex.getQuotesForModify.mockResolvedValue(QUOTE_OPTIONS);
  apex.getQuoteHierarchy.mockResolvedValue(hierarchy);
  const el = await mountWizard();
  await clickSelector(el, 'button[data-choice="modify"]');
  await change(quoteCombobox(el), quoteId);
  await clickButton(el, "Next");
  return el;
};

beforeEach(resetWizardMocks);
afterEach(() => {
  clearDocument();
  restoreTimers();
});

describe("c-rlm-set-up-quote-wizard: modify - choosing a quote", () => {
  it("loads the quotes into the combobox behind a placeholder option", async () => {
    apex.getQuotesForModify.mockResolvedValue(QUOTE_OPTIONS);
    const el = await mountWizard();

    await clickSelector(el, 'button[data-choice="modify"]');

    expect(apex.getQuotesForModify).toHaveBeenCalledTimes(1);
    expect(activeStepLabel(el)).toBe("Quote");
    expect(quoteCombobox(el).options).toEqual([
      { label: "-- Select a quote --", value: "" },
      { label: "Q-0010", value: QUOTE_ID },
      { label: "Q-0020 (Large Deal)", value: LARGE_DEAL_QUOTE_ID }
    ]);
  });

  it("shows only the placeholder when the org has no quotes", async () => {
    apex.getQuotesForModify.mockResolvedValue([]);
    const el = await mountWizard();

    await clickSelector(el, 'button[data-choice="modify"]');

    expect(quoteCombobox(el).options).toHaveLength(1);
  });

  it("shows only the placeholder and logs when loading quotes fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    apex.getQuotesForModify.mockRejectedValue(new Error("no access"));
    const el = await mountWizard();

    await clickSelector(el, 'button[data-choice="modify"]');

    expect(quoteCombobox(el).options).toHaveLength(1);
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining("getQuotesForModify failed"),
      expect.any(Error)
    );
    errorSpy.mockRestore();
  });

  it("shows a spinner while quotes load, then the combobox", async () => {
    let release;
    apex.getQuotesForModify.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      })
    );
    const el = await mountWizard();

    await clickSelector(el, 'button[data-choice="modify"]');
    expect(text(el)).toContain("Loading quotes");
    expect(quoteCombobox(el)).toBeNull();

    release(QUOTE_OPTIONS);
    await settle();
    expect(text(el)).not.toContain("Loading quotes");
    expect(quoteCombobox(el)).not.toBeNull();
  });

  it("stays on the quote step until a quote is chosen", async () => {
    apex.getQuotesForModify.mockResolvedValue(QUOTE_OPTIONS);
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="modify"]');

    await clickButton(el, "Next");

    expect(activeStepLabel(el)).toBe("Quote");
    expect(apex.getQuoteHierarchy).not.toHaveBeenCalled();
  });

  it("detects the product set of the selected quote and lets the user override it", async () => {
    apex.getSetUpQuoteUiConfig.mockResolvedValue({
      showProductSetSelector: true,
      transactionTypes: []
    });
    apex.getQuotesForModify.mockResolvedValue(QUOTE_OPTIONS);
    apex.detectQuoteProductSetMode.mockResolvedValue("SIEMENS");
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="modify"]');

    await change(quoteCombobox(el), QUOTE_ID);

    expect(apex.detectQuoteProductSetMode).toHaveBeenCalledWith({
      quoteId: QUOTE_ID
    });
    const radio = qa(el, "lightning-radio-group").find(
      (r) => r.label === "Product set"
    );
    expect(radio.value).toBe("SIEMENS");

    await change(radio, "QUANTUMBIT");
    expect(radio.value).toBe("QUANTUMBIT");
  });

  it("falls back to QuantumBit when product-set detection fails or the quote is cleared", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    apex.getSetUpQuoteUiConfig.mockResolvedValue({
      showProductSetSelector: true,
      transactionTypes: []
    });
    apex.getQuotesForModify.mockResolvedValue(QUOTE_OPTIONS);
    apex.detectQuoteProductSetMode.mockRejectedValue(new Error("nope"));
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="modify"]');

    await change(quoteCombobox(el), QUOTE_ID);
    const radio = qa(el, "lightning-radio-group").find(
      (r) => r.label === "Product set"
    );
    expect(radio.value).toBe("QUANTUMBIT");
    expect(errorSpy).toHaveBeenCalled();

    apex.detectQuoteProductSetMode.mockClear();
    await change(quoteCombobox(el), "");
    expect(apex.detectQuoteProductSetMode).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});

describe("c-rlm-set-up-quote-wizard: modify - hierarchy step", () => {
  it("loads the existing groups for the selected quote into the tree", async () => {
    const el = await openHierarchyFor(QUOTE_ID);

    expect(apex.getQuoteHierarchy).toHaveBeenCalledWith({ quoteId: QUOTE_ID });
    expect(activeStepLabel(el)).toBe("Hierarchy");
    expect(treeLabels(existingTree(el))).toEqual([
      "Root  3 line item(s)",
      "Child  1 line item(s)"
    ]);
  });

  it("accepts the hierarchy as a JSON string", async () => {
    const el = await openHierarchyFor(QUOTE_ID, JSON.stringify(HIERARCHY));

    expect(treeLabels(existingTree(el))).toHaveLength(2);
  });

  it("explains that there are no groups when the quote has none", async () => {
    const el = await openHierarchyFor(QUOTE_ID, { parents: [] });

    expect(existingTree(el)).toBeNull();
    expect(text(el)).toContain(
      "No existing groups, or all have been marked for deletion."
    );
  });

  it("treats a failed hierarchy load as an empty quote and still advances", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    apex.getQuotesForModify.mockResolvedValue(QUOTE_OPTIONS);
    apex.getQuoteHierarchy.mockRejectedValue(new Error("boom"));
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="modify"]');
    await change(quoteCombobox(el), QUOTE_ID);

    await clickButton(el, "Next");

    expect(activeStepLabel(el)).toBe("Hierarchy");
    expect(existingTree(el)).toBeNull();
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining("getQuoteHierarchy failed"),
      expect.any(Error)
    );
    errorSpy.mockRestore();
  });

  it("hides a group and its subgroups after the tree reports a delete", async () => {
    const el = await openHierarchyFor(QUOTE_ID);
    const tree = existingTree(el);

    // Rows: Root (0) and Child (0-0); delete the child first.
    qa(tree, "lightning-button-icon.tree-delete-btn")[1].click();
    await settle();
    expect(treeLabels(existingTree(el))).toEqual(["Root  3 line item(s)"]);

    qa(existingTree(el), "lightning-button-icon.tree-delete-btn")[0].click();
    await settle();
    expect(existingTree(el)).toBeNull();
    expect(text(el)).toContain(
      "No existing groups, or all have been marked for deletion."
    );
  });

  it("switches between the existing / manual / CSV rails and gates Next on the CSV rail", async () => {
    const el = await openHierarchyFor(QUOTE_ID);
    const rail = (name) => q(el, `button[data-rail="${name}"]`);
    const nextDisabled = () =>
      qa(el, "lightning-button").find((b) => b.label === "Next").disabled;

    expect(rail("existing").getAttribute("aria-current")).toBe("page");
    expect(nextDisabled()).toBe(false);

    rail("manual").click();
    await settle();
    expect(rail("manual").getAttribute("aria-current")).toBe("page");
    expect(rail("existing").getAttribute("aria-current")).toBeNull();

    rail("csv").click();
    await settle();
    expect(rail("csv").getAttribute("aria-current")).toBe("page");
    expect(nextDisabled()).toBe(true);
  });
});

describe("c-rlm-set-up-quote-wizard: modify - full run", () => {
  it("carries deletes, renames, new subgroups and counts into the Apex payload", async () => {
    const el = await openHierarchyFor(QUOTE_ID);

    // Rename Root via the tree's own double-click editor.
    const treeEl = existingTree(el);
    q(treeEl, '.tree-label[data-path="0"]').dispatchEvent(
      new CustomEvent("dblclick", { bubbles: true })
    );
    await settle();
    const draft = q(treeEl, "lightning-input.tree-rename-input");
    draft.value = "Root Renamed";
    draft.dispatchEvent(new CustomEvent("change"));
    draft.dispatchEvent(new CustomEvent("blur"));
    await settle();

    // Add a pending subgroup under Root, then delete the existing Child.
    q(
      existingTree(el),
      'lightning-input.child-name[data-parent-path="0"]'
    ).value = "Brand New";
    qa(existingTree(el), "lightning-button")
      .find((b) => b.label === "Add" && b.dataset.parentPath === "0")
      .click();
    await settle();
    const deleteButtons = qa(
      existingTree(el),
      "lightning-button-icon.tree-delete-btn"
    );
    // Rows: Root, Child, Brand New (pending, depth 1). Delete Child.
    deleteButtons[1].click();
    await settle();

    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Product counts");

    // Enter a count for the existing Root group in the counts tree.
    const counts = q(
      el,
      'c-rlm-set-up-quote-hierarchy-tree[data-step="product-counts-existing"]'
    );
    const rootCount = qa(counts, "lightning-input.tree-count-input")[0];
    await change(rootCount, "7");
    await settle(400);
    expect(apex.previewQuoteLineCounts).toHaveBeenCalled();
    const preview = JSON.parse(
      apex.previewQuoteLineCounts.mock.calls.at(-1)[0].previewJson
    );
    expect(preview).toMatchObject({
      isCreate: false,
      quoteId: QUOTE_ID,
      groupsToDeleteJson: JSON.stringify([CHILD_ID])
    });

    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Large Deal");
    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Confirm");
    expect(text(el)).toContain("Modify");
    expect(text(el)).toContain("1 group(s) and their line items");
    expect(text(el)).toContain("1 group(s)");
    expect(text(el)).toContain("1 new subgroup(s)");

    await clickButton(el, "Run");

    const payload = payloadSentToApex();
    expect(payload).toMatchObject({
      isCreate: false,
      quoteId: QUOTE_ID,
      newQuoteName: null,
      quoteAccountId: null,
      groupsToDeleteJson: JSON.stringify([CHILD_ID]),
      groupRenamesJson: JSON.stringify({ [ROOT_ID]: "Root Renamed" })
    });
    expect(JSON.parse(payload.existingGroupCountsJson)).toEqual({
      [ROOT_ID]: 7
    });
    expect(JSON.parse(payload.newSubgroupsJson)).toEqual([
      expect.objectContaining({ parentGroupId: ROOT_ID, name: "Brand New" })
    ]);

    await clickButton(el, "Done");
    expect(navigate).toHaveBeenLastCalledWith({
      type: "standard__recordPage",
      attributes: {
        recordId: NEW_QUOTE_ID,
        objectApiName: "Quote",
        actionName: "view"
      }
    });
  });

  it("skips the Large Deal step for a quote that is already a Large Deal", async () => {
    const el = await openHierarchyFor(LARGE_DEAL_QUOTE_ID);
    // Six indicator dots instead of seven.
    expect(qa(el, ".step-indicator-item")).toHaveLength(6);

    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Product counts");
    await clickButton(el, "Next");

    expect(activeStepLabel(el)).toBe("Confirm");
    expect(text(el)).toContain("Yes (already set on quote)");

    await clickButton(el, "Back");
    expect(activeStepLabel(el)).toBe("Product counts");
  });

  it("previews the impact of counts on the Confirm step and surfaces a preview error", async () => {
    apex.previewQuoteLineCounts.mockRejectedValue({
      body: { message: "Preview unavailable" }
    });
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const el = await openHierarchyFor(QUOTE_ID);
    await clickButton(el, "Next");
    expect(text(el)).toContain("Calculating quote line estimate");

    await settle(400);

    expect(text(el)).toContain("Preview unavailable");
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining("previewQuoteLineCounts failed"),
      expect.anything()
    );
    errorSpy.mockRestore();
  });

  it("reports an Apex failure returned for a modify run", async () => {
    apex.runSetUpQuoteFromLWC.mockResolvedValue({
      success: false,
      errorMessage: "Quote is locked"
    });
    const el = await openHierarchyFor(QUOTE_ID);
    for (let i = 0; i < 3; i++) await clickButton(el, "Next");
    await clickButton(el, "Run");

    expect(activeStepLabel(el)).toBe("Result");
    expect(text(el)).toContain("Quote is locked");
  });
});

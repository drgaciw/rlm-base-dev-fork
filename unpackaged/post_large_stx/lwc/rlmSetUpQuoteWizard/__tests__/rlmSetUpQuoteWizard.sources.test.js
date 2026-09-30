/* eslint-disable no-await-in-loop -- sequential awaits are intentional: each step must settle before the next */
/* eslint-disable jest/no-mocks-import -- the shared harness lives in __mocks__ so jest ignores it for test discovery */
import {
  ACCOUNT_ID,
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

const CSV_HEADER =
  "Group 1,Group 2,Group 3,Group 4,Group 5,Bundle Product,Product,Quantity";
const VALID_CSV = [
  CSV_HEADER,
  "Alpha,Beta,,,,,QB-X,2",
  "Gamma,,,,,,QB-Y,"
].join("\n");

const REPEAT_QUOTES = [
  {
    quoteId: "0QA",
    quoteLabel: "Q-A",
    lines: [
      {
        groupName: "Parent Group",
        productName: "Router",
        productCode: "RTR-1",
        historicalQuantity: 2,
        editableQuantity: 3,
        historicalUnitPrice: 10,
        historicalNetTotal: 20
      },
      {
        groupName: "Child Group",
        productName: "Switch",
        productCode: "SW-1",
        historicalQuantity: 1
      },
      { productName: "Loose", productCode: "LS-1", historicalQuantity: 5 }
    ]
  },
  {
    quoteId: "0QB",
    quoteLabel: "Q-B",
    lines: [
      {
        groupName: "Parent Group",
        productName: "Cable",
        productCode: "CB-1",
        historicalQuantity: 4
      }
    ]
  }
];

const nextButton = (el) => footerButton(el, "Next");

// Attaches `content` as the chosen file on the visible <input type="file"> and
// waits for the FileReader callback.
const chooseCsv = async (el, content, name = "groups.csv") => {
  const input = q(el, 'input[type="file"]');
  const file = new File([content], name, { type: "text/csv" });
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  input.dispatchEvent(new CustomEvent("change"));
  await settle(50);
  await settle(50);
};

beforeEach(resetWizardMocks);
afterEach(() => {
  clearDocument();
  restoreTimers();
});

describe("c-rlm-set-up-quote-wizard: create from CSV", () => {
  const startCsv = async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "From CSV");
    await clickSelector(el, 'button[data-mode="CSV"]');
    await settle(400);
    await clickButton(el, "Next");
    return el;
  };

  it("locks Next for a moment after switching creation mode to stop click-through", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');

    await clickSelector(el, 'button[data-mode="CSV"]');
    expect(nextButton(el).disabled).toBe(true);
    expect(q(el, 'button[data-mode="CSV"]').className).toContain(
      "choice-card-selected"
    );

    await settle(400);
    expect(nextButton(el).disabled).toBe(false);
  });

  it("ignores a second click on the already selected mode card", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await clickSelector(el, 'button[data-mode="CSV"]');
    await settle(400);

    await clickSelector(el, 'button[data-mode="CSV"]');

    expect(nextButton(el).disabled).toBe(false);
  });

  it("parses the file, summarises it and gates Next on a valid upload", async () => {
    const el = await startCsv();
    expect(activeStepLabel(el)).toBe("Hierarchy");
    expect(nextButton(el).disabled).toBe(true);

    await chooseCsv(el, VALID_CSV);

    expect(text(el)).toContain("File: groups.csv");
    expect(text(el)).toContain("Rows: 2 · Groups: 2 · Line items: 2");
    expect(nextButton(el).disabled).toBe(false);
  });

  it("sends the parsed hierarchy and line items on Run, skipping product counts", async () => {
    const el = await startCsv();
    await chooseCsv(el, VALID_CSV);

    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Large Deal");
    await clickButton(el, "Next");
    expect(text(el)).toContain("Create from CSV");
    await clickButton(el, "Run");

    const payload = payloadSentToApex();
    expect(
      JSON.parse(payload.hierarchyJson).parents.map((p) => p.name)
    ).toEqual(["Alpha", "Gamma"]);
    expect(JSON.parse(payload.csvImportLineItemsJson)).toEqual([
      { path: "0-0", productIdentifier: "QB-X", quantity: 2 },
      { path: "1", productIdentifier: "QB-Y", quantity: 1 }
    ]);
    expect(activeStepLabel(el)).toBe("Result");
  });

  it("rejects a file whose header does not match and keeps Next disabled", async () => {
    const el = await startCsv();

    await chooseCsv(el, "Name,Qty\nA,1");

    expect(q(el, "pre.csv-debug-block").textContent).toContain(
      "Invalid CSV header. Expected columns: Group 1"
    );
    expect(nextButton(el).disabled).toBe(true);
    expect(text(el)).not.toContain("Rows:");
  });

  it("rejects a file that has a header but no data rows", async () => {
    const el = await startCsv();

    await chooseCsv(el, CSV_HEADER);

    expect(q(el, "pre.csv-debug-block").textContent).toBe(
      "CSV must have header and at least one data row"
    );
  });

  it("accepts a BOM, quoted cells and the nine-column Excel header", async () => {
    const el = await startCsv();
    const excel =
      '﻿Group 1,Group 2,Group 3,Group 4,Group 5,Bundle Product,"",Product,Quantity\r\n' +
      '"Big, Group",,,,,,,QB-Z,3\r\n';

    await chooseCsv(el, excel);

    expect(text(el)).toContain("Rows: 1 · Groups: 1 · Line items: 1");
  });

  it("clears a previous upload when the file chooser is emptied", async () => {
    const el = await startCsv();
    await chooseCsv(el, VALID_CSV);
    expect(text(el)).toContain("Rows: 2");

    const input = q(el, 'input[type="file"]');
    Object.defineProperty(input, "files", { value: [], configurable: true });
    input.dispatchEvent(new CustomEvent("change"));
    await settle();

    expect(text(el)).not.toContain("Rows: 2");
    expect(nextButton(el).disabled).toBe(true);
  });

  it("offers Import from CSV / Build manually when no mode card was chosen", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "Chooser");
    await clickButton(el, "Next");

    expect(text(el)).toContain("Choose how to add groups and products.");
    expect(q(el, 'input[type="file"]')).toBeNull();

    await clickSelector(el, 'button[data-choice="csv"]');
    expect(q(el, 'input[type="file"]')).not.toBeNull();
    expect(nextButton(el).disabled).toBe(true);
  });

  it("adds new groups from a CSV to an existing quote in the modify flow", async () => {
    apex.getQuotesForModify.mockResolvedValue([
      { value: "0Q1", label: "Q1", isLargeDeal: "false" }
    ]);
    apex.getQuoteHierarchy.mockResolvedValue({
      parents: [{ id: "0QG1", name: "Root", lineItemCount: 1, children: [] }]
    });
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="modify"]');
    await change(q(el, 'lightning-combobox[data-step="quote-id"]'), "0Q1");
    await clickButton(el, "Next");

    await clickSelector(el, 'button[data-rail="csv"]');
    await chooseCsv(el, VALID_CSV);
    expect(text(el)).toContain("Rows: 2");
    expect(
      q(
        el,
        'c-rlm-set-up-quote-hierarchy-tree[data-step="hierarchy-modify-csv-preview"]'
      )
    ).not.toBeNull();

    await clickButton(el, "Next");
    // Existing groups still get counts; new groups come from the file.
    expect(activeStepLabel(el)).toBe("Product counts");
    await clickSelector(el, 'button[data-rail="manual"]');
    expect(text(el)).toContain("New groups and products come from your CSV");

    await clickButton(el, "Next");
    await clickButton(el, "Next");
    await clickButton(el, "Run");
    expect(JSON.parse(payloadSentToApex().csvImportLineItemsJson)).toHaveLength(
      2
    );
  });
});

describe("c-rlm-set-up-quote-wizard: create with a manual hierarchy", () => {
  it("builds groups in the tree, sets a count per group and sends both to Apex", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "Manual");
    await clickButton(el, "Next");
    await clickSelector(el, 'button[data-choice="manual"]');

    const tree = q(
      el,
      'c-rlm-set-up-quote-hierarchy-tree[data-step="hierarchy-edit"]'
    );
    q(tree, ".parent-name-input").value = "Team A";
    q(tree, "lightning-button.btn-add").click();
    await settle();
    q(tree, 'lightning-input.child-name[data-parent-path="0"]').value =
      "Sub A1";
    qa(tree, "lightning-button")
      .find((b) => b.label === "Add" && b.dataset.parentPath === "0")
      .click();
    await settle();

    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Product counts");
    const inputs = qa(el, 'lightning-input[data-step="product-count"]');
    expect(inputs.map((i) => i.dataset.groupKey)).toEqual(["0", "0-0"]);
    await change(inputs[1], "4");
    await settle(400);

    await clickButton(el, "Next");
    await clickButton(el, "Next");
    const confirmTree = q(
      el,
      'c-rlm-set-up-quote-hierarchy-tree[data-step="hierarchy-confirm"]'
    );
    expect(
      qa(confirmTree, ".tree-label").map((l) => l.textContent.trim())
    ).toEqual(["Team A × 0", "Sub A1 × 4"]);
    await clickButton(el, "Run");

    const payload = payloadSentToApex();
    expect(JSON.parse(payload.hierarchyJson).parents[0]).toMatchObject({
      name: "Team A",
      children: [{ name: "Sub A1", path: "0-0" }]
    });
    expect(JSON.parse(payload.productCountsJson)).toEqual({ 0: 0, "0-0": 4 });
  });

  it("blocks Next when two groups share a name", async () => {
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "Dupes");
    await clickButton(el, "Next");
    await clickSelector(el, 'button[data-choice="manual"]');
    const tree = q(
      el,
      'c-rlm-set-up-quote-hierarchy-tree[data-step="hierarchy-edit"]'
    );
    for (const name of ["Same", "same"]) {
      q(tree, ".parent-name-input").value = name;
      q(tree, "lightning-button.btn-add").click();
      await settle();
    }

    await clickButton(el, "Next");

    expect(activeStepLabel(el)).toBe("Hierarchy");
    expect(text(el)).toContain("Duplicate group name is not allowed: same");
  });
});

describe("c-rlm-set-up-quote-wizard: create from previous quotes", () => {
  const startPrevious = async () => {
    apex.getAccountsForRepeatBuy.mockResolvedValue([
      { label: "Acme", value: ACCOUNT_ID }
    ]);
    apex.getRecentQuotesForRepeatBuy.mockResolvedValue([
      { label: "Q-A", value: "0QA" },
      { label: "Q-B", value: "0QB" }
    ]);
    apex.getRepeatBuyLines.mockResolvedValue(REPEAT_QUOTES);
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await nameQuote(el, "Repeat");
    await clickSelector(el, 'button[data-mode="PREVIOUS_QUOTES"]');
    await settle(400);
    return el;
  };
  const accountBox = (el) =>
    qa(el, "lightning-combobox").find(
      (c) => c.label === "Account for historical quote lookup"
    );
  // Static `name` is set as a property, not reflected as an attribute, so an
  // attribute selector would not match.
  const quoteList = (el) =>
    qa(el, "lightning-dual-listbox").find((d) => d.name === "repeatbuy-quotes");
  const pickQuotes = async (el, ids = ["0QA", "0QB"]) => {
    await change(accountBox(el), ACCOUNT_ID);
    await change(quoteList(el), ids);
  };
  const toAssignStep = async (el) => {
    await pickQuotes(el);
    await clickButton(el, "Next");
    await clickButton(el, "Next");
  };
  const rowInputs = (el, key) =>
    qa(el, "lightning-input").filter((i) => i.dataset.key === key);
  const gridRows = (el) => qa(el, ".repeat-grid-row");
  const searchBox = (el) =>
    qa(el, "lightning-input").find((i) => i.type === "search");
  const rowIcon = (el, key, alt) =>
    qa(el, "lightning-button-icon").find(
      (b) => b.dataset.key === key && b.alternativeText.startsWith(alt)
    );

  it("loads accounts, then that account's recent quotes into the dual listbox", async () => {
    const el = await startPrevious();

    expect(apex.getAccountsForRepeatBuy).toHaveBeenCalledTimes(1);
    expect(accountBox(el).options).toEqual([
      { label: "Acme", value: ACCOUNT_ID }
    ]);
    expect(quoteList(el).options).toEqual([]);

    await change(accountBox(el), ACCOUNT_ID);

    expect(apex.getRecentQuotesForRepeatBuy).toHaveBeenCalledWith({
      accountId: ACCOUNT_ID
    });
    expect(quoteList(el).options).toEqual([
      { label: "Q-A", value: "0QA" },
      { label: "Q-B", value: "0QB" }
    ]);
  });

  it("degrades to empty account and quote lists when Apex fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    apex.getAccountsForRepeatBuy.mockRejectedValue(new Error("acct"));
    apex.getRecentQuotesForRepeatBuy.mockRejectedValue(new Error("quotes"));
    const el = await mountWizard();
    await clickSelector(el, 'button[data-choice="create"]');
    await clickSelector(el, 'button[data-mode="PREVIOUS_QUOTES"]');
    await settle(400);
    expect(accountBox(el).options).toEqual([]);

    await change(accountBox(el), ACCOUNT_ID);

    expect(quoteList(el).options).toEqual([]);
    expect(errorSpy).toHaveBeenCalledTimes(2);
    errorSpy.mockRestore();
  });

  it("does not look up quotes when the account is cleared", async () => {
    const el = await startPrevious();

    await change(accountBox(el), "  ");

    expect(apex.getRecentQuotesForRepeatBuy).not.toHaveBeenCalled();
  });

  it("requires at least one source quote before leaving the quote step", async () => {
    const el = await startPrevious();

    await clickButton(el, "Next");

    expect(activeStepLabel(el)).toBe("Quote");
    expect(apex.getRepeatBuyLines).not.toHaveBeenCalled();
  });

  it("seeds the hierarchy from the selected quotes and merges duplicate top-level names", async () => {
    const el = await startPrevious();
    await pickQuotes(el);

    await clickButton(el, "Next");

    expect(apex.getRepeatBuyLines).toHaveBeenCalledWith({
      quoteIdsJson: JSON.stringify(["0QA", "0QB"])
    });
    expect(activeStepLabel(el)).toBe("Hierarchy");
    expect(text(el)).toContain("Historical groups are pre-seeded");
    const tree = q(
      el,
      'c-rlm-set-up-quote-hierarchy-tree[data-step="hierarchy-edit"]'
    );
    expect(qa(tree, ".tree-label").map((l) => l.textContent.trim())).toEqual([
      "Parent Group",
      "Child Group",
      "Ungrouped",
      "Parent Group"
    ]);

    await clickButton(el, "Next");
    // MERGE (the default) collapses the two "Parent Group" roots into one.
    expect(activeStepLabel(el)).toBe("Assign repeat lines");
    const masters = qa(el, "button[data-master-key]").map(
      (b) => b.dataset.masterKey
    );
    expect(masters).toContain("quote:0");
    expect(masters).toContain("quote:1");
    // The detail pane starts on the first source quote (3 of the 4 lines).
    expect(gridRows(el)).toHaveLength(3);
    expect(text(el)).toContain("4 total");
  });

  it("keeps duplicate group names apart with the RENAME resolution", async () => {
    const el = await startPrevious();
    await pickQuotes(el);
    await clickButton(el, "Next");

    const radio = qa(el, "lightning-radio-group").find(
      (r) => r.label === "When duplicate group names exist"
    );
    await change(radio, "RENAME");
    await clickButton(el, "Next");

    expect(activeStepLabel(el)).toBe("Assign repeat lines");
    await clickButton(el, "Next");
    await clickButton(el, "Next");
    await clickButton(el, "Next");
    await clickButton(el, "Run");

    const names = JSON.parse(payloadSentToApex().hierarchyJson).parents.map(
      (p) => p.name
    );
    expect(names).toEqual([
      "Parent Group",
      "Child Group",
      "Ungrouped",
      "Parent Group (2)"
    ]);
  });

  it("shows an empty hierarchy and no assignments when the line lookup fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const el = await startPrevious();
    apex.getRepeatBuyLines.mockRejectedValue(new Error("lines"));
    await pickQuotes(el);

    await clickButton(el, "Next");
    await clickButton(el, "Next");

    expect(activeStepLabel(el)).toBe("Assign repeat lines");
    expect(text(el)).toContain("No repeated lines available");
    errorSpy.mockRestore();
  });

  it("filters the repeated lines and narrows them by source quote", async () => {
    const el = await startPrevious();
    await toAssignStep(el);
    const masters = () =>
      qa(el, "button[data-master-key]").map((b) => b.dataset.masterKey);
    expect(gridRows(el)).toHaveLength(3);

    await clickSelector(el, 'button[data-master-key="quote:1"]');
    expect(gridRows(el)).toHaveLength(1);
    expect(text(el)).toContain("Selected: Q-B");

    // A filter only keeps quotes / groups that still have a matching line.
    await change(searchBox(el), "router");
    expect(masters().every((k) => k.includes(":0"))).toBe(true);
    expect(gridRows(el)).toHaveLength(0);
    expect(text(el)).toContain("No lines for this selection.");

    await clickSelector(el, 'button[data-master-key="quote:0"]');
    expect(gridRows(el)).toHaveLength(1);
    expect(text(el)).toContain("Router");
  });

  it("applies bulk target, duplicate, remove and restore to the selected rows", async () => {
    const el = await startPrevious();
    await toAssignStep(el);
    const bulkIcon = (alt) =>
      qa(el, "lightning-button-icon.repeat-bulk-icon-btn").find((b) =>
        b.alternativeText.startsWith(alt)
      );

    // Nothing selected: bulk actions are disabled.
    expect(bulkIcon("Duplicate").disabled).toBe(true);

    await change(qa(el, ".repeat-bulk-bar lightning-input")[0], undefined, {
      checked: true
    });
    expect(text(el)).toContain("4 selected of 4 total");
    expect(bulkIcon("Duplicate").disabled).toBe(false);

    await change(q(el, "lightning-combobox.repeat-bulk-target"), "1");
    await clickButton(el, "Apply to selected");
    expect(text(el)).toContain("4 selected row(s) updated with target group.");

    bulkIcon("Duplicate").click();
    await settle();
    expect(text(el)).toContain(
      "4 selected row(s) marked as Duplicate to target."
    );

    bulkIcon("Remove").click();
    await settle();
    expect(text(el)).toContain("Removed 4");

    bulkIcon("Restore").click();
    await settle();
    expect(text(el)).toContain("Removed 0");
  });

  it("edits a single row: selection, quantity, duplicate and remove toggles", async () => {
    const el = await startPrevious();
    await toAssignStep(el);
    const key = "0QA-0-0";

    const [checkbox, quantity] = rowInputs(el, key);
    expect(quantity.value).toBe(3);
    await change(checkbox, undefined, { checked: true });
    expect(text(el)).toContain("1 selected of 4 total");

    await change(quantity, "9");
    expect(rowInputs(el, key)[1].value).toBe(9);
    await change(rowInputs(el, key)[1], "0");
    expect(rowInputs(el, key)[1].value).toBe(1);

    rowIcon(el, key, "Duplicate to target").click();
    await settle();
    expect(text(el)).toContain("1 row marked as duplicate to target.");
    rowIcon(el, key, "Undo duplicate").click();
    await settle();
    expect(text(el)).toContain("1 row unmarked from duplicate.");

    rowIcon(el, key, "Remove from add").click();
    await settle();
    expect(text(el)).toContain("1 row marked as remove from add.");
    expect(text(el)).toContain("Removed 1");
    rowIcon(el, key, "Restore").click();
    await settle();
    expect(text(el)).toContain("1 row restored.");
  });

  it("sends the edited assignments to Apex as repeatBuyAssignmentsJson", async () => {
    const el = await startPrevious();
    await toAssignStep(el);
    const key = "0QA-0-0";
    await change(rowInputs(el, key)[1], "6");
    rowIcon(el, "0QA-1-0", "Remove from add").click();
    await settle();

    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Product counts");
    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Large Deal");
    await clickButton(el, "Next");
    expect(text(el)).toContain("Create from previous quotes");
    await clickButton(el, "Run");

    const payload = payloadSentToApex();
    expect(payload.repeatBuyAccountId).toBe(ACCOUNT_ID);
    const rows = JSON.parse(payload.repeatBuyAssignmentsJson);
    expect(rows).toHaveLength(4);
    expect(rows[0]).toMatchObject({
      productIdentifier: "RTR-1",
      quantity: 6,
      removed: false,
      duplicateToTarget: false
    });
    expect(rows.find((r) => r.productIdentifier === "SW-1").removed).toBe(true);
    // The 4-step indicator flow keeps the source quote name and mode locked.
    expect(payload.newQuoteName).toBe("Repeat");
  });

  it("goes back through the assignment step to the hierarchy step", async () => {
    const el = await startPrevious();
    await toAssignStep(el);

    await clickButton(el, "Back");
    expect(activeStepLabel(el)).toBe("Hierarchy");

    await clickButton(el, "Next");
    await clickButton(el, "Next");
    expect(activeStepLabel(el)).toBe("Product counts");
    await clickButton(el, "Back");
    expect(activeStepLabel(el)).toBe("Assign repeat lines");
  });
});

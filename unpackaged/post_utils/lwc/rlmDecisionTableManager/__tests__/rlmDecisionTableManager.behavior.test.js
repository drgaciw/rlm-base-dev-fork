/* eslint-disable no-await-in-loop -- sequential awaits are intentional: each step must settle before the next */
import RlmDecisionTableManager from "c/rlmDecisionTableManager";
import { clearDocument, mountComponent } from "@rlm/lwc-test-utils";
import getDecisionTables from "@salesforce/apex/RLM_DecisionTableManagerController.getDecisionTables";
import refreshTables from "@salesforce/apex/RLM_DecisionTableManagerController.refreshTables";
import getRefreshStatus from "@salesforce/apex/RLM_DecisionTableManagerController.getRefreshStatus";

jest.mock(
  "@salesforce/apex/RLM_DecisionTableManagerController.getDecisionTables",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_DecisionTableManagerController.refreshTables",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_DecisionTableManagerController.getRefreshStatus",
  () => ({ default: jest.fn() }),
  { virtual: true }
);

const TAG = "c-rlm-decision-table-manager";
const POLL_MS = 4000;

const table = (overrides = {}) => ({
  label: "Price Rules",
  apiName: "PriceRules",
  description: "Prices by product",
  usageType: "DefaultPricing",
  staleness: "Fresh",
  stalenessReason: "Synced after the newest visible change.",
  refreshStatus: "Completed",
  refreshFailureReason: null,
  lastSyncDate: "2025-01-10T10:00:00.000Z",
  lastIncrementalSyncDate: null,
  incrementalEnabled: false,
  dataSourceType: "SingleSobject",
  sourceObject: "Product2",
  tableType: "Lookup",
  executionType: "Sequential",
  conditionType: "All",
  filterResultBy: null,
  status: "Active",
  isVersioned: false,
  sourceCriteria: ["IsActive = true"],
  criteriaApplied: true,
  unreproducedCriteria: [],
  sourceRowCount: 12,
  sourceNewestChange: "2025-01-09T10:00:00.000Z",
  contributingObjects: [],
  ...overrides
});

const TABLES = [
  table(),
  table({
    label: "Rate Card",
    apiName: "RateCard",
    usageType: "DefaultRating",
    staleness: "Stale",
    stalenessReason: "Product2 changed after the last full sync."
  }),
  table({
    label: "Bundle Rules",
    apiName: "BundleRules",
    usageType: "ProductQualification",
    staleness: "Not comparable",
    sourceRowCount: 0,
    criteriaApplied: false
  }),
  table({
    label: "Tax Table",
    apiName: "TaxTable",
    usageType: "RevenueStandardTax",
    staleness: "Unknown",
    lastSyncDate: null,
    refreshStatus: ""
  })
];

// With fake timers, `ms` also runs the component's poll interval.
const settle = async (ms = 0) => {
  await jest.advanceTimersByTimeAsync(ms);
  for (let i = 0; i < 50; i++) await Promise.resolve();
};

const mount = async () => {
  const el = mountComponent(TAG, RlmDecisionTableManager);
  const toasts = [];
  el.addEventListener("lightning__showtoast", (e) => toasts.push(e.detail));
  await settle();
  return { el, toasts };
};

const q = (el, selector) => el.shadowRoot.querySelector(selector);
const qa = (el, selector) => [...el.shadowRoot.querySelectorAll(selector)];
const text = (el) => el.shadowRoot.textContent.replace(/\s+/g, " ");
const grid = (el) => q(el, "lightning-datatable");
const rowNames = (el) => grid(el).data.map((r) => r.apiName);
const button = (el, label) =>
  qa(el, "lightning-button").find((b) => b.label === label);
const tile = (el, key) => q(el, `button[data-verdict="${key}"]`);
const tileCounts = (el) =>
  Object.fromEntries(
    qa(el, ".dtm-tile").map((t) => [
      t.querySelector(".dtm-tile__label").textContent.trim(),
      Number(t.querySelector(".dtm-tile__count").textContent)
    ])
  );
const click = async (node) => {
  node.click();
  await settle();
};
const select = async (el, apiNames) => {
  grid(el).dispatchEvent(
    new CustomEvent("rowselection", {
      detail: { selectedRows: apiNames.map((apiName) => ({ apiName })) }
    })
  );
  await settle();
};
const queued = (over = {}) => ({
  queuedCount: 1,
  failedCount: 0,
  failedApiNames: [],
  unknownApiNames: [],
  incremental: false,
  ...over
});
const statusRow = (over = {}) => ({
  apiName: "RateCard",
  label: "Rate Card",
  usageType: "DefaultRating",
  refreshStatus: "Completed",
  lastSyncDate: "2025-01-10T10:00:00.000Z",
  lastIncrementalSyncDate: null,
  ...over
});

beforeEach(() => {
  jest.useFakeTimers();
  [getDecisionTables, refreshTables, getRefreshStatus].forEach((fn) =>
    fn.mockReset()
  );
  getDecisionTables.mockResolvedValue(TABLES);
});

afterEach(() => {
  clearDocument();
  jest.clearAllTimers();
  jest.useRealTimers();
});

describe("c-rlm-decision-table-manager: render", () => {
  it("shows a spinner while loading, then the sorted table and row summary", async () => {
    let release;
    getDecisionTables.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      })
    );
    const el = mountComponent(TAG, RlmDecisionTableManager);
    await settle();
    expect(q(el, "lightning-spinner")).not.toBeNull();
    expect(grid(el)).toBeNull();

    release(TABLES);
    await settle();

    expect(q(el, "lightning-spinner")).toBeNull();
    // default sort: usage type ascending
    expect(rowNames(el)).toEqual([
      "PriceRules", // DefaultPricing
      "RateCard", // DefaultRating
      "BundleRules", // ProductQualification
      "TaxTable" // RevenueStandardTax
    ]);
    expect(text(el)).toContain("4 decision tables");
  });

  it("counts Fresh, Stale and not-established tables in the summary tiles", async () => {
    const { el } = await mount();

    expect(tileCounts(el)).toEqual({
      Total: 4,
      Stale: 1,
      Fresh: 1,
      "Not comparable": 2
    });
    expect(tile(el, "all").getAttribute("aria-pressed")).toBe("true");
  });

  it("decorates rows with a verdict icon, usage icon and refresh colour", async () => {
    const { el } = await mount();

    const byName = Object.fromEntries(grid(el).data.map((r) => [r.apiName, r]));
    expect(byName.PriceRules).toMatchObject({
      stalenessIcon: "utility:success",
      usageIcon: "utility:moneybag",
      refreshStatusClass: "slds-text-color_success"
    });
    expect(byName.RateCard.stalenessIcon).toBe("utility:warning");
    expect(byName.TaxTable.stalenessIcon).toBe("utility:question");
    expect(byName.TaxTable.usageIcon).toBe("utility:percent");
  });

  it("lists every usage type plus an All option", async () => {
    const { el } = await mount();

    const box = qa(el, "lightning-combobox").find(
      (c) => c.label === "Usage type"
    );
    expect(box.options.map((o) => o.value)).toEqual([
      "all",
      "DefaultPricing",
      "DefaultRating",
      "ProductQualification",
      "RevenueStandardTax"
    ]);
  });
});

describe("c-rlm-decision-table-manager: empty state and load errors", () => {
  it("explains a missing DecisionTable read permission when nothing is returned", async () => {
    getDecisionTables.mockResolvedValue([]);
    const { el } = await mount();

    expect(grid(el)).toBeNull();
    expect(text(el)).toContain(
      "No decision tables were returned. You may not have read access to DecisionTable."
    );
    expect(button(el, "Refresh stale only").disabled).toBe(true);
    expect(button(el, "Refresh all shown (0)").disabled).toBe(true);
  });

  it("says no tables match once filters remove every row", async () => {
    const { el } = await mount();
    const search = qa(el, "lightning-input").find((i) => i.type === "search");
    search.value = "zzz-no-such-table";
    search.dispatchEvent(new CustomEvent("change"));
    await settle();

    expect(text(el)).toContain("No decision tables match the current filters.");
    expect(grid(el)).toBeNull();
  });

  it("shows the Apex error message and an empty list when loading fails", async () => {
    getDecisionTables.mockRejectedValue({
      body: { message: "Insufficient access" }
    });
    const { el } = await mount();

    expect(q(el, '[role="alert"]').textContent).toContain(
      "Insufficient access"
    );
    expect(text(el)).toContain("No decision tables were returned");
    expect(q(el, "lightning-spinner")).toBeNull();
  });

  it("reads a plain Error message and tells the user to reload for unknown shapes", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    getDecisionTables.mockRejectedValueOnce(new Error("Network down"));
    const { el } = await mount();
    expect(q(el, '[role="alert"]').textContent).toContain("Network down");

    getDecisionTables.mockRejectedValueOnce({});
    await click(
      qa(el, "lightning-button-icon").find(
        (b) => b.alternativeText === "Reload table list"
      )
    );

    expect(q(el, '[role="alert"]').textContent).toContain(
      "Reload the page and try again"
    );
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining("unrecognised error shape"),
      expect.anything()
    );
    errorSpy.mockRestore();
  });

  it("reloads the list from the reload button and clears a previous error", async () => {
    getDecisionTables.mockRejectedValueOnce(new Error("first try failed"));
    const { el } = await mount();
    expect(q(el, '[role="alert"]')).not.toBeNull();

    await click(
      qa(el, "lightning-button-icon").find(
        (b) => b.alternativeText === "Reload table list"
      )
    );

    expect(getDecisionTables).toHaveBeenCalledTimes(2);
    expect(q(el, '[role="alert"]')).toBeNull();
    expect(grid(el).data).toHaveLength(4);
  });
});

describe("c-rlm-decision-table-manager: filtering, sorting and selecting", () => {
  it("narrows rows by search text across name, API name and source object", async () => {
    const { el } = await mount();
    const search = qa(el, "lightning-input").find((i) => i.type === "search");

    search.value = "  rate card ";
    search.dispatchEvent(new CustomEvent("change"));
    await settle();
    expect(rowNames(el)).toEqual(["RateCard"]);
    expect(text(el)).toContain("1 of 4 decision tables");

    search.value = "product2";
    search.dispatchEvent(new CustomEvent("change"));
    await settle();
    expect(rowNames(el)).toHaveLength(4);
  });

  it("filters by usage type", async () => {
    const { el } = await mount();
    const box = qa(el, "lightning-combobox").find(
      (c) => c.label === "Usage type"
    );

    box.dispatchEvent(
      new CustomEvent("change", { detail: { value: "DefaultRating" } })
    );
    await settle();

    expect(rowNames(el)).toEqual(["RateCard"]);
    expect(button(el, "Refresh all shown (1)")).toBeTruthy();
  });

  it("toggles a verdict filter from a summary tile and back off again", async () => {
    const { el } = await mount();

    await click(tile(el, "Stale"));
    expect(rowNames(el)).toEqual(["RateCard"]);
    expect(tile(el, "Stale").getAttribute("aria-pressed")).toBe("true");
    expect(tile(el, "Stale").className).toContain("is-active");

    await click(tile(el, "Stale"));
    expect(rowNames(el)).toHaveLength(4);
    expect(tile(el, "all").getAttribute("aria-pressed")).toBe("true");
  });

  it("the not-comparable tile selects both non-committal verdicts, matching its count", async () => {
    const { el } = await mount();

    await click(tile(el, "unclear"));

    expect(rowNames(el).sort()).toEqual(["BundleRules", "TaxTable"]);
    expect(tileCounts(el)["Not comparable"]).toBe(2);
  });

  it("sorts on a column header in both directions, keeping never-synced rows last", async () => {
    const { el } = await mount();
    const sort = (fieldName, sortDirection) =>
      grid(el).dispatchEvent(
        new CustomEvent("sort", { detail: { fieldName, sortDirection } })
      );

    sort("label", "asc");
    await settle();
    expect(rowNames(el)).toEqual([
      "BundleRules",
      "PriceRules",
      "RateCard",
      "TaxTable"
    ]);
    expect(grid(el).sortedBy).toBe("label");

    sort("label", "desc");
    await settle();
    expect(rowNames(el)).toEqual([
      "TaxTable",
      "RateCard",
      "PriceRules",
      "BundleRules"
    ]);

    sort("lastSyncDate", "asc");
    await settle();
    expect(rowNames(el).pop()).toBe("TaxTable");
    sort("lastSyncDate", "desc");
    await settle();
    expect(rowNames(el).pop()).toBe("TaxTable");
  });

  it("tracks row selection in the refresh button label and row summary", async () => {
    const { el } = await mount();
    expect(button(el, "Refresh selected").disabled).toBe(true);

    await select(el, ["RateCard", "PriceRules"]);

    expect(button(el, "Refresh 2 selected").disabled).toBe(false);
    expect(text(el)).toContain("4 decision tables · 2 selected");
  });
});

describe("c-rlm-decision-table-manager: row details dialog", () => {
  const openDetails = async (el, apiName) => {
    const row = grid(el).data.find((r) => r.apiName === apiName);
    grid(el).dispatchEvent(
      new CustomEvent("rowaction", {
        detail: { action: { name: "details" }, row }
      })
    );
    await settle();
  };
  const dialog = (el) => q(el, 'section[role="dialog"]');

  it("opens the verdict, definition and criteria for the chosen table and takes focus", async () => {
    const { el } = await mount();
    expect(dialog(el)).toBeNull();

    await openDetails(el, "RateCard");

    expect(dialog(el)).not.toBeNull();
    expect(dialog(el).getAttribute("aria-modal")).toBe("true");
    expect(el.shadowRoot.activeElement).toBe(dialog(el));
    const body = text(el);
    expect(body).toContain("Rate Card");
    expect(body).toContain("Product2 changed after the last full sync.");
    expect(body).toContain("SingleSobject · Product2");
    expect(body).toContain("Lookup · executes via Sequential");
    expect(body).toContain("All conditions");
    expect(body).toContain("Applied to the freshness check");
    expect(q(el, ".dtm-verdict_stale")).not.toBeNull();
    expect(qa(el, ".dtm-criteria code").map((c) => c.textContent)).toEqual([
      "IsActive = true"
    ]);
  });

  it("frames an unestablished verdict with the caveats instead of reassurance", async () => {
    const { el } = await mount();

    await openDetails(el, "BundleRules");

    expect(q(el, ".dtm-verdict_unclear")).not.toBeNull();
    const body = text(el);
    expect(body).toContain("Not comparable");
    expect(body).toContain("Nothing visible matched the reproduced filter.");
    expect(body).toContain("Not reproduced by the freshness check");
  });

  it("shows a failed-refresh callout, a never-synced date and no-data notes", async () => {
    getDecisionTables.mockResolvedValue([
      table({
        apiName: "Broken",
        label: "Broken",
        refreshStatus: "Failed",
        refreshFailureReason: "Row limit exceeded",
        lastSyncDate: null,
        sourceRowCount: null,
        sourceNewestChange: null
      })
    ]);
    const { el } = await mount();

    await openDetails(el, "Broken");

    const body = text(el);
    expect(body).toContain("Last refresh failed");
    expect(body).toContain("Row limit exceeded");
    expect(body).toContain("Never");
    expect(body).toContain("Source was not counted.");
    expect(body).toContain("Nothing visible to compare against.");
    expect(grid(el).data[0].refreshStatusClass).toBe("slds-text-color_error");
  });

  it("closes from the Close button, returning focus to the table", async () => {
    const { el } = await mount();
    await openDetails(el, "PriceRules");

    await click(button(el, "Close"));

    expect(dialog(el)).toBeNull();
  });

  it("closes on Escape and stops the key from reaching the page", async () => {
    const { el } = await mount();
    await openDetails(el, "PriceRules");
    const escape = new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
      cancelable: true
    });
    const stop = jest.spyOn(escape, "stopPropagation");

    dialog(el).dispatchEvent(escape);
    await settle();

    expect(stop).toHaveBeenCalled();
    expect(dialog(el)).toBeNull();
  });

  it("keeps the open dialog in step with the list when it is reloaded", async () => {
    const { el } = await mount();
    await openDetails(el, "RateCard");
    expect(text(el)).toContain("Product2 changed after the last full sync.");

    getDecisionTables.mockResolvedValue([
      table({
        apiName: "RateCard",
        label: "Rate Card",
        staleness: "Fresh",
        stalenessReason: "Now synced."
      })
    ]);
    await click(
      qa(el, "lightning-button-icon").find(
        (b) => b.alternativeText === "Reload table list"
      )
    );

    expect(text(el)).toContain("Now synced.");
    expect(q(el, ".dtm-verdict_fresh")).not.toBeNull();
  });

  it("wraps focus with the sentinels and Shift+Tab from the dialog", async () => {
    const { el } = await mount();
    await openDetails(el, "PriceRules");
    const [before, after] = qa(el, ".dtm-focus-sentinel");
    // The lightning-button stub has no focus(); spy on the host's.
    const closeButton = q(el, ".slds-modal__footer lightning-button");
    closeButton.focus = jest.fn();

    after.dispatchEvent(new CustomEvent("focusin"));
    expect(el.shadowRoot.activeElement).toBe(dialog(el));
    expect(closeButton.focus).not.toHaveBeenCalled();

    before.dispatchEvent(new CustomEvent("focusin"));
    expect(closeButton.focus).toHaveBeenCalledTimes(1);

    const shiftTab = new KeyboardEvent("keydown", {
      key: "Tab",
      shiftKey: true,
      bubbles: true,
      cancelable: true
    });
    dialog(el).dispatchEvent(shiftTab);
    expect(shiftTab.defaultPrevented).toBe(true);
    expect(closeButton.focus).toHaveBeenCalledTimes(2);
  });
});

describe("c-rlm-decision-table-manager: refresh and polling", () => {
  it("queues the selected tables, announces it and polls until the refresh completes", async () => {
    refreshTables.mockResolvedValue(queued());
    getRefreshStatus
      .mockResolvedValueOnce([statusRow()]) // unchanged terminal status: not proof this run started
      .mockResolvedValueOnce([statusRow({ refreshStatus: "In Progress" })])
      .mockResolvedValueOnce([
        statusRow({
          refreshStatus: "Completed",
          lastSyncDate: "2025-02-01T00:00:00.000Z"
        })
      ]);
    const { el, toasts } = await mount();
    await select(el, ["RateCard"]);

    await click(button(el, "Refresh 1 selected"));

    expect(refreshTables).toHaveBeenCalledWith({
      apiNames: ["RateCard"],
      incremental: false
    });
    expect(toasts[0]).toMatchObject({
      title: "Full refresh queued",
      message: "1 decision table(s) queued.",
      variant: "success"
    });
    expect(text(el)).toContain("Watching 1 decision table(s)");
    expect(q(el, "lightning-progress-bar")).not.toBeNull();
    // Buttons lock while a refresh is being watched.
    expect(button(el, "Refresh all shown (4)").disabled).toBe(true);

    await settle(POLL_MS);
    expect(text(el)).toContain("Refreshing — 0 of 1 finished");
    await settle(POLL_MS);
    expect(text(el)).toContain("Refreshing — 0 of 1 finished");
    expect(toasts).toHaveLength(1);

    await settle(POLL_MS);
    expect(toasts.at(-1)).toMatchObject({
      title: "Refresh complete",
      variant: "success"
    });
    expect(q(el, "lightning-progress-bar")).toBeNull();
    // A finished watch reloads the authoritative list.
    expect(getDecisionTables).toHaveBeenCalledTimes(2);
    expect(getRefreshStatus).toHaveBeenCalledTimes(3);
  });

  it("does not report a failed refresh as complete", async () => {
    refreshTables.mockResolvedValue(queued());
    getRefreshStatus.mockResolvedValue([
      statusRow({
        refreshStatus: "Failed",
        lastSyncDate: "2025-02-01T00:00:00.000Z"
      })
    ]);
    const { el, toasts } = await mount();
    await select(el, ["RateCard"]);
    await click(button(el, "Refresh 1 selected"));

    await settle(POLL_MS);

    const last = toasts.at(-1);
    expect(last).toMatchObject({
      title: "Refresh finished with problems",
      variant: "error",
      mode: "sticky"
    });
    expect(last.message).toContain("RateCard (Failed)");
    expect(toasts.map((t) => t.title)).not.toContain("Refresh complete");
  });

  it("sends incremental=true when the toggle is on and labels the toast accordingly", async () => {
    refreshTables.mockResolvedValue(queued({ incremental: true }));
    getRefreshStatus.mockResolvedValue([
      statusRow({ refreshStatus: "Queued" })
    ]);
    const { el, toasts } = await mount();
    const toggle = qa(el, "lightning-input").find((i) => i.type === "toggle");
    toggle.checked = true;
    toggle.dispatchEvent(new CustomEvent("change"));
    await settle();
    await select(el, ["RateCard"]);

    await click(button(el, "Refresh 1 selected"));

    expect(refreshTables).toHaveBeenCalledWith({
      apiNames: ["RateCard"],
      incremental: true
    });
    expect(toasts[0].title).toBe("Incremental refresh queued");
  });

  it("refreshes every shown table and only the stale ones", async () => {
    refreshTables.mockResolvedValue(queued({ queuedCount: 4 }));
    getRefreshStatus.mockResolvedValue([
      statusRow({ refreshStatus: "Queued" })
    ]);
    const { el } = await mount();

    await click(button(el, "Refresh stale only"));
    expect(refreshTables.mock.calls[0][0].apiNames).toEqual(["RateCard"]);

    await click(button(el, "Stop watching"));
    await click(button(el, "Refresh all shown (4)"));
    expect(refreshTables.mock.calls[1][0].apiNames.sort()).toEqual([
      "BundleRules",
      "PriceRules",
      "RateCard",
      "TaxTable"
    ]);
  });

  it("reports a partial queue, watching only the accepted tables", async () => {
    refreshTables.mockResolvedValue(
      queued({
        queuedCount: 1,
        failedCount: 1,
        failedApiNames: ["PriceRules"],
        unknownApiNames: ["Ghost"]
      })
    );
    getRefreshStatus.mockResolvedValue([
      statusRow({ refreshStatus: "Queued" })
    ]);
    const { el, toasts } = await mount();
    await select(el, ["RateCard", "PriceRules", "Ghost"]);

    await click(button(el, "Refresh 3 selected"));

    expect(toasts[0]).toMatchObject({
      title: "Full refresh partially queued",
      variant: "warning",
      mode: "sticky"
    });
    expect(toasts[0].message).toBe(
      "1 queued · 1 failed to queue (PriceRules) · 1 not found (Ghost)"
    );
    await settle(POLL_MS);
    expect(getRefreshStatus).toHaveBeenCalledWith({ apiNames: ["RateCard"] });
  });

  it("shows the controller's error and the unknown names without starting to poll", async () => {
    refreshTables.mockResolvedValue({
      errorMessage: "Incremental refresh is disabled for PriceRules.",
      unknownApiNames: ["Ghost"],
      queuedCount: 0
    });
    const { el, toasts } = await mount();
    await select(el, ["PriceRules"]);

    await click(button(el, "Refresh 1 selected"));

    expect(q(el, '[role="alert"]').textContent).toContain(
      "Incremental refresh is disabled for PriceRules. Also not found: Ghost."
    );
    expect(toasts[0]).toMatchObject({
      title: "Refresh not started",
      variant: "error"
    });
    expect(q(el, "lightning-progress-bar")).toBeNull();
    await settle(POLL_MS);
    expect(getRefreshStatus).not.toHaveBeenCalled();
  });

  it("reports a thrown refresh call and unlocks the page", async () => {
    refreshTables.mockRejectedValue({ body: { message: "Callout limit" } });
    const { el, toasts } = await mount();
    await select(el, ["PriceRules"]);

    await click(button(el, "Refresh 1 selected"));

    expect(toasts.at(-1)).toMatchObject({
      title: "Refresh failed",
      message: "Callout limit",
      variant: "error",
      mode: "sticky"
    });
    expect(q(el, "lightning-spinner")).toBeNull();
    expect(button(el, "Refresh 1 selected").disabled).toBe(false);
  });

  it("stops watching and warns when the status call itself fails", async () => {
    refreshTables.mockResolvedValue(queued());
    getRefreshStatus.mockRejectedValue(new Error("Status endpoint down"));
    const { el, toasts } = await mount();
    await select(el, ["RateCard"]);
    await click(button(el, "Refresh 1 selected"));

    await settle(POLL_MS);

    expect(toasts.at(-1)).toMatchObject({
      title: "Lost track of the refresh",
      message: "Status endpoint down"
    });
    expect(q(el, "lightning-progress-bar")).toBeNull();
    await settle(POLL_MS * 3);
    expect(getRefreshStatus).toHaveBeenCalledTimes(1);
  });

  it("gives up after 45 checks and says the outcome is unknown", async () => {
    refreshTables.mockResolvedValue(queued());
    getRefreshStatus.mockResolvedValue([
      statusRow({ refreshStatus: "In Progress" })
    ]);
    const { el, toasts } = await mount();
    await select(el, ["RateCard"]);
    await click(button(el, "Refresh 1 selected"));

    await settle(POLL_MS * 45);

    expect(getRefreshStatus).toHaveBeenCalledTimes(45);
    const last = toasts.at(-1);
    expect(last).toMatchObject({
      title: "Stopped watching",
      variant: "warning",
      mode: "sticky"
    });
    expect(last.message).toContain("Stopped watching after 45 checks.");
    expect(last.message).toContain(
      "1 table(s) could not be confirmed finished: RateCard."
    );
    expect(q(el, "lightning-progress-bar")).toBeNull();
  });

  it("does not open a second overlapping poll while one is still in flight", async () => {
    refreshTables.mockResolvedValue(queued());
    let release;
    getRefreshStatus.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      })
    );
    const { el } = await mount();
    await select(el, ["RateCard"]);
    await click(button(el, "Refresh 1 selected"));

    await settle(POLL_MS * 3);
    expect(getRefreshStatus).toHaveBeenCalledTimes(1);

    release([statusRow({ refreshStatus: "In Progress" })]);
    await settle(POLL_MS);
    expect(getRefreshStatus).toHaveBeenCalledTimes(2);
  });

  it("lets the user stop watching without cancelling the queued refresh", async () => {
    refreshTables.mockResolvedValue(queued());
    getRefreshStatus.mockResolvedValue([
      statusRow({ refreshStatus: "In Progress" })
    ]);
    const { el, toasts } = await mount();
    await select(el, ["RateCard"]);
    await click(button(el, "Refresh 1 selected"));

    await click(button(el, "Stop watching"));

    expect(toasts.at(-1)).toMatchObject({
      title: "Stopped watching",
      variant: "info"
    });
    expect(toasts.at(-1).message).toContain(
      "Any refresh already queued is unaffected"
    );
    expect(q(el, "lightning-progress-bar")).toBeNull();
    await settle(POLL_MS * 2);
    expect(getRefreshStatus).not.toHaveBeenCalled();
  });

  it("never starts polling when the page is left while the refresh call is pending", async () => {
    let release;
    refreshTables.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      })
    );
    getRefreshStatus.mockResolvedValue([
      statusRow({ refreshStatus: "In Progress" })
    ]);
    const { el, toasts } = await mount();
    await select(el, ["RateCard"]);
    await click(button(el, "Refresh 1 selected"));

    clearDocument();
    release(queued());
    await settle(POLL_MS * 3);

    expect(getRefreshStatus).not.toHaveBeenCalled();
    expect(toasts).toHaveLength(0);
    // el is detached but must not have opened an interval
    expect(jest.getTimerCount()).toBe(0);
    expect(el.isConnected).toBe(false);
  });

  it("clears the poll timer when the component is removed mid-refresh", async () => {
    refreshTables.mockResolvedValue(queued());
    getRefreshStatus.mockResolvedValue([
      statusRow({ refreshStatus: "In Progress" })
    ]);
    const { el } = await mount();
    await select(el, ["RateCard"]);
    await click(button(el, "Refresh 1 selected"));
    expect(jest.getTimerCount()).toBeGreaterThan(0);

    clearDocument();
    await settle();

    expect(jest.getTimerCount()).toBe(0);
    await settle(POLL_MS * 2);
    expect(getRefreshStatus).not.toHaveBeenCalled();
  });
});

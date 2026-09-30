/* eslint-disable no-await-in-loop -- sequential awaits are intentional: each step must settle before the next */
import RlmUsageUploader from "c/rlmUsageUploader";
import { clearDocument, mountComponent } from "@rlm/lwc-test-utils";
import getAssetsForAccount from "@salesforce/apex/RLM_UsageUploaderController.getAssetsForAccount";
import getUsageResourcesForAsset from "@salesforce/apex/RLM_UsageUploaderController.getUsageResourcesForAsset";
import uploadUsage from "@salesforce/apex/RLM_UsageUploaderController.uploadUsage";
import validateUsageEntries from "@salesforce/apex/RLM_UsageUploaderController.validateUsageEntries";
import bulkUploadUsage from "@salesforce/apex/RLM_UsageUploaderController.bulkUploadUsage";

jest.mock(
  "@salesforce/apex/RLM_UsageUploaderController.getAssetsForAccount",
  () => {
    const { createApexTestWireAdapter } = jest.requireActual(
      "@salesforce/sfdx-lwc-jest"
    );
    return {
      default: createApexTestWireAdapter(jest.fn(() => Promise.resolve()))
    };
  },
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_UsageUploaderController.getUsageResourcesForAsset",
  () => {
    const { createApexTestWireAdapter } = jest.requireActual(
      "@salesforce/sfdx-lwc-jest"
    );
    return {
      default: createApexTestWireAdapter(jest.fn(() => Promise.resolve()))
    };
  },
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_UsageUploaderController.uploadUsage",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_UsageUploaderController.validateUsageEntries",
  () => ({ default: jest.fn() }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_UsageUploaderController.bulkUploadUsage",
  () => ({ default: jest.fn() }),
  { virtual: true }
);

const TAG = "c-rlm-usage-uploader";
const ASSET_ID = "02i000000000001AAA";
const ACCOUNT_ID = "001000000000001AAA";
const TODAY = "2025-06-15";

const RESOURCES = [
  {
    resourceId: "UR1",
    resourceName: "API Calls",
    unitOfMeasureId: "U1",
    availableUoms: [
      { uomId: "U1", uomName: "Call", uomCode: "CALL" },
      { uomId: "U2", uomName: "Kilo-call", uomCode: "KCALL" }
    ]
  },
  {
    resourceId: "UR2",
    resourceName: "Storage, GB",
    unitOfMeasureId: "U3",
    availableUoms: [{ uomId: "U3", uomName: "Gigabyte", uomCode: "GB" }]
  }
];

const ASSETS = [
  { assetId: ASSET_ID, assetName: "Asset A", productName: "Platform" },
  {
    assetId: "02i000000000002AAA",
    assetName: "Asset B",
    productName: "Storage"
  }
];

const CSV_HEADER = "Usage Resource,Quantity,Transaction Date";

// Lets awaited Apex promises settle and the component re-render.
const settle = async (ms = 0) => {
  await jest.advanceTimersByTimeAsync(ms);
  for (let i = 0; i < 50; i++) await Promise.resolve();
};

const mountOn = async (recordId, { resources = RESOURCES, assets } = {}) => {
  const el = mountComponent(TAG, RlmUsageUploader, { recordId });
  const toasts = [];
  el.addEventListener("lightning__showtoast", (e) => toasts.push(e.detail));
  if (assets) getAssetsForAccount.emit(assets);
  if (resources) getUsageResourcesForAsset.emit(resources);
  await settle();
  return { el, toasts };
};
const mountAsset = () => mountOn(ASSET_ID);

const q = (el, selector) => el.shadowRoot.querySelector(selector);
const qa = (el, selector) => [...el.shadowRoot.querySelectorAll(selector)];
const text = (el) => el.shadowRoot.textContent.replace(/\s+/g, " ");
const combo = (el, name) =>
  qa(el, "lightning-combobox").find((c) => c.name === name);
const input = (el, type) =>
  qa(el, "lightning-input").find((i) => i.type === type);
const button = (el, label) =>
  qa(el, "lightning-button").find((b) => b.label === label);
const change = async (node, value) => {
  node.dispatchEvent(new CustomEvent("change", { detail: { value } }));
  await settle();
};
const click = async (node) => {
  node.click();
  await settle();
};
const grid = (el) => q(el, "lightning-datatable");

// Chooses a CSV through the hidden <input type="file"> and waits for the
// FileReader callback and the validation call that follows.
const chooseCsv = async (el, content, name = "usage.csv") => {
  const fileInput = q(el, '[data-id="csv-file-input"]');
  Object.defineProperty(fileInput, "files", {
    value: [new File([content], name, { type: "text/csv" })],
    configurable: true
  });
  fileInput.dispatchEvent(new CustomEvent("change"));
  await settle(50);
  await settle(50);
};
const csv = (...rows) => [CSV_HEADER, ...rows].join("\n");
const allValid = (entries) => entries.map(() => ({ isValid: true }));

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(2025, 5, 15, 12, 0, 0));
  [uploadUsage, validateUsageEntries, bulkUploadUsage].forEach((fn) =>
    fn.mockReset()
  );
  validateUsageEntries.mockImplementation(async ({ entries }) =>
    allValid(entries)
  );
});

afterEach(() => {
  clearDocument();
  jest.clearAllTimers();
  jest.useRealTimers();
});

describe("c-rlm-usage-uploader: render (Asset context)", () => {
  it("shows the spinner until usage resources arrive", async () => {
    const { el } = await mountOn(ASSET_ID, { resources: null });

    expect(q(el, "lightning-spinner")).not.toBeNull();
    expect(qa(el, "lightning-tab")).toHaveLength(0);
    // No asset picker outside the Account context
    expect(combo(el, "assetPicker")).toBeUndefined();
  });

  it("defaults the form to the first resource, its unit, quantity 1 and today", async () => {
    const { el } = await mountAsset();

    expect(q(el, "lightning-spinner")).toBeNull();
    expect(combo(el, "usageResource").value).toBe("UR1");
    expect(combo(el, "usageResource").options).toEqual([
      { label: "API Calls", value: "UR1" },
      { label: "Storage, GB", value: "UR2" }
    ]);
    expect(combo(el, "unitOfMeasure").options).toEqual([
      { label: "Call (CALL)", value: "U1" },
      { label: "Kilo-call (KCALL)", value: "U2" }
    ]);
    expect(combo(el, "unitOfMeasure").value).toBe("U1");
    expect(input(el, "number").value).toBe(1);
    expect(input(el, "date").value).toBe(TODAY);
    expect(button(el, "Upload Usage").disabled).toBe(false);
    expect(q(el, "c-rlm-asset-rates-grants")).not.toBeNull();
  });

  it("says so when the asset has no active usage resources", async () => {
    const { el } = await mountOn(ASSET_ID, { resources: [] });

    expect(text(el)).toContain(
      "No active usage resources found for this product."
    );
    expect(qa(el, "lightning-tab")).toHaveLength(0);
  });

  it("shows the Apex error when resources fail to load and clears it on recovery", async () => {
    const { el } = await mountOn(ASSET_ID, { resources: null });

    getUsageResourcesForAsset.emitError({
      body: { message: "No access to usage resources" }
    });
    await settle();
    expect(q(el, '[role="alert"]').textContent).toContain(
      "No access to usage resources"
    );
    expect(q(el, "lightning-spinner")).toBeNull();
    expect(text(el)).not.toContain("No active usage resources found");

    getUsageResourcesForAsset.emit(RESOURCES);
    await settle();
    expect(q(el, '[role="alert"]')).toBeNull();
    expect(combo(el, "usageResource")).toBeDefined();
  });
});

describe("c-rlm-usage-uploader: Account context and asset picker", () => {
  it("waits for an asset choice before showing the upload form", async () => {
    const { el } = await mountOn(ACCOUNT_ID, {
      assets: ASSETS,
      resources: null
    });

    expect(combo(el, "assetPicker").options).toEqual([
      { label: "Asset A (Platform)", value: ASSET_ID },
      { label: "Asset B (Storage)", value: "02i000000000002AAA" }
    ]);
    expect(qa(el, "lightning-tab")).toHaveLength(0);
    expect(q(el, "lightning-spinner")).toBeNull();
  });

  it("shows the no-assets alert when the account has none", async () => {
    const { el } = await mountOn(ACCOUNT_ID, { assets: [], resources: null });

    expect(q(el, '[role="alert"]').textContent).toContain(
      "No active assets found on this account with Anchor products."
    );
    expect(combo(el, "assetPicker")).toBeUndefined();
  });

  it("toasts the Apex message when assets fail to load", async () => {
    const el = mountComponent(TAG, RlmUsageUploader, { recordId: ACCOUNT_ID });
    const toasts = [];
    el.addEventListener("lightning__showtoast", (e) => toasts.push(e.detail));

    getAssetsForAccount.emitError({ body: { message: "Sharing blocked" } });
    await settle();

    expect(toasts).toEqual([
      expect.objectContaining({
        title: "Error",
        message: "Failed to load assets: Sharing blocked",
        variant: "error"
      })
    ]);
    expect(q(el, '[role="alert"]')).not.toBeNull();
  });

  it("loads that asset's resources after it is chosen, then resets when another is picked", async () => {
    const { el } = await mountOn(ACCOUNT_ID, {
      assets: ASSETS,
      resources: null
    });

    await change(combo(el, "assetPicker"), ASSET_ID);
    expect(q(el, "lightning-spinner")).not.toBeNull();
    getUsageResourcesForAsset.emit(RESOURCES);
    await settle();
    expect(combo(el, "usageResource").value).toBe("UR1");

    await change(input(el, "number"), "9");
    await change(combo(el, "assetPicker"), "02i000000000002AAA");

    // Stale resources from the first asset are gone until the wire answers.
    expect(qa(el, "lightning-tab")).toHaveLength(0);
    expect(q(el, "lightning-spinner")).not.toBeNull();
  });
});

describe("c-rlm-usage-uploader: single entry upload", () => {
  it("uploads one usage record, announces it with a link and resets the form", async () => {
    uploadUsage.mockResolvedValue("0TJ000000000001AAA");
    const { el, toasts } = await mountAsset();
    await change(combo(el, "usageResource"), "UR2");
    await change(input(el, "number"), "2.5");
    await change(input(el, "date"), "2025-06-10");
    expect(combo(el, "unitOfMeasure").value).toBe("U3");

    await click(button(el, "Upload Usage"));

    expect(uploadUsage).toHaveBeenCalledWith({
      assetId: ASSET_ID,
      usageResourceId: "UR2",
      quantity: 2.5,
      transactionDate: "2025-06-10",
      unitOfMeasureId: "U3"
    });
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      title: "Success",
      variant: "success",
      messageData: [
        {
          url: "/lightning/r/TransactionJournal/0TJ000000000001AAA/view",
          label: "View Transaction Journal"
        }
      ]
    });
    // form back to defaults
    expect(combo(el, "usageResource").value).toBe("UR1");
    expect(input(el, "number").value).toBe(1);
    expect(input(el, "date").value).toBe(TODAY);
  });

  it("shows Uploading... and blocks a second click while the call is pending", async () => {
    let finish;
    uploadUsage.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      })
    );
    const { el } = await mountAsset();

    await click(button(el, "Upload Usage"));
    expect(button(el, "Uploading...").disabled).toBe(true);
    await click(button(el, "Uploading..."));
    expect(uploadUsage).toHaveBeenCalledTimes(1);

    finish("0TJ000000000002AAA");
    await settle();
    expect(button(el, "Upload Usage").disabled).toBe(false);
  });

  it("keeps the form and toasts the Apex error when the upload fails", async () => {
    uploadUsage.mockRejectedValue({ body: { message: "Asset is not active" } });
    const { el, toasts } = await mountAsset();
    await change(input(el, "number"), "4");

    await click(button(el, "Upload Usage"));

    expect(toasts).toEqual([
      expect.objectContaining({
        title: "Error",
        message: "Asset is not active",
        variant: "error"
      })
    ]);
    expect(input(el, "number").value).toBe("4");
    expect(button(el, "Upload Usage").disabled).toBe(false);
  });

  it("disables Upload until a quantity is entered and ignores a forced click", async () => {
    const { el } = await mountAsset();

    await change(input(el, "number"), "");

    expect(button(el, "Upload Usage").disabled).toBe(true);
    // The click handler re-checks the same rule.
    button(el, "Upload Usage").click();
    await settle();
    expect(uploadUsage).not.toHaveBeenCalled();
  });

  it("passes no unit when the chosen resource has none", async () => {
    uploadUsage.mockResolvedValue("0TJ000000000003AAA");
    const { el } = await mountOn(ASSET_ID, {
      resources: [
        {
          resourceId: "UR9",
          resourceName: "Seats",
          unitOfMeasureId: null,
          availableUoms: []
        }
      ]
    });
    expect(combo(el, "unitOfMeasure")).toBeUndefined();

    await click(button(el, "Upload Usage"));

    expect(uploadUsage.mock.calls[0][0].unitOfMeasureId).toBeNull();
  });

  it("reduces string, Error and array-shaped failures to a message", async () => {
    const { el, toasts } = await mountAsset();
    uploadUsage.mockRejectedValueOnce("plain string");
    await click(button(el, "Upload Usage"));
    uploadUsage.mockRejectedValueOnce(new Error("boom"));
    await click(button(el, "Upload Usage"));
    uploadUsage.mockRejectedValueOnce({
      body: [{ message: "a" }, { message: "b" }]
    });
    await click(button(el, "Upload Usage"));
    uploadUsage.mockRejectedValueOnce({});
    await click(button(el, "Upload Usage"));

    expect(toasts.map((t) => t.message)).toEqual([
      "plain string",
      "boom",
      "a, b",
      "Unknown error"
    ]);
  });
});

describe("c-rlm-usage-uploader: CSV upload", () => {
  it("offers a drop zone and no preview before a file is chosen", async () => {
    const { el } = await mountAsset();

    expect(q(el, ".slds-file-selector__dropzone")).not.toBeNull();
    expect(text(el)).toContain(
      "Required columns: Usage Resource, Quantity, Transaction Date."
    );
    expect(grid(el)).toBeNull();
  });

  it("parses the file, validates every row and shows a preview with counts", async () => {
    validateUsageEntries.mockResolvedValue([
      { isValid: true },
      { isValid: false, errorMessage: "Unknown usage resource" }
    ]);
    const { el } = await mountAsset();

    await chooseCsv(el, csv("API Calls,10,2025-03-05", "Nope,2,2025-03-06"));

    expect(validateUsageEntries).toHaveBeenCalledTimes(1);
    const sent = validateUsageEntries.mock.calls[0][0];
    expect(sent.assetId).toBe(ASSET_ID);
    expect(sent.entries).toEqual([
      {
        usageResourceId: "UR1",
        usageResourceName: "API Calls",
        quantity: 10,
        transactionDate: "2025-03-05"
      },
      {
        usageResourceId: null,
        usageResourceName: "Nope",
        quantity: 2,
        transactionDate: "2025-03-06"
      }
    ]);
    expect(text(el)).toContain("Preview: usage.csv");
    expect(text(el)).toContain("2 row(s) • 1 valid • 1 error(s)");
    expect(grid(el).data.map((r) => r.statusIcon)).toEqual([
      "✅ Valid",
      "❌ Unknown usage resource"
    ]);
    expect(grid(el).data[1]._cssClass).toBe("slds-text-color_error");
    // Confirm stays available while at least one row is valid
    expect(button(el, "Confirm Upload").disabled).toBe(false);
  });

  it("normalises header aliases, quoted names, thousands separators and date formats", async () => {
    const { el } = await mountAsset();

    await chooseCsv(
      el,
      [
        "﻿Resource,Qty,Date",
        '"Storage, GB","1,250.5",03/15/2025',
        "API Calls,3,15/03/2025",
        "API Calls,4,March 30 2026",
        "API Calls,5,30-Mar-2026",
        "API Calls,6,3/5/25",
        "API Calls,7,2025/07/04",
        "API Calls,abc,not-a-date"
      ].join("\r\n")
    );

    const rows = validateUsageEntries.mock.calls[0][0].entries;
    expect(
      rows.map((r) => [r.usageResourceName, r.quantity, r.transactionDate])
    ).toEqual([
      ["Storage, GB", 1250.5, "2025-03-15"],
      ["API Calls", 3, "2025-03-15"],
      ["API Calls", 4, "2026-03-30"],
      ["API Calls", 5, "2026-03-30"],
      ["API Calls", 6, "2025-03-05"],
      ["API Calls", 7, "2025-07-04"],
      ["API Calls", 0, null]
    ]);
    expect(rows[0].usageResourceId).toBe("UR2");
  });

  it("rejects a file without the required columns", async () => {
    const { el, toasts } = await mountAsset();

    await chooseCsv(el, "Name,Count\nA,1");

    expect(toasts[0]).toMatchObject({ variant: "error" });
    expect(toasts[0].message).toContain(
      "CSV must contain columns: Usage Resource"
    );
    expect(validateUsageEntries).not.toHaveBeenCalled();
    expect(grid(el)).toBeNull();
  });

  it("rejects a file with only a header row", async () => {
    const { el, toasts } = await mountAsset();

    await chooseCsv(el, CSV_HEADER);

    expect(toasts[0].message).toBe(
      "CSV file must have a header row and at least one data row."
    );
    expect(grid(el)).toBeNull();
  });

  it("reports a failed validation call and keeps the rows as pending", async () => {
    validateUsageEntries.mockRejectedValue({
      body: { message: "Validator offline" }
    });
    const { el, toasts } = await mountAsset();

    await chooseCsv(el, csv("API Calls,1,2025-03-05"));

    expect(toasts.at(-1).message).toBe("Validation failed: Validator offline");
    expect(grid(el).data[0].statusIcon).toBe("⏳ Pending");
    expect(button(el, "Confirm Upload").disabled).toBe(true);
  });

  it("disables Confirm when every row is invalid", async () => {
    validateUsageEntries.mockResolvedValue([
      { isValid: false, errorMessage: "bad" }
    ]);
    const { el } = await mountAsset();

    await chooseCsv(el, csv("API Calls,1,2025-03-05"));

    expect(button(el, "Confirm Upload").disabled).toBe(true);
  });

  it("bulk uploads the validated rows, then returns to the drop zone", async () => {
    bulkUploadUsage.mockResolvedValue({
      successCount: 2,
      errorCount: 0,
      errors: []
    });
    const { el, toasts } = await mountAsset();
    await chooseCsv(
      el,
      csv("API Calls,1,2025-03-05", '"Storage, GB",2,2025-03-06')
    );

    await click(button(el, "Confirm Upload"));

    expect(bulkUploadUsage).toHaveBeenCalledTimes(1);
    expect(
      bulkUploadUsage.mock.calls[0][0].entries.map((e) => e.usageResourceId)
    ).toEqual(["UR1", "UR2"]);
    expect(toasts.at(-1)).toMatchObject({
      title: "Success",
      message: "2 usage record(s) created successfully.",
      variant: "success"
    });
    expect(grid(el)).toBeNull();
    expect(q(el, ".slds-file-selector__dropzone")).not.toBeNull();
  });

  it("shows Uploading... while the bulk call is pending and locks Confirm", async () => {
    let finish;
    bulkUploadUsage.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      })
    );
    const { el } = await mountAsset();
    await chooseCsv(el, csv("API Calls,1,2025-03-05"));

    await click(button(el, "Confirm Upload"));
    expect(button(el, "Uploading...").disabled).toBe(true);
    expect(bulkUploadUsage).toHaveBeenCalledTimes(1);

    finish({ successCount: 1, errorCount: 0 });
    await settle();
    expect(grid(el)).toBeNull();
  });

  it("warns about partial success and logs the row errors", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    bulkUploadUsage.mockResolvedValue({
      successCount: 1,
      errorCount: 1,
      errors: ["Row 2: quantity must be positive"]
    });
    const { el, toasts } = await mountAsset();
    await chooseCsv(
      el,
      csv("API Calls,1,2025-03-05", "API Calls,-1,2025-03-06")
    );

    await click(button(el, "Confirm Upload"));

    expect(toasts.at(-1)).toMatchObject({
      variant: "warning",
      message: "1 usage record(s) created successfully. 1 row(s) had errors."
    });
    expect(errorSpy).toHaveBeenCalledWith("Bulk upload errors:", [
      "Row 2: quantity must be positive"
    ]);
    errorSpy.mockRestore();
  });

  it("keeps the preview and toasts when the bulk call fails", async () => {
    bulkUploadUsage.mockRejectedValue({ body: { message: "Governor limit" } });
    const { el, toasts } = await mountAsset();
    await chooseCsv(el, csv("API Calls,1,2025-03-05"));

    await click(button(el, "Confirm Upload"));

    expect(toasts.at(-1).message).toBe("Bulk upload failed: Governor limit");
    expect(grid(el)).not.toBeNull();
    expect(button(el, "Confirm Upload").disabled).toBe(false);
  });

  it("discards the preview on Cancel and empties the file input", async () => {
    const { el } = await mountAsset();
    await chooseCsv(el, csv("API Calls,1,2025-03-05"));
    expect(grid(el)).not.toBeNull();

    await click(button(el, "Cancel"));

    expect(grid(el)).toBeNull();
    expect(q(el, '[data-id="csv-file-input"]').value).toBe("");
  });

  it("does nothing when the file chooser is cancelled", async () => {
    const { el } = await mountAsset();
    const fileInput = q(el, '[data-id="csv-file-input"]');
    Object.defineProperty(fileInput, "files", {
      value: [],
      configurable: true
    });

    fileInput.dispatchEvent(new CustomEvent("change"));
    await settle();

    expect(validateUsageEntries).not.toHaveBeenCalled();
    expect(grid(el)).toBeNull();
  });
});

describe("c-rlm-usage-uploader: drag and drop and the drop zone", () => {
  const dropzone = (el) => q(el, ".slds-file-selector__dropzone");
  const drop = async (el, file) => {
    const event = new CustomEvent("drop", { bubbles: true, cancelable: true });
    event.dataTransfer = { files: file ? [file] : [] };
    dropzone(el).dispatchEvent(event);
    await settle(50);
    await settle(50);
    return event;
  };

  it("highlights the zone while dragging over and clears it on leave", async () => {
    const { el } = await mountAsset();

    dropzone(el).dispatchEvent(
      new CustomEvent("dragover", { cancelable: true })
    );
    await settle();
    expect(dropzone(el).classList.contains("slds-has-drag-over")).toBe(true);

    dropzone(el).dispatchEvent(new CustomEvent("dragleave"));
    await settle();
    expect(dropzone(el).classList.contains("slds-has-drag-over")).toBe(false);
  });

  it("processes a dropped .csv (case-insensitive) and clears the highlight", async () => {
    const { el } = await mountAsset();
    dropzone(el).dispatchEvent(
      new CustomEvent("dragover", { cancelable: true })
    );

    await drop(el, new File([csv("API Calls,1,2025-03-05")], "USAGE.CSV"));

    expect(text(el)).toContain("Preview: USAGE.CSV");
    expect(validateUsageEntries).toHaveBeenCalledTimes(1);
  });

  it("refuses a dropped file that is not a CSV", async () => {
    const { el, toasts } = await mountAsset();

    const event = await drop(el, new File(["x"], "notes.txt"));

    expect(event.defaultPrevented).toBe(true);
    expect(toasts).toEqual([
      expect.objectContaining({
        message: "Please drop a CSV file.",
        variant: "error"
      })
    ]);
    expect(validateUsageEntries).not.toHaveBeenCalled();
  });

  it("ignores a drop that carries no files", async () => {
    const { el, toasts } = await mountAsset();

    await drop(el, null);

    expect(toasts).toHaveLength(0);
  });

  it("opens the file picker from a click, Enter or Space on the drop-zone button", async () => {
    const { el } = await mountAsset();
    const fileInput = q(el, '[data-id="csv-file-input"]');
    fileInput.click = jest.fn();
    const target = q(el, ".slds-file-selector__body");

    target.click();
    target.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", cancelable: true })
    );
    const space = new KeyboardEvent("keydown", { key: " ", cancelable: true });
    target.dispatchEvent(space);
    target.dispatchEvent(
      new KeyboardEvent("keydown", { key: "a", cancelable: true })
    );

    expect(fileInput.click).toHaveBeenCalledTimes(3);
    expect(space.defaultPrevented).toBe(true);
  });
});

describe("c-rlm-usage-uploader: sample CSV download", () => {
  it("builds a template with one row per usage resource and triggers a download", async () => {
    const { el } = await mountAsset();
    const link = { setAttribute: jest.fn(), click: jest.fn() };
    const realCreate = document.createElement.bind(document);
    const createSpy = jest
      .spyOn(document, "createElement")
      .mockImplementation((tag, ...rest) => {
        if (tag === "a") return link;
        return realCreate(tag, ...rest);
      });

    button(el, "Download Sample CSV").click();
    createSpy.mockRestore();

    const attrs = Object.fromEntries(link.setAttribute.mock.calls);
    expect(attrs.download).toBe("usage_upload_template.csv");
    const body = decodeURIComponent(
      attrs.href.replace("data:text/csv;charset=utf-8,", "")
    );
    expect(body.split("\n")).toEqual([
      "Usage Resource,Quantity,Transaction Date",
      `API Calls,1,${TODAY}`,
      `"Storage, GB",1,${TODAY}`
    ]);
    expect(link.click).toHaveBeenCalledTimes(1);
  });
});

describe("c-rlm-usage-uploader: tabs", () => {
  it("tracks the active tab from the tabset's change event", async () => {
    const { el } = await mountAsset();
    const tabset = q(el, "lightning-tabset");
    expect(tabset.activeTabValue).toBe("single");

    tabset.dispatchEvent(
      new CustomEvent("change", { detail: { value: "csv" } })
    );
    await settle();

    expect(tabset.activeTabValue).toBe("csv");
  });
});

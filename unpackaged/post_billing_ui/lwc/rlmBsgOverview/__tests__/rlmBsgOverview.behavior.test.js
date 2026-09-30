import RlmBsgOverview from "c/rlmBsgOverview";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";
import { refreshApex } from "@salesforce/apex";
import getBillingScheduleGroupData from "@salesforce/apex/RLM_BSGTimelineController.getBillingScheduleGroupData";
import getConsolidatedTimeline from "@salesforce/apex/RLM_BSGTimelineController.getConsolidatedTimeline";

jest.mock(
  "@salesforce/apex",
  () => ({ refreshApex: jest.fn(() => Promise.resolve()) }),
  { virtual: true }
);
jest.mock(
  "@salesforce/apex/RLM_BSGTimelineController.getBillingScheduleGroupData",
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
  "@salesforce/apex/RLM_BSGTimelineController.getConsolidatedTimeline",
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

const TAG = "c-rlm-bsg-overview";

// Mid-month, midday UTC so the month a date falls in does not depend on the
// machine's timezone.
const at = (month, day = 15) =>
  `2025-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}T12:00:00.000Z`;

const schedule = (overrides = {}) => ({
  id: "BS1",
  scheduleNumber: "BS-001",
  category: "Original",
  status: "Active",
  startDate: at(1),
  endDate: at(6),
  billingTermUnit: "Month",
  billingTerm: 1,
  billingPeriodAmount: 100,
  billedAmount: 300,
  pendingAmount: 300,
  totalAmount: 600,
  quantity: 2,
  unitPrice: 50,
  netUnitPrice: 50,
  nextBillingDate: at(4),
  billingType: "Advance",
  billingMethod: "Invoice",
  ...overrides
});

const MONTHLY_BSG = {
  totalBilledAmount: 300,
  totalPendingAmount: 300,
  billingSchedules: [schedule()]
};

const SEGMENTS = [
  {
    startDate: at(1),
    endDate: at(6),
    status: "Active",
    activeScheduleIds: ["BS1"],
    activeScheduleNumbers: ["BS-001"],
    netQuantity: 2,
    periodicBilling: 100,
    credits: 0
  }
];

const mount = () =>
  mountComponent(TAG, RlmBsgOverview, { recordId: "001000000000001AAA" });

const load = async (bsg, segments = SEGMENTS) => {
  const el = mount();
  getBillingScheduleGroupData.emit(bsg);
  getConsolidatedTimeline.emit(segments);
  await flushPromises();
  return el;
};

const q = (el, selector) => el.shadowRoot.querySelector(selector);
const qa = (el, selector) => [...el.shadowRoot.querySelectorAll(selector)];
const text = (el) => el.shadowRoot.textContent.replace(/\s+/g, " ");
const summary = (el) =>
  Object.fromEntries(
    qa(el, ".summary-card").map((card) => [
      card.querySelector(".summary-label").textContent.trim(),
      card.querySelector(".summary-value").textContent.trim()
    ])
  );
const xLabels = (el) =>
  qa(el, ".x-axis-label").map((n) => n.textContent.trim());
const tableRows = (el) =>
  qa(el, ".segments-table tbody tr").map((tr) =>
    [...tr.querySelectorAll("td")].map((td) => td.textContent.trim())
  );
const viewButton = (el, label) =>
  qa(el, "lightning-button").find((b) => b.label === label);

afterEach(() => {
  clearDocument();
  jest.clearAllMocks();
});

describe("c-rlm-bsg-overview: render", () => {
  it("shows a spinner and no summary until both wires have answered", async () => {
    const el = mount();
    await flushPromises();

    expect(q(el, "lightning-spinner")).not.toBeNull();
    expect(qa(el, ".summary-card")).toHaveLength(0);
  });

  it("renders summary cards, the monthly bar chart and the billing table", async () => {
    const el = await load(MONTHLY_BSG);

    expect(q(el, "lightning-spinner")).toBeNull();
    expect(summary(el)).toEqual({
      "Total Billed": "$300.00",
      "Total Pending": "$300.00",
      "Net Quantity": "2",
      "Billing Completion": "50.0%"
    });
    expect(xLabels(el)).toEqual([
      "Jan '25",
      "Feb '25",
      "Mar '25",
      "Apr '25",
      "May '25",
      "Jun '25"
    ]);
    const rows = tableRows(el);
    expect(rows).toHaveLength(6);
    expect(rows.map((r) => r[5])).toEqual([
      "Billed",
      "Billed",
      "Billed",
      "Pending",
      "Pending",
      "Pending"
    ]);
    expect(rows[0]).toEqual([
      "Jan '25",
      "2",
      "$100.00",
      "--",
      "BS-001",
      "Billed"
    ]);
    // y axis runs from the tallest bar down to zero
    expect(qa(el, ".y-axis-label").map((n) => n.textContent.trim())).toEqual([
      "$100.00",
      "$75.00",
      "$50.00",
      "$25.00",
      "$0.00"
    ]);
  });

  it("charts a partially billed period as Partial via the table status", async () => {
    const el = await load({
      ...MONTHLY_BSG,
      billingSchedules: [schedule({ billedAmount: 150 })]
    });

    expect(tableRows(el).map((r) => r[5])).toEqual([
      "Billed",
      "Partial",
      "Pending",
      "Pending",
      "Pending",
      "Pending"
    ]);
  });

  it("charts milestone billing by completion date with an Event bucket for undated items", async () => {
    const el = await load(
      {
        totalBilledAmount: 500,
        totalPendingAmount: 700,
        billingSchedules: [
          schedule({
            billingTermUnit: "Milestone",
            startDate: at(1),
            endDate: at(12)
          })
        ],
        milestoneItems: [
          { id: "M2", name: "Go live", amount: 700, status: "Pending" },
          {
            id: "M1",
            name: "Kick-off",
            amount: 500,
            status: "Invoiced",
            completionDate: at(2)
          }
        ]
      },
      [] // milestone charts do not depend on consolidated segments
    );

    expect(xLabels(el)).toEqual(["Feb 15, 25", "Event"]);
    expect(tableRows(el).map((r) => [r[2], r[5]])).toEqual([
      ["$500.00", "Billed"],
      ["$700.00", "Pending"]
    ]);
  });

  it("marks suspended periods and shows the suspension overlay and legend", async () => {
    const el = await load({
      ...MONTHLY_BSG,
      suspensionDate: at(3, 1),
      resumptionDate: at(5, 20)
    });

    expect(q(el, ".chart-suspension-overlay")).not.toBeNull();
    expect(qa(el, ".suspended-bar").length).toBeGreaterThan(0);
    const statuses = tableRows(el).map((r) => r[5]);
    expect(statuses).toContain("Suspended");
    expect(text(el)).toContain("Suspended");
    // Suspended billing is carried forward and shown as $0.00
    expect(tableRows(el).find((r) => r[5] === "Suspended")[2]).toBe("$0.00");
  });

  it("shows the end-date marker and prorates the final period", async () => {
    const el = await load({
      ...MONTHLY_BSG,
      endDate: at(4, 10)
    });

    expect(q(el, ".bsg-end-marker")).not.toBeNull();
    expect(text(el)).toContain("End: Apr 10, 2025");
    const rows = tableRows(el);
    expect(rows.find((r) => r[0] === "Apr '25")[2]).toContain("(prorated)");
    expect(rows.find((r) => r[0] === "May '25")[5]).toBe("Past End Date");
  });

  it("buckets quarterly and yearly schedules on their own frequency", async () => {
    const el = await load({
      ...MONTHLY_BSG,
      billingSchedules: [
        schedule({
          billingTermUnit: "Quarterly",
          startDate: at(1),
          endDate: at(9)
        })
      ]
    });

    expect(xLabels(el)).toEqual(["Jan-Mar '25", "Apr-Jun '25", "Jul-Sep '25"]);
  });

  it("collapses a one-time schedule into a single bucket", async () => {
    const el = await load({
      totalBilledAmount: 0,
      totalPendingAmount: 250,
      billingSchedules: [
        schedule({
          billingTermUnit: "OneTime",
          billedAmount: 0,
          pendingAmount: 250
        })
      ]
    });

    expect(xLabels(el)).toEqual(["One-Time"]);
    expect(tableRows(el)[0][5]).toBe("Pending");
  });

  it("switches to a scrolling chart when there are more than twelve periods", async () => {
    const el = await load({
      ...MONTHLY_BSG,
      billingSchedules: [
        schedule({
          startDate: "2025-01-15T12:00:00.000Z",
          endDate: "2026-06-15T12:00:00.000Z"
        })
      ]
    });

    expect(xLabels(el)).toHaveLength(18);
    expect(q(el, ".chart-plot-area").classList.contains("crowded")).toBe(true);
  });
});

describe("c-rlm-bsg-overview: empty state", () => {
  it("shows zeroed summary cards and no table when there are no schedules or segments", async () => {
    const el = await load(
      { totalBilledAmount: 0, totalPendingAmount: 0, billingSchedules: [] },
      []
    );

    expect(summary(el)).toEqual({
      "Total Billed": "$0.00",
      "Total Pending": "$0.00",
      "Net Quantity": "0",
      "Billing Completion": "0.0%"
    });
    expect(q(el, ".segments-table")).toBeNull();
    expect(xLabels(el)).toEqual([]);
    expect(qa(el, ".y-axis-label")).toHaveLength(0);
  });

  it("shows no Gantt rows for an empty schedule list", async () => {
    const el = await load(
      { totalBilledAmount: 0, totalPendingAmount: 0, billingSchedules: [] },
      []
    );

    viewButton(el, "Billing Schedules").click();
    await flushPromises();

    expect(qa(el, ".schedule-row")).toHaveLength(0);
    expect(q(el, ".timeline-container")).toBeNull();
  });
});

describe("c-rlm-bsg-overview: wire errors", () => {
  it("shows the Apex message and no summary when the BSG wire fails", async () => {
    const el = mount();

    getBillingScheduleGroupData.emitError({
      body: { message: "Insufficient privileges" },
      status: 403
    });
    await flushPromises();

    expect(text(el)).toContain("Insufficient privileges");
    expect(qa(el, ".summary-card")).toHaveLength(0);
    expect(q(el, "lightning-spinner")).toBeNull();
  });

  it("falls back to a generic message when the error has no body", async () => {
    const el = mount();

    getBillingScheduleGroupData.emitError({ body: {} });
    await flushPromises();
    expect(text(el)).toContain("An error occurred loading the BSG data");

    getConsolidatedTimeline.emitError({ body: {} });
    await flushPromises();
    expect(text(el)).toContain(
      "An error occurred loading the consolidated data"
    );
  });

  it("clears the chart and reports the timeline error even after data had loaded", async () => {
    const el = await load(MONTHLY_BSG);
    expect(tableRows(el)).toHaveLength(6);

    getConsolidatedTimeline.emitError({ body: { message: "Timeline failed" } });
    await flushPromises();

    expect(text(el)).toContain("Timeline failed");
    expect(tableRows(el)).toHaveLength(0);
  });

  it("recovers when a later emission succeeds", async () => {
    const el = mount();
    getBillingScheduleGroupData.emitError({ body: { message: "boom" } });
    await flushPromises();
    expect(text(el)).toContain("boom");

    getBillingScheduleGroupData.emit(MONTHLY_BSG);
    getConsolidatedTimeline.emit(SEGMENTS);
    await flushPromises();

    expect(text(el)).not.toContain("boom");
    expect(summary(el)["Total Billed"]).toBe("$300.00");
  });
});

describe("c-rlm-bsg-overview: switching view and inspecting a schedule", () => {
  const openTimeline = async () => {
    const el = await load(MONTHLY_BSG);
    viewButton(el, "Billing Schedules").click();
    await flushPromises();
    return el;
  };
  const scheduleLink = (el) => q(el, "lightning-button.schedule-link");

  it("swaps the period chart for the schedule timeline and highlights the active tab", async () => {
    const el = await load(MONTHLY_BSG);
    expect(viewButton(el, "Billings by Period").variant).toBe("brand");
    expect(viewButton(el, "Billing Schedules").variant).toBe("neutral");

    viewButton(el, "Billing Schedules").click();
    await flushPromises();

    expect(q(el, ".chart-container")).toBeNull();
    expect(viewButton(el, "Billing Schedules").variant).toBe("brand");
    expect(qa(el, ".month-label").map((n) => n.textContent.trim())).toEqual([
      "Jan 25",
      "Feb 25",
      "Mar 25",
      "Apr 25",
      "May 25",
      "Jun 25"
    ]);
    expect(scheduleLink(el).label).toBe("BS-001");
    expect(q(el, ".bar-amount").textContent.trim()).toBe("$100.00/mo");

    viewButton(el, "Billings by Period").click();
    await flushPromises();
    expect(q(el, ".chart-container")).not.toBeNull();
  });

  it("opens the schedule detail panel on click and closes it again", async () => {
    const el = await openTimeline();
    expect(q(el, ".bs-detail-panel")).toBeNull();

    scheduleLink(el).click();
    await flushPromises();

    const panel = q(el, ".bs-detail-panel");
    expect(panel).not.toBeNull();
    const detail = text(el);
    expect(detail).toContain("BS-001");
    expect(detail).toContain("Total Amount$600.00");
    expect(detail).toContain("Billed Amount$300.00");
    expect(detail).toContain("Start DateJan 15, 2025");
    expect(detail).toContain("Billing Term UnitMonth");
    expect(q(el, ".progress-bar-filled").textContent.trim()).toBe("50%");
    expect(q(el, ".badge-active").textContent.trim()).toBe("Active");

    qa(el, "lightning-button-icon")
      .find((b) => b.alternativeText === "Close")
      .click();
    await flushPromises();
    expect(q(el, ".bs-detail-panel")).toBeNull();
  });

  it("humanises camel-case status labels and maps them to badge classes", async () => {
    const el = await load({
      ...MONTHLY_BSG,
      billingSchedules: [
        schedule({ status: "CompletelyBilled", category: "Amendment" })
      ]
    });
    viewButton(el, "Billing Schedules").click();
    await flushPromises();

    scheduleLink(el).click();
    await flushPromises();

    expect(q(el, ".badge-billed").textContent.trim()).toBe("Completely Billed");
  });

  it("shows the suspension overlay on the timeline for a suspended BSG", async () => {
    const el = await load({
      ...MONTHLY_BSG,
      suspensionDate: at(3, 1),
      resumptionDate: at(4, 20)
    });
    viewButton(el, "Billing Schedules").click();
    await flushPromises();

    expect(q(el, ".suspension-overlay")).not.toBeNull();
    expect(q(el, ".suspension-overlay").getAttribute("style")).toContain(
      "calc(200px"
    );
  });
});

describe("c-rlm-bsg-overview: refresh", () => {
  const refreshButton = (el) =>
    qa(el, "lightning-button-icon").find(
      (b) => b.alternativeText === "Refresh"
    );

  it("refreshes both wires, shows the spinner and re-renders with the reloaded data", async () => {
    const el = await load(MONTHLY_BSG);
    expect(q(el, "lightning-spinner")).toBeNull();

    refreshButton(el).click();
    await flushPromises();

    expect(refreshApex).toHaveBeenCalledTimes(2);
    expect(q(el, "lightning-spinner")).not.toBeNull();

    // The platform re-provisions the wires after refreshApex resolves.
    getBillingScheduleGroupData.emit({
      ...MONTHLY_BSG,
      totalBilledAmount: 600,
      totalPendingAmount: 0
    });
    getConsolidatedTimeline.emit(SEGMENTS);
    await flushPromises();

    expect(q(el, "lightning-spinner")).toBeNull();
    expect(summary(el)["Billing Completion"]).toBe("100.0%");
  });

  it("drops the spinner and selected schedule when refreshing fails", async () => {
    const el = await load(MONTHLY_BSG);
    viewButton(el, "Billing Schedules").click();
    await flushPromises();
    q(el, "lightning-button.schedule-link").click();
    await flushPromises();
    expect(q(el, ".bs-detail-panel")).not.toBeNull();
    refreshApex.mockRejectedValueOnce(new Error("offline"));

    refreshButton(el).click();
    await flushPromises();
    await flushPromises();

    expect(q(el, ".bs-detail-panel")).toBeNull();
    expect(q(el, "lightning-spinner")).toBeNull();
  });
});

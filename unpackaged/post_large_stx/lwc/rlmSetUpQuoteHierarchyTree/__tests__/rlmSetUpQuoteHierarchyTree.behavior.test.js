import RlmSetUpQuoteHierarchyTree from "c/rlmSetUpQuoteHierarchyTree";
import {
  clearDocument,
  flushPromises,
  mountComponent
} from "@rlm/lwc-test-utils";

const TAG = "c-rlm-set-up-quote-hierarchy-tree";

const TREE = JSON.stringify({
  parents: [
    {
      name: "Hardware",
      children: [
        { name: "Servers", children: [] },
        { name: "Racks", children: [] }
      ]
    },
    { name: "Services", children: [] }
  ]
});

const EXISTING_TREE = JSON.stringify({
  parents: [
    {
      name: "Existing A",
      sfId: "0QG000000000001AAA",
      lineItemCount: 4,
      children: [
        {
          name: "Pending B",
          tempId: "new-1",
          lineItemCount: 0,
          children: []
        }
      ]
    }
  ]
});

const mount = async (props = {}) => {
  const el = mountComponent(TAG, RlmSetUpQuoteHierarchyTree, props);
  await flushPromises();
  return el;
};

const q = (el, selector) => el.shadowRoot.querySelector(selector);
const qa = (el, selector) => [...el.shadowRoot.querySelectorAll(selector)];
const labels = (el) => qa(el, ".tree-label").map((n) => n.textContent.trim());
const live = (el) => JSON.parse(el.getLiveHierarchyJson());
const listen = (el, name) => {
  const handler = jest.fn();
  el.addEventListener(name, handler);
  return handler;
};
const typeInto = (input, value) => {
  input.value = value;
};

afterEach(clearDocument);

describe("c-rlm-set-up-quote-hierarchy-tree: render and empty state", () => {
  it("renders every node of the display hierarchy with folder / file icons", async () => {
    const el = await mount({ displayHierarchyJson: TREE });

    expect(labels(el)).toEqual(["Hardware", "Servers", "Racks", "Services"]);
    const icons = qa(el, "lightning-icon.tree-node-icon").map(
      (i) => i.iconName
    );
    expect(icons).toEqual([
      "utility:open_folder",
      "utility:file",
      "utility:file",
      "utility:file"
    ]);
    expect(q(el, "h3.heading + .row, .tree-root")).not.toBeNull();
  });

  it("shows only the add-parent control when the hierarchy is empty", async () => {
    const el = await mount();

    expect(qa(el, ".tree-row")).toHaveLength(0);
    expect(q(el, ".parent-name-input")).not.toBeNull();
    expect(q(el, "lightning-button.btn-add")).not.toBeNull();
    expect(el.getLiveHierarchyJson()).toBe('{"parents":[]}');
    expect(el.getLiveProductCountsJson()).toBe("{}");
  });

  it("hides add controls and explains the CSV limitation in read-only mode", async () => {
    const el = await mount({
      displayHierarchyJson: TREE,
      readOnlyHierarchy: true
    });

    expect(q(el, ".parent-name-input")).toBeNull();
    expect(qa(el, "lightning-input.child-name")).toHaveLength(0);
    expect(el.shadowRoot.textContent).toContain("Hierarchy from CSV");
    expect(labels(el)).toHaveLength(4);
  });

  it("hides add controls when allowAddNodes is false", async () => {
    const el = await mount({
      displayHierarchyJson: TREE,
      allowAddNodes: false,
      showSectionHeader: false
    });

    expect(q(el, ".parent-name-input")).toBeNull();
    expect(qa(el, "lightning-input.child-name")).toHaveLength(0);
    expect(q(el, "h3.heading")).toBeNull();
  });

  it("ignores malformed hierarchy JSON instead of throwing", async () => {
    const el = await mount({ displayHierarchyJson: "{not json" });

    expect(qa(el, ".tree-row")).toHaveLength(0);
    expect(el.getLiveHierarchyJson()).toBe('{"parents":[]}');
  });

  it("seeds the tree from initialHierarchyJson and, like the wizard's confirm step, appends per-path counts when sync is suppressed", async () => {
    const el = await mount({
      initialHierarchyJson: JSON.stringify({
        parents: [{ name: "Seeded", children: [] }]
      }),
      productCountsJson: JSON.stringify({ 0: 12 }),
      showProductCounts: true,
      suppressSync: true
    });

    expect(labels(el)).toEqual(["Seeded × 12"]);
  });

  it("overwrites a supplied productCountsJson from its own counts unless sync is suppressed", async () => {
    const el = await mount({
      displayHierarchyJson: TREE,
      productCountsJson: JSON.stringify({ 0: 12 })
    });

    expect(el.productCountsJson).toBe("{}");
  });

  it("labels modify-mode rows with line counts and (new) for pending groups", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      modifyExistingMode: true,
      showExistingLineItemCounts: true
    });

    expect(labels(el)).toEqual([
      "Existing A  4 line item(s)",
      "Pending B  0 line item(s) (new)"
    ]);
  });
});

describe("c-rlm-set-up-quote-hierarchy-tree: adding groups", () => {
  it("adds a parent, clears the input and ignores blank names", async () => {
    const el = await mount();
    const input = q(el, ".parent-name-input");
    const add = q(el, "lightning-button.btn-add");

    typeInto(input, "   ");
    add.click();
    await flushPromises();
    expect(qa(el, ".tree-row")).toHaveLength(0);

    typeInto(input, "  Platform ");
    add.click();
    await flushPromises();

    expect(labels(el)).toEqual(["Platform"]);
    expect(input.value).toBe("");
    expect(live(el)).toEqual({
      parents: [{ name: "Platform", path: "0", children: [] }]
    });
    expect(el.hierarchyJson).toBe(el.getLiveHierarchyJson());
  });

  it("adds a parent when Enter is pressed and not on other keys", async () => {
    const el = await mount();
    const input = q(el, ".parent-name-input");
    typeInto(input, "Keyboard");

    input.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    await flushPromises();
    expect(qa(el, ".tree-row")).toHaveLength(0);

    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", cancelable: true })
    );
    await flushPromises();
    expect(labels(el)).toEqual(["Keyboard"]);
  });

  it("adds a subgroup under the chosen path", async () => {
    const el = await mount({ displayHierarchyJson: TREE });
    const childInput = q(
      el,
      'lightning-input.child-name[data-parent-path="1"]'
    );
    const addButton = qa(el, "lightning-button").find(
      (b) => b.label === "Add" && b.dataset.parentPath === "1"
    );

    typeInto(childInput, "Support");
    addButton.click();
    await flushPromises();

    expect(labels(el)).toEqual([
      "Hardware",
      "Servers",
      "Racks",
      "Services",
      "Support"
    ]);
    expect(live(el).parents[1].children[0]).toMatchObject({
      name: "Support",
      path: "1-0"
    });
  });

  it("does not add a subgroup with a blank name", async () => {
    const el = await mount({ displayHierarchyJson: TREE });
    const addButton = qa(el, "lightning-button").find(
      (b) => b.label === "Add" && b.dataset.parentPath === "0"
    );

    addButton.click();
    await flushPromises();

    expect(labels(el)).toHaveLength(4);
  });

  it("dispatches existingtreemutated with a tempId when a subgroup is added in modify mode", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      modifyExistingMode: true
    });
    const mutated = listen(el, "existingtreemutated");
    typeInto(
      q(el, 'lightning-input.child-name[data-parent-path="0"]'),
      "Fresh"
    );

    qa(el, "lightning-button")
      .find((b) => b.label === "Add" && b.dataset.parentPath === "0")
      .click();
    await flushPromises();

    expect(mutated).toHaveBeenCalledTimes(1);
    const sent = JSON.parse(mutated.mock.calls[0][0].detail.hierarchyJson);
    const fresh = sent.parents[0].children.find((c) => c.name === "Fresh");
    expect(fresh.tempId).toMatch(/^new-/);
    expect(fresh.lineItemCount).toBe(0);
    // Modify mode never shows the top-level "Add parent" section.
    expect(q(el, ".parent-name-input")).toBeNull();
  });
});

describe("c-rlm-set-up-quote-hierarchy-tree: selecting, renaming and collapsing", () => {
  const dblclick = async (el, path) => {
    q(el, `.tree-label[data-path="${path}"]`).dispatchEvent(
      new CustomEvent("dblclick", { bubbles: true })
    );
    await flushPromises();
  };

  it("marks a row selected on click and on Enter / Space", async () => {
    const el = await mount({ displayHierarchyJson: TREE });
    const core = (path) => q(el, `.tree-row-core[data-path="${path}"]`);

    core("1").click();
    await flushPromises();
    expect(core("1").getAttribute("aria-selected")).toBe("true");
    expect(core("0").getAttribute("aria-selected")).toBe("false");

    core("0").dispatchEvent(
      new KeyboardEvent("keydown", { key: " ", cancelable: true })
    );
    await flushPromises();
    expect(core("0").getAttribute("aria-selected")).toBe("true");
  });

  it("renames on double-click + blur and notifies the parent in modify mode", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      modifyExistingMode: true
    });
    const mutated = listen(el, "existingtreemutated");

    await dblclick(el, "0");
    const draft = q(el, "lightning-input.tree-rename-input");
    expect(draft.value).toBe("Existing A");
    typeInto(draft, "  Renamed A ");
    draft.dispatchEvent(new CustomEvent("change"));
    draft.dispatchEvent(new CustomEvent("blur"));
    await flushPromises();

    expect(q(el, "lightning-input.tree-rename-input")).toBeNull();
    expect(live(el).parents[0].name).toBe("Renamed A");
    expect(mutated).toHaveBeenCalledTimes(1);
    expect(
      JSON.parse(mutated.mock.calls[0][0].detail.hierarchyJson).parents[0].name
    ).toBe("Renamed A");
  });

  it("keeps the old name when the rename is emptied, unchanged or cancelled with Escape", async () => {
    const el = await mount({ displayHierarchyJson: TREE });

    await dblclick(el, "1");
    let draft = q(el, "lightning-input.tree-rename-input");
    typeInto(draft, "");
    draft.dispatchEvent(new CustomEvent("change"));
    draft.dispatchEvent(new CustomEvent("blur"));
    await flushPromises();
    expect(labels(el)).toContain("Services");

    await dblclick(el, "1");
    draft = q(el, "lightning-input.tree-rename-input");
    draft.dispatchEvent(new CustomEvent("blur"));
    await flushPromises();
    expect(labels(el)).toContain("Services");

    await dblclick(el, "1");
    draft = q(el, "lightning-input.tree-rename-input");
    typeInto(draft, "Discarded");
    draft.dispatchEvent(new CustomEvent("change"));
    draft.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", cancelable: true })
    );
    draft.dispatchEvent(new CustomEvent("blur"));
    await flushPromises();
    expect(q(el, "lightning-input.tree-rename-input")).toBeNull();
    expect(labels(el)).toContain("Services");
    expect(labels(el)).not.toContain("Discarded");
  });

  it("starts a rename from the keyboard with F2 unless renaming is disabled", async () => {
    const el = await mount({ displayHierarchyJson: TREE });
    const f2 = () =>
      q(el, '.tree-row-core[data-path="0"]').dispatchEvent(
        new KeyboardEvent("keydown", { key: "F2", cancelable: true })
      );

    f2();
    await flushPromises();
    expect(q(el, "lightning-input.tree-rename-input")).not.toBeNull();

    const locked = await mount({
      displayHierarchyJson: TREE,
      allowRename: false
    });
    locked.shadowRoot
      .querySelector('.tree-row-core[data-path="0"]')
      .dispatchEvent(
        new KeyboardEvent("keydown", { key: "F2", cancelable: true })
      );
    await flushPromises();
    expect(
      locked.shadowRoot.querySelector("lightning-input.tree-rename-input")
    ).toBeNull();
  });

  it("collapses and re-expands a branch with the +/- toggle", async () => {
    const el = await mount({ displayHierarchyJson: TREE });
    const toggle = () => q(el, 'button.tree-toggle[data-path="0"]');
    expect(toggle().textContent.trim()).toBe("−");

    toggle().click();
    await flushPromises();
    expect(labels(el)).toEqual(["Hardware", "Services"]);
    expect(toggle().textContent.trim()).toBe("+");
    expect(toggle().getAttribute("aria-label")).toBe("Expand");

    toggle().click();
    await flushPromises();
    expect(labels(el)).toHaveLength(4);
  });
});

describe("c-rlm-set-up-quote-hierarchy-tree: deleting existing groups", () => {
  const deleteButtons = (el) => qa(el, "lightning-button-icon.tree-delete-btn");

  it("dispatches existingtreegroupdelete with sfId for server groups and tempId for pending ones", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      modifyExistingMode: true
    });
    const deleted = listen(el, "existingtreegroupdelete");
    expect(deleteButtons(el)).toHaveLength(2);

    deleteButtons(el)[0].click();
    deleteButtons(el)[1].click();
    await flushPromises();

    expect(deleted.mock.calls.map((c) => c[0].detail)).toEqual([
      { sfId: "0QG000000000001AAA" },
      { tempId: "new-1" }
    ]);
  });

  it("shows no delete controls outside modify mode", async () => {
    const el = await mount({ displayHierarchyJson: EXISTING_TREE });

    expect(deleteButtons(el)).toHaveLength(0);
  });
});

describe("c-rlm-set-up-quote-hierarchy-tree: product count editing", () => {
  const countInputs = (el) => qa(el, "lightning-input.tree-count-input");

  it("renders one count input per row with roll-up totals", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      productCountsEditMode: true,
      productCountsJson: JSON.stringify({ "0QG000000000001AAA": 3, "new-1": 2 })
    });

    expect(countInputs(el).map((i) => i.value)).toEqual(["3", "2"]);
    const text = el.shadowRoot.textContent.replace(/\s+/g, " ");
    expect(text).toContain("Subgroups: 1 · On quote: 4");
    // 4 on quote + 3 entered on the parent, plus the pending child's 2.
    expect(text).toContain("Row total: 7");
    expect(text).toContain("Subtree total: 9");
    expect(text).toContain(
      "Combined total (on quote + additions, full tree): 9"
    );
    expect(labels(el)).toEqual(["Existing A", "Pending B (new)"]);
    expect(q(el, "lightning-input.parent-name-input")).toBeNull();
  });

  it("dispatches quotelinepreviewsync and records the entered count", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      productCountsEditMode: true
    });
    const sync = listen(el, "quotelinepreviewsync");
    const first = countInputs(el)[0];

    first.value = "8";
    first.dispatchEvent(new CustomEvent("change"));
    await flushPromises();

    expect(sync).toHaveBeenCalledTimes(1);
    expect(sync.mock.calls[0][0].bubbles).toBe(true);
    expect(JSON.parse(el.getLiveProductCountsJson())).toEqual({
      "0QG000000000001AAA": 8
    });
    expect(el.shadowRoot.textContent).toContain("Row total: 12");
  });

  it("coerces negative or non-numeric entries to zero", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      productCountsEditMode: true
    });
    const first = countInputs(el)[0];

    first.value = "-5";
    first.dispatchEvent(new CustomEvent("change"));
    await flushPromises();
    expect(
      JSON.parse(el.getLiveProductCountsJson())["0QG000000000001AAA"]
    ).toBe(0);

    first.value = "abc";
    first.dispatchEvent(new CustomEvent("change"));
    await flushPromises();
    expect(
      JSON.parse(el.getLiveProductCountsJson())["0QG000000000001AAA"]
    ).toBe(0);
  });

  it("prefers the wizard-supplied grand summary over the subtree roll-up", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      productCountsEditMode: true,
      productCountsExternalGrandSummary: "Full quote: 10 rows now"
    });

    const text = el.shadowRoot.textContent;
    expect(text).toContain("Full quote: 10 rows now");
    expect(text).not.toContain("Combined total (on quote");
  });

  it("does not select or rename rows while editing counts", async () => {
    const el = await mount({
      displayHierarchyJson: EXISTING_TREE,
      productCountsEditMode: true
    });

    q(el, '.tree-row-core[data-path="0"]').click();
    q(el, '.tree-label[data-path="0"]').dispatchEvent(
      new CustomEvent("dblclick", { bubbles: true })
    );
    await flushPromises();

    expect(q(el, "lightning-input.tree-rename-input")).toBeNull();
    expect(
      q(el, '.tree-row-core[data-path="0"]').getAttribute("aria-selected")
    ).toBe("false");
  });
});

describe("c-rlm-set-up-quote-hierarchy-tree: suppressSync", () => {
  it("keeps hierarchyJson untouched when the parent suppresses sync", async () => {
    const el = await mount({
      displayHierarchyJson: TREE,
      suppressSync: true,
      hierarchyJson: '{"parents":[]}'
    });

    expect(el.hierarchyJson).toBe('{"parents":[]}');
    expect(live(el).parents).toHaveLength(2);
  });
});

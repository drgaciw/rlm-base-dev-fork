#!/usr/bin/env python3
"""Unit tests for scripts/ai/query_erd.py (TP-10b).

`query_erd.py` is how agents read the Revenue Cloud data model (the committed ERD file): describe an
object, list its relationships, list a domain, find a path between two objects, search, and print
stats. Wrong answers here are silent -- an agent simply believes them -- so the tests pin the
behaviour that decides what a reader is told: reference detection, `refersTo` normalisation, the
forward-then-reverse path search, case-insensitive lookup, the "not found" messages and the exit
codes.

They run against a small synthetic ERD written to a temp directory (the module's `ERD_PATH` is
pointed at it), so they neither depend on nor duplicate what tests/test_erd_doc_counts.py asserts
about the committed file (and the committed ERD file stays the gate's single-check probe path).

Self-contained -- no pytest:

    python tests/test_query_erd.py

Exits 0 when every check passes, 1 otherwise.
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ai"))

import query_erd as Q  # noqa: E402

RESULTS = []


def _ascii(text):
    """stdout may be cp1252 (Windows, PYTHONUTF8 unset); never let a check name crash the run."""
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(_ascii(f"  [{'PASS' if condition else 'FAIL'}] {name}"
                 + ("" if condition or detail == "" else f": {detail}")))


# Invoice -> Order -> Product2 -> Catalog, plus an Orphan that nothing references. `Order.ProductRef`
# lists two targets, one of which is not an ERD object; `Product2.Notes` carries `refersTo` without
# being a reference type; targets carry stray whitespace and a trailing comma the way the export does.
ERD = {
    "metadata": {"release": "264", "releaseLabel": "Summer '26", "apiVersion": "68.0"},
    "relationships": [{"from": "Order", "to": "Product2"}, {"from": "Invoice", "to": "Order"}],
    "objects": {
        "Product2": {
            "domain": "Product Catalog Management", "domainShort": "PCM", "isStandard": True,
            "fields": {
                "Name": {"type": "string", "description": "The product name"},
                "CatalogId": {"type": "reference", "refersTo": "Catalog", "relationshipName": "Catalog",
                              "description": "Which catalog the product is listed in"},
                "Notes": {"type": "string", "refersTo": "Catalog"},
            },
        },
        "Catalog": {"domain": "Product Catalog Management", "domainShort": "PCM", "fields": {}},
        "Order": {
            "domain": "Order Management", "domainShort": "Orders", "is_standard": False,
            "fields": {
                "ProductRef": {"type": "reference", "refersTo": ["Product2,", " NotInErd"]},
                "UsageId": {"type": "reference"},
            },
        },
        "Invoice": {
            "domain": "Billing", "domainShort": "Billing",
            "fields": {"OrderId": {"type": "reference", "refersTo": "Order, "}},
        },
        "Orphan": {"domain": "Unclassified", "fields": {"Invoice_Number__c": {"type": "string"}}},
    },
}


def run_query(argv, erd=ERD):
    """(exit code, stdout) of `query_erd.main()` with sys.argv=argv against a temp ERD file."""
    with tempfile.TemporaryDirectory() as tmp:
        erd_path = Path(tmp) / "erd-data.json"
        if erd is not None:
            with open(erd_path, "w", encoding="utf-8", newline="\n") as fh:
                if isinstance(erd, str):
                    fh.write(erd)
                else:
                    json.dump(erd, fh)
        out = io.StringIO()
        code = 0
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(Q, "ERD_PATH", erd_path))
            stack.enter_context(mock.patch.object(sys, "argv", ["query_erd.py", *argv]))
            stack.enter_context(contextlib.redirect_stdout(out))
            try:
                Q.main()
            except SystemExit as exc:
                code = exc.code if exc.code is not None else 0
    return code, out.getvalue()


def test_helpers():
    print("\nextract_refs / get_domain_short / find_object / build_relationship_index")
    check("a comma-separated refersTo string is split and trimmed",
          Q.extract_refs({"refersTo": "Account, Contact ,"}) == ["Account", "Contact"])
    check("a list refersTo is trimmed and its trailing commas and blanks dropped",
          Q.extract_refs({"refersTo": ["Account,", "  ", " Contact"]}) == ["Account", "Contact"])
    check("no refersTo (missing or empty) yields no refs",
          Q.extract_refs({}) == [] and Q.extract_refs({"refersTo": ""}) == [])
    check("domainShort wins, then domain, then 'Unknown'",
          Q.get_domain_short({"domainShort": "PCM", "domain": "Long"}) == "PCM"
          and Q.get_domain_short({"domain": "Long"}) == "Long"
          and Q.get_domain_short({}) == "Unknown")
    check("find_object is exact first, then case-insensitive, else None",
          Q.find_object(ERD, "Product2") == "Product2"
          and Q.find_object(ERD, "pRoDuCt2") == "Product2"
          and Q.find_object(ERD, "Nope") is None)

    outgoing, incoming = Q.build_relationship_index(ERD)
    check("outgoing edges are (field, target) per source, including list-valued refersTo",
          sorted(outgoing["Order"]) == [("ProductRef", "Product2")]
          and outgoing["Invoice"] == [("OrderId", "Order")], dict(outgoing))
    check("a field with refersTo counts as a relationship even when its type is not 'reference'",
          ("Notes", "Catalog") in outgoing["Product2"] and ("CatalogId", "Catalog") in outgoing["Product2"])
    check("targets outside the ERD are dropped, and a reference with no refersTo adds no edge",
          all(t in ERD["objects"] for edges in outgoing.values() for _, t in edges))
    check("incoming is the exact reverse of outgoing",
          sorted(incoming["Product2"]) == [("Order", "ProductRef")]
          and sorted(incoming["Catalog"]) == [("Product2", "CatalogId"), ("Product2", "Notes")]
          and "Orphan" not in incoming)


def test_load_erd():
    print("\nload_erd failure modes")
    code, out = run_query(["stats"], erd=None)
    check("a missing ERD file exits 1 and says where it looked and what to check",
          code == 1 and "ERD data file not found" in out and "Ensure" in out, f"{code}: {out}")
    code, out = run_query(["stats"], erd="{not json")
    check("an unparseable ERD file exits 1 with the parse error", code == 1 and "Failed to parse" in out,
          f"{code}: {out}")


def test_describe():
    print("\ndescribe")
    code, out = run_query(["describe", "product2"])
    check("lookup is case-insensitive and the canonical name is printed", code == 0 and "\nProduct2\n" in out, out)
    check("domain, counts and standard flag are shown",
          "Domain: Product Catalog Management (PCM)" in out
          and "Fields: 3 total (2 relationships, 1 data)" in out and "Standard: True" in out, out)
    check("relationship fields show name, relationship name and targets; descriptions are indented under them",
          "CatalogId (Catalog) → Catalog" in out and "Which catalog the product is listed in" in out, out)
    check("data fields show their type and description", "Name (string): The product name" in out, out)

    _, out = run_query(["describe", "Order"])
    check("a reference with no refersTo prints '?' as its target and the is_standard alias is read",
          "UsageId → ?" in out and "ProductRef → Product2, NotInErd" in out and "Standard: False" in out, out)
    _, out = run_query(["describe", "Orphan"])
    check("an object with no relationships prints no relationship section and defaults 'unknown' standard",
          "Relationship Fields" not in out and "Data Fields (1)" in out and "Standard: unknown" in out
          and "Domain: Unclassified (Unclassified)" in out, out)
    _, out = run_query(["describe", "Catalog"])
    check("an object with no fields prints neither section", "Fields: 0 total" in out
          and "Relationship Fields" not in out and "Data Fields" not in out, out)
    code, out = run_query(["describe", "Nothing"])
    check("an unknown object suggests search and still exits 0",
          code == 0 and "Object 'Nothing' not found. Try:" in out and 'search "Nothing"' in out, f"{code}: {out}")


def test_relationships():
    print("\nrelationships")
    _, out = run_query(["relationships", "Order"])
    check("both directions are listed with the other side's domain",
          "Outgoing (this object references):" in out and "ProductRef → Product2 [PCM]" in out
          and "Incoming (referenced by):" in out and "Invoice.OrderId [Billing]" in out, out)
    _, out = run_query(["relationships", "Invoice"])
    check("an object nothing references has no Incoming section", "Incoming" not in out and "Outgoing" in out, out)
    _, out = run_query(["relationships", "Orphan"])
    check("an object with no edges says so", "No relationships found." in out, out)
    _, out = run_query(["relationships", "Missing"])
    check("an unknown object is reported", "Object 'Missing' not found." in out, out)


def test_domain():
    print("\ndomain")
    _, out = run_query(["domain", "pcm"])
    check("domain matches the short name case-insensitively and counts its objects",
          "Product Catalog Management — 2 objects" in out
          and "Product2 (3 fields, 2 relationships)" in out and "Catalog (0 fields, 0 relationships)" in out, out)
    _, out = run_query(["domain", "Order", "Management"])
    check("a multi-word domain name is joined and matches the long name",
          "Order Management — 1 objects" in out and "Order (2 fields, 2 relationships)" in out, out)
    _, out = run_query(["domain", "zzz"])
    check("an unknown domain lists the available short names, sorted",
          "No objects found for domain 'zzz'." in out
          and "Available domains: Billing, Orders, PCM, Unclassified" in out, out)


def test_path():
    print("\npath")
    _, out = run_query(["path", "Invoice", "Product2"])
    check("a forward path lists each hop and the field that crosses it",
          "Path: Invoice → Product2 (2 hops)" in out and "↓ OrderId" in out and "↓ ProductRef" in out
          and "Invoice [Billing]" in out and "Order [Orders]" in out and "Product2 [PCM]" in out
          and "reverse" not in out, out)
    _, out = run_query(["path", "product2", "INVOICE"])
    check("with no forward route the search falls back to reverse traversal and says so",
          "Path: Product2 → Invoice (2 hops, reverse traversal)" in out
          and "↑ Order.ProductRef" in out and "↑ Invoice.OrderId" in out, out)
    _, out = run_query(["path", "Catalog", "Catalog"])
    check("a path from an object to itself is zero hops", "Path: Catalog → Catalog (0 hops)" in out, out)
    _, out = run_query(["path", "Orphan", "Product2"])
    check("unconnected objects report no path", "No path found between Orphan and Product2." in out, out)
    _, out = run_query(["path", "Nope", "Product2"])
    check("an unknown start object is named", "Start object 'Nope' not found." in out, out)
    _, out = run_query(["path", "Product2", "Nope"])
    check("an unknown end object is named", "End object 'Nope' not found." in out, out)
    code, out = run_query(["path", "Product2"])
    check("path with one argument prints the usage and exits 1", code == 1 and "Usage:" in out, f"{code}: {out}")


def test_search():
    print("\nsearch")
    _, out = run_query(["search", "invoice"])
    check("objects and fields are searched case-insensitively",
          "Objects matching 'invoice' (1):" in out and "Invoice [Billing] (1 fields)" in out
          and "Fields matching 'invoice' (1):" in out and "Orphan.Invoice_Number__c (string)" in out, out)
    _, out = run_query(["search", "catalogid"])
    check("a matching reference field shows its targets", "Product2.CatalogId (reference) → Catalog" in out
          and "Objects matching" not in out, out)
    _, out = run_query(["search", "no", "such", "thing"])
    check("a multi-word query is joined and an empty result says so", "No results for 'no such thing'." in out, out)

    many = {"objects": {"Big": {"domain": "D", "fields": {f"Field{i:03d}": {"type": "string"} for i in range(60)}}}}
    _, out = run_query(["search", "field"], erd=many)
    check("field hits are capped at 50 with the remainder counted",
          "Fields matching 'field' (60):" in out and "... and 10 more" in out
          and out.count("Big.Field") == 50, out)


def test_stats():
    print("\nstats")
    _, out = run_query(["stats"])
    check("the header is built from the metadata block",
          "Revenue Cloud Data Model — Release 264 (Summer '26, API v68.0)" in out, out)
    check("totals come from the objects, and the relationship count from relationships[] (not the field tally)",
          "Total Objects:       5" in out and "Total Fields:        7" in out
          and "Reference Fields:    5" in out and "Total Relationships: 2" in out
          and "Domains:             4" in out, out)
    body = out.split("Objects\n")[-1]
    check("domains are listed by descending object count", body.index("PCM") < body.index("Billing"), out)
    bare = {"objects": {"A": {"domain": "D", "fields": {}}}}
    _, out = run_query(["stats"], erd=bare)
    check("an ERD with no metadata falls back to the plain header and zero relationships",
          "Revenue Cloud Data Model\n" in out and "Release" not in out and "Total Relationships: 0" in out, out)


def test_dispatch():
    print("\nmain() dispatch")
    for label, argv in (("no arguments", []), ("an unknown command", ["frobnicate"]),
                        ("describe without an object", ["describe"]),
                        ("search without a query", ["search"]),
                        ("domain without a name", ["domain"]),
                        ("relationships without an object", ["relationships"])):
        code, out = run_query(argv)
        check(f"{label} prints the usage and exits 1", code == 1 and "Usage:" in out, f"{code}: {out[:80]}")
    code, out = run_query(["STATS"])
    check("the command word is case-insensitive", code == 0 and "Total Objects" in out, out)


def main():
    test_helpers()
    test_load_erd()
    test_describe()
    test_relationships()
    test_domain()
    test_path()
    test_search()
    test_stats()
    test_dispatch()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

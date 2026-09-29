// The unsafe javascript: urls below are inputs the code under test must reject.
/* eslint-disable no-script-url */
import getObjectIdFromQuery from "@salesforce/apex/RLM_Learning_DynamicLinkHelper.getObjectIdFromQuery";
import {
  escapeHtml,
  findDynamicLinkIdentifier,
  getPageReferenceByDynamicType,
  reduceErrorMessage,
  requireSafeUrl,
  safeVideoUrl
} from "c/rlmLearningCommonFunctions";

jest.mock(
  "@salesforce/apex/RLM_Learning_DynamicLinkHelper.getObjectIdFromQuery",
  () => ({ __esModule: true, default: jest.fn() }),
  { virtual: true }
);

describe("c-rlm-learning-common-functions", () => {
  describe("escapeHtml", () => {
    it("escapes markup characters", () => {
      expect(escapeHtml(`<a href="x">Tom & 'Jerry'</a>`)).toBe(
        "&lt;a href=&quot;x&quot;&gt;Tom &amp; &#39;Jerry&#39;&lt;/a&gt;"
      );
    });

    it("treats null and undefined as an empty string", () => {
      expect(escapeHtml(null)).toBe("");
      expect(escapeHtml(undefined)).toBe("");
    });
  });

  describe("safeVideoUrl", () => {
    it("allows https urls on allow-listed video hosts", () => {
      const url = "https://www.youtube.com/embed/abc";
      expect(safeVideoUrl(url)).toBe(url);
    });

    it("rejects non-https, unknown hosts, and unparsable input", () => {
      expect(safeVideoUrl("http://www.youtube.com/embed/abc")).toBeNull();
      expect(safeVideoUrl("https://evil.example.com/v")).toBeNull();
      expect(safeVideoUrl("not a url")).toBeNull();
      expect(safeVideoUrl("")).toBeNull();
    });
  });

  describe("requireSafeUrl", () => {
    it("accepts absolute http(s) urls and single-slash relative paths", () => {
      expect(requireSafeUrl(" https://example.com/x ")).toBe(
        "https://example.com/x"
      );
      expect(requireSafeUrl("/lightning/page/home")).toBe(
        "/lightning/page/home"
      );
    });

    it.each([
      "javascript:alert(1)",
      "data:text/html,hi",
      "//evil.example.com",
      "/\\evil.example.com",
      ""
    ])("throws for unsafe url %p", (url) => {
      expect(() => requireSafeUrl(url)).toThrow("Unsafe or invalid link URL");
    });
  });

  describe("reduceErrorMessage", () => {
    it("reduces the supported error shapes to one string", () => {
      expect(reduceErrorMessage({ body: { message: "apex" } })).toBe("apex");
      expect(
        reduceErrorMessage({ body: [{ message: "a" }, { message: "b" }] })
      ).toBe("a, b");
      expect(reduceErrorMessage({ message: "plain" })).toBe("plain");
    });

    it("falls back when nothing usable is present", () => {
      expect(reduceErrorMessage(undefined)).toBe("Unknown error");
      expect(reduceErrorMessage({ body: [] }, "custom")).toBe("custom");
    });
  });

  describe("findDynamicLinkIdentifier", () => {
    it("returns the identifier that ends with DYN_LINK", () => {
      const input = "See <b>PriceManagement_Getstarted_DYN_LINK</b> now";
      expect(findDynamicLinkIdentifier(input, input.indexOf("DYN_LINK"))).toBe(
        "PriceManagement_Getstarted_DYN_LINK"
      );
    });
  });

  describe("getPageReferenceByDynamicType", () => {
    const link = (developerName, extra = {}) => ({
      RecordType: { DeveloperName: developerName },
      RLM_Learning_App_API_Name__c: "standard__LightningSales",
      ...extra
    });

    it("builds an app page reference and adds the page id state", async () => {
      const ref = await getPageReferenceByDynamicType(
        link("NamedPage", {
          RLM_Learning_Page_Name__c: "Home",
          RLM_Learning_Page__c: "a00000000000001AAA"
        })
      );
      expect(ref.type).toBe("standard__app");
      expect(ref.attributes.pageRef.attributes.pageName).toBe("Home");
      expect(ref.attributes.pageRef.state).toEqual({
        c__pageId: "a00000000000001AAA"
      });
    });

    it("resolves the record id for a record page", async () => {
      getObjectIdFromQuery.mockResolvedValue([{ Id: "001000000000001AAA" }]);
      const ref = await getPageReferenceByDynamicType(
        link("RecordPage", { RLM_Learning_Object__c: "Account" })
      );
      expect(ref.attributes.pageRef.attributes.recordId).toBe(
        "001000000000001AAA"
      );
    });

    it("rejects a record page whose query matches nothing", async () => {
      getObjectIdFromQuery.mockResolvedValue([]);
      await expect(
        getPageReferenceByDynamicType(
          link("RecordPage", { RLM_Learning_Object__c: "Account" })
        )
      ).rejects.toThrow("No record found for RecordPage: Account");
    });

    it("refuses an unsafe web link", async () => {
      await expect(
        getPageReferenceByDynamicType(
          link("WebPage", { RLM_Learning_Link__c: "javascript:alert(1)" })
        )
      ).rejects.toThrow("Unsafe or invalid link URL");
    });
  });
});

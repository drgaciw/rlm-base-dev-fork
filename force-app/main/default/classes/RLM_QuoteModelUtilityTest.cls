/**
 * Tests for RLM_QuoteModelUtility.
 *
 * Not covered here: the per-line loop of CreateQuoteContextString. It dereferences
 * QuoteLineItem.ProrationPolicy, which is populated by the pricing engine and cannot be set with
 * Apex DML, so a DML-built line always fails inside the class. That loop (including the bulkified
 * attribute/relationship maps from pack 083) is exercised by the nightly integration run (TP-04).
 * The two date converters and both queries are pure/DML-testable and are asserted directly.
 */
@isTest
private class RLM_QuoteModelUtilityTest {

    @TestSetup
    static void setup() {
        Account acct = RLM_TestDataFactory.createAccount();
        Product2 product = RLM_TestDataFactory.createProduct('Quote Model Product');
        RLM_TestDataFactory.createStandardPricebookEntry(product.Id, 100);
        RLM_TestDataFactory.createQuote(acct.Id);
    }

    private static Quote theQuote() {
        return [SELECT Id, Pricebook2Id FROM Quote LIMIT 1];
    }

    @isTest
    static void convertStartDateUsesMidnight() {
        System.assertEquals('2026-03-05T00:00:00.000Z', RLM_QuoteModelUtility.convertStartDate(Date.newInstance(2026, 3, 5)));
    }

    @isTest
    static void convertEndDateUsesEndOfDay() {
        System.assertEquals('2026-03-05T23:59:59.000Z', RLM_QuoteModelUtility.convertEndDate(Date.newInstance(2026, 3, 5)));
    }

    @isTest
    static void getQuoteReturnsTheRequestedQuote() {
        Quote q = theQuote();

        Quote fetched = RLM_QuoteModelUtility.getQuote(new List<Id>{ q.Id });

        System.assertEquals(q.Id, fetched.Id);
        System.assertEquals(q.Pricebook2Id, fetched.Pricebook2Id);
    }

    @isTest
    static void getQuoteThrowsWhenNoQuoteMatches() {
        Quote q = theQuote();
        delete q;

        try {
            RLM_QuoteModelUtility.getQuote(new List<Id>{ q.Id });
            System.assert(false, 'a missing quote must surface as an error');
        } catch (System.ListException e) {
            System.assert(true);
        }
    }

    @isTest
    static void getQuoteLinesIsEmptyForQuoteWithoutLines() {
        System.assert(RLM_QuoteModelUtility.getQuoteLines(theQuote().Id).isEmpty());
    }

    @isTest
    static void getQuoteLinesReturnsAllLinesForBulkQuote() {
        Quote q = theQuote();
        PricebookEntry pbe = [SELECT Id FROM PricebookEntry LIMIT 1];
        RLM_TestDataFactory.createQuoteLineItems(q.Id, pbe.Id, RLM_TestDataFactory.BULK_SIZE);

        Test.startTest();
        List<QuoteLineItem> lines = RLM_QuoteModelUtility.getQuoteLines(q.Id);
        Test.stopTest();

        System.assertEquals(RLM_TestDataFactory.BULK_SIZE, lines.size());
        System.assertEquals(q.Id, lines[0].QuoteId, 'lines must be scoped to the requested quote');
    }

    @isTest
    static void contextStringForQuoteWithoutLinesCarriesQuoteHeader() {
        Quote q = theQuote();

        List<String> result = RLM_QuoteModelUtility.CreateQuoteContextString(new List<Id>{ q.Id });

        System.assertEquals(1, result.size());
        Map<String, Object> root = (Map<String, Object>) JSON.deserializeUntyped(result[0]);
        Map<String, Object> salesTransaction = (Map<String, Object>) root.get('SalesTransaction');
        System.assertEquals(String.valueOf(q.Id), salesTransaction.get('SalesTransactionSource'));
        System.assertEquals(String.valueOf(q.Pricebook2Id), salesTransaction.get('PriceBooks'));
        System.assert(((List<Object>) salesTransaction.get('SalesTransactionItem')).isEmpty());
    }

    @isTest
    static void contextStringThrowsWhenNoQuoteMatches() {
        try {
            RLM_QuoteModelUtility.CreateQuoteContextString(new List<Id>());
            System.assert(false, 'an empty Id list must surface as an error');
        } catch (System.ListException e) {
            System.assert(true);
        }
    }
}

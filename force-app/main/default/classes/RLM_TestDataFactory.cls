/**
 * Shared test-data builders for the TP-06 Apex test backlog (docs/references/test-plan-2026-09.md §4.2).
 *
 * Rules the builders enforce so callers cannot forget them:
 *  - Quotes always get an Account, an Opportunity (OpportunityId) and Status = 'Draft'.
 *  - Pricebook entries use the standard pricebook (Test.getStandardPricebookId) — never a
 *    hard-coded Id, and never SeeAllData.
 *  - Builders that create children take a count so tests can exercise bulk (BULK_SIZE = 200).
 *
 * Test-only: `@isTest` keeps it out of the org's coverage denominator.
 */
@isTest
public class RLM_TestDataFactory {

    public static final Integer BULK_SIZE = 200;

    /**
     * A well-formed 18-char Id for `type` that needs no DML (e.g. to feed Id-typed inputs or to
     * point at a record that must not exist). The 'AAA' checksum suffix is correct only for a
     * prefix with no uppercase letters, so it is rejected for such prefixes (Quote's 0Q0, say)
     * instead of returning an Id the platform would refuse.
     */
    public static Id wellFormedId(Schema.SObjectType type, Integer n) {
        String prefix = type.getDescribe().getKeyPrefix();
        if (prefix == null || prefix != prefix.toLowerCase()) {
            throw new IllegalArgumentException('wellFormedId supports only digit/lower-case key prefixes, got: ' + prefix);
        }
        return Id.valueOf(prefix + String.valueOf(n).leftPad(12, '0') + 'AAA');
    }

    public static List<Account> createAccounts(Integer count, Boolean doInsert) {
        List<Account> accounts = new List<Account>();
        for (Integer i = 0; i < count; i++) {
            accounts.add(new Account(Name = 'RLM Test Account ' + i));
        }
        if (doInsert) {
            insert accounts;
        }
        return accounts;
    }

    public static Account createAccount() {
        return createAccounts(1, true)[0];
    }

    public static Product2 createProduct(String name) {
        Product2 product = new Product2(Name = name, IsActive = true);
        insert product;
        return product;
    }

    public static PricebookEntry createStandardPricebookEntry(Id product2Id, Decimal unitPrice) {
        PricebookEntry pbe = new PricebookEntry(
            Pricebook2Id = Test.getStandardPricebookId(),
            Product2Id = product2Id,
            UnitPrice = unitPrice,
            IsActive = true
        );
        insert pbe;
        return pbe;
    }

    public static Opportunity createOpportunity(Id accountId) {
        Opportunity opp = new Opportunity(
            Name = 'RLM Test Opportunity',
            AccountId = accountId,
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30)
        );
        insert opp;
        return opp;
    }

    public static Quote createQuote(Id accountId) {
        Opportunity opp = createOpportunity(accountId);
        Quote q = new Quote(
            Name = 'RLM Test Quote',
            OpportunityId = opp.Id,
            Pricebook2Id = Test.getStandardPricebookId(),
            Status = 'Draft'
        );
        insert q;
        return q;
    }

    public static List<QuoteLineItem> createQuoteLineItems(Id quoteId, Id pricebookEntryId, Integer count) {
        List<QuoteLineItem> lines = new List<QuoteLineItem>();
        for (Integer i = 0; i < count; i++) {
            lines.add(new QuoteLineItem(
                QuoteId = quoteId,
                PricebookEntryId = pricebookEntryId,
                Quantity = 1,
                UnitPrice = 100,
                StartDate = Date.today()
            ));
        }
        insert lines;
        return lines;
    }

    public static List<Asset> createAssets(Id accountId, Id product2Id, Integer count) {
        List<Asset> assets = new List<Asset>();
        for (Integer i = 0; i < count; i++) {
            assets.add(new Asset(Name = 'RLM Test Asset ' + i, AccountId = accountId, Product2Id = product2Id));
        }
        insert assets;
        return assets;
    }

    public static Order createOrder(Id accountId) {
        Order o = new Order(
            AccountId = accountId,
            Pricebook2Id = Test.getStandardPricebookId(),
            EffectiveDate = Date.today(),
            Status = 'Draft'
        );
        insert o;
        return o;
    }

    public static OrderItem createOrderItem(Id orderId, PricebookEntry pbe) {
        OrderItem oi = new OrderItem(
            OrderId = orderId,
            Product2Id = pbe.Product2Id,
            PricebookEntryId = pbe.Id,
            Quantity = 1,
            UnitPrice = pbe.UnitPrice
        );
        insert oi;
        return oi;
    }
}

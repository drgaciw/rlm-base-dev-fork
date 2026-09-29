/**
 * Tests for RLM_AssetInfoUtility (a `without sharing` @InvocableMethod; see the decision
 * comment at the top of that class — architect review A-C7).
 *
 * COVERAGE GAP, on purpose and stated here so nobody assumes otherwise: the "Add" and "existing
 * asset" branches read OrderItem.OrderAction.Type. OrderAction rows are created only by the Place
 * Order / createOrUpdateAssetFromOrder platform flow, not by Apex DML, so a hermetic test cannot
 * reach them; asserting on them would need a @TestVisible seam in the class (out of scope for a
 * test-only package). Those branches are covered by the nightly integration run (TP-04), which
 * builds real orders. What this class pins is only the part testable without the platform: empty
 * and no-detail input is a no-op, including for a user with no object access.
 *
 * DEFERRED to TP-04 (needs an org with a Partner Community user and real orders): the test-plan
 * section 4.2 assertion that a partner user who owns no Assets still receives the elevated result,
 * i.e. the assertion that documents the `without sharing` decision. Nothing in this class asserts it.
 */
@isTest
private class RLM_AssetInfoUtilityTest {

    // A CreateAssetOrderEvent whose AssetDetails child list is empty. Child relationship lists
    // cannot be assigned on an in-memory sObject, so the event is built the way a Flow hands it over.
    private static CreateAssetOrderEvent eventWithNoDetails() {
        return (CreateAssetOrderEvent) JSON.deserialize(
            '{"AssetDetails":{"totalSize":0,"done":true,"records":[]}}',
            CreateAssetOrderEvent.class
        );
    }

    @isTest
    static void emptyInputListIsANoOp() {
        Integer assetsBefore = [SELECT COUNT() FROM Asset];

        Test.startTest();
        RLM_AssetInfoUtility.calculateAssetRenewInfo(new List<CreateAssetOrderEvent>());
        Test.stopTest();

        System.assertEquals(assetsBefore, [SELECT COUNT() FROM Asset], 'no asset may be written for empty input');
    }

    @isTest
    static void eventWithoutAssetDetailsWritesNothing() {
        Account acct = RLM_TestDataFactory.createAccount();
        Product2 product = RLM_TestDataFactory.createProduct('Asset Info Product');
        Asset existing = RLM_TestDataFactory.createAssets(acct.Id, product.Id, 1)[0];

        Test.startTest();
        RLM_AssetInfoUtility.calculateAssetRenewInfo(new List<CreateAssetOrderEvent>{ eventWithNoDetails() });
        Test.stopTest();

        Asset after = [SELECT RenewalTerm, RenewalTermUnit, PricingSource FROM Asset WHERE Id = :existing.Id];
        System.assertEquals(null, after.RenewalTerm, 'an event with no details must not touch existing assets');
        System.assertEquals(null, after.RenewalTermUnit);
    }

    // What this proves, and no more: an event with no details is a no-op for a user with NO object
    // access and no ownership of the data, and nothing is written. It does NOT prove the
    // `without sharing` decision: the elevated queries only run when there are details to look up,
    // and the Add / existing-asset paths need OrderAction rows (see the class header). The test-plan
    // section 4.2 assertion (a Partner Community user who owns no Assets still gets the elevated
    // result) is DEFERRED to TP-04's org-backed run.
    @isTest
    static void eventWithNoDetailsIsANoOpForAUserWithNoObjectAccess() {
        Profile minimumAccess = [SELECT Id FROM Profile WHERE Name = 'Minimum Access - Salesforce' LIMIT 1];
        String uniq = String.valueOf(Crypto.getRandomInteger()).replace('-', 'n');
        User nonOwner = new User(
            Alias = 'nonown',
            Email = 'nonowner.' + uniq + '@example.invalid',
            EmailEncodingKey = 'UTF-8',
            LastName = 'NonOwner',
            LanguageLocaleKey = 'en_US',
            LocaleSidKey = 'en_US',
            ProfileId = minimumAccess.Id,
            TimeZoneSidKey = 'America/Los_Angeles',
            UserName = 'nonowner.' + uniq + '@example.invalid'
        );
        System.runAs(new User(Id = UserInfo.getUserId())) {
            insert nonOwner;
        }

        Account acct = RLM_TestDataFactory.createAccount();
        Product2 product = RLM_TestDataFactory.createProduct('Asset Info Product');
        RLM_TestDataFactory.createAssets(acct.Id, product.Id, 1);

        Test.startTest();
        System.runAs(nonOwner) {
            RLM_AssetInfoUtility.calculateAssetRenewInfo(new List<CreateAssetOrderEvent>{ eventWithNoDetails() });
        }
        Test.stopTest();

        System.assertEquals(1, [SELECT COUNT() FROM Asset WHERE AccountId = :acct.Id], 'asset must be untouched');
    }
}

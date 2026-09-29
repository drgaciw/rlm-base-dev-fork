/**
 * USER_MODE contract of RLM_AI_UpdateRecordFieldsService, exercised as a non-admin user
 * (architect review A-C6; docs/references/test-plan-2026-09.md §4.2).
 *
 * Hermetic on purpose: the running user gets a PermissionSet created INSIDE this test that mirrors
 * what the shipped agent permission set RLM_QuotingAssistant grants (Quote edit; Quote.Description /
 * ExpirationDate / Status; QuoteLineItem.StartDate / EndDate / Description). It deliberately does not
 * reference RLM_QuotingAssistant: this class deploys with prepare_agents step 3, before the agent
 * permission sets exist (step 9), and a deployed test must not depend on them. Whether the SHIPPED
 * permission set grants what the service needs is checked by the nightly post-build verification
 * (TP-04), not here.
 *
 * The user is on the Minimum Access profile so that this PermissionSet is its only grant.
 *
 * What this proves: with exactly those grants the service updates the granted fields, and it does
 * NOT write a field the user has no FLS for, nor any object outside its allowlist.
 */
@isTest
private class RLM_AI_UpdateRecordFieldsServiceUserModeTest {

    private static final String USER_LAST_NAME = 'UserModeTest';

    @TestSetup
    static void setup() {
        // Minimum Access has no object or field permissions of its own, so the PermissionSet built
        // below is the ONLY grant this user holds. (Standard User already carries Quote/QuoteLineItem
        // CRUD and FLS, which would make every positive assertion pass without the grant and the
        // no-FLS assertion fail.)
        Profile minimumAccess = [SELECT Id FROM Profile WHERE Name = 'Minimum Access - Salesforce' LIMIT 1];
        String uniq = String.valueOf(Crypto.getRandomInteger()).replace('-', 'n');
        User u = new User(
            Alias = 'umtest',
            Email = 'usermode.' + uniq + '@example.invalid',
            EmailEncodingKey = 'UTF-8',
            LastName = USER_LAST_NAME,
            LanguageLocaleKey = 'en_US',
            LocaleSidKey = 'en_US',
            ProfileId = minimumAccess.Id,
            TimeZoneSidKey = 'America/Los_Angeles',
            UserName = 'usermode.' + uniq + '@example.invalid'
        );

        // Setup objects (User, PermissionSet, grants, assignment) must be inserted in a separate
        // context from the business data below, or the platform raises MIXED_DML_OPERATION.
        System.runAs(new User(Id = UserInfo.getUserId())) {
            insert u;

            PermissionSet ps = new PermissionSet(Name = 'RLM_UserModeTestGrant', Label = 'RLM UserMode Test Grant');
            insert ps;
            insert new ObjectPermissions(
                ParentId = ps.Id, SobjectType = 'Quote', PermissionsRead = true, PermissionsEdit = true);
            // Read-only companions mirroring the shipped RLM_QuotingAssistant permission set (Opportunity
            // read) plus Product2 read for the agent user's standard quoting grants. Not claimed to be
            // needed by the service: its lookup queries run in system mode. They give no write access.
            insert new List<ObjectPermissions>{
                new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Opportunity', PermissionsRead = true),
                new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Product2', PermissionsRead = true)
            };
            List<FieldPermissions> fieldGrants = new List<FieldPermissions>();
            for (String field : new List<String>{
                'Quote.Description', 'Quote.ExpirationDate', 'Quote.Status',
                'QuoteLineItem.StartDate', 'QuoteLineItem.EndDate', 'QuoteLineItem.Description'
            }) {
                fieldGrants.add(new FieldPermissions(
                    ParentId = ps.Id, SobjectType = field.substringBefore('.'), Field = field,
                    PermissionsRead = true, PermissionsEdit = true));
            }
            insert fieldGrants;
            insert new PermissionSetAssignment(AssigneeId = u.Id, PermissionSetId = ps.Id);
        }

        // Owned by the run-as user so record-level sharing is not what these tests are measuring.
        Account acct = new Account(Name = 'UserMode Account', OwnerId = u.Id);
        insert acct;
        Opportunity opp = new Opportunity(
            Name = 'UserMode Opportunity', AccountId = acct.Id, OwnerId = u.Id,
            StageName = 'Prospecting', CloseDate = Date.today().addDays(30));
        insert opp;
        Id standardPbId = Test.getStandardPricebookId();
        insert new Quote(
            Name = 'UserMode Quote', OpportunityId = opp.Id, Pricebook2Id = standardPbId,
            Status = 'Draft', Description = 'Original description');
        Product2 product = new Product2(Name = 'UserMode Product', IsActive = true);
        insert product;
        PricebookEntry pbe = new PricebookEntry(
            Pricebook2Id = standardPbId, Product2Id = product.Id, UnitPrice = 100, IsActive = true);
        insert pbe;
        insert new QuoteLineItem(
            QuoteId = [SELECT Id FROM Quote LIMIT 1].Id, PricebookEntryId = pbe.Id,
            Quantity = 1, UnitPrice = 100, Description = 'Original line description');
    }

    private static User runAsUser() {
        return [SELECT Id FROM User WHERE LastName = :USER_LAST_NAME AND Alias = 'umtest' LIMIT 1];
    }

    private static RLM_AI_UpdateRecordFieldsService.UpdateFieldsOutput call(
        User runAs, String sObjectType, String fieldUpdatesJson, List<String> lineIds
    ) {
        RLM_AI_UpdateRecordFieldsService.UpdateFieldsInput input =
            new RLM_AI_UpdateRecordFieldsService.UpdateFieldsInput();
        input.quoteId = String.valueOf([SELECT Id FROM Quote LIMIT 1].Id);
        input.sObjectType = sObjectType;
        input.fieldUpdatesJson = fieldUpdatesJson;
        input.quoteLineItemIds = lineIds;

        List<RLM_AI_UpdateRecordFieldsService.UpdateFieldsOutput> results;
        Test.startTest();
        System.runAs(runAs) {
            results = RLM_AI_UpdateRecordFieldsService.updateRecordFields(
                new List<RLM_AI_UpdateRecordFieldsService.UpdateFieldsInput>{ input });
        }
        Test.stopTest();
        return results[0];
    }

    @isTest
    static void grantedQuoteFieldIsUpdated() {
        RLM_AI_UpdateRecordFieldsService.UpdateFieldsOutput out = call(
            runAsUser(), 'Quote', '[{"fieldApiName":"Description","value":"Edited by agent user"}]', null);

        System.assertEquals(true, out.isSuccess, 'error: ' + out.errorMessage);
        System.assertEquals(1, out.updatedCount);
        System.assertEquals('Edited by agent user', [SELECT Description FROM Quote LIMIT 1].Description);
    }

    // A-C6: the LLM-supplied sObjectType is not guaranteed to match the allowlist's casing.
    @isTest
    static void lowercaseQuoteSObjectTypeIsAccepted() {
        RLM_AI_UpdateRecordFieldsService.UpdateFieldsOutput out = call(
            runAsUser(), 'quote', '[{"fieldApiName":"Description","value":"Lowercase ok"}]', null);

        System.assertEquals(true, out.isSuccess, 'error: ' + out.errorMessage);
        System.assertEquals('Lowercase ok', [SELECT Description FROM Quote LIMIT 1].Description);
    }

    @isTest
    static void grantedLineFieldIsUpdated() {
        QuoteLineItem line = [SELECT Id FROM QuoteLineItem LIMIT 1];

        RLM_AI_UpdateRecordFieldsService.UpdateFieldsOutput out = call(
            runAsUser(), 'QuoteLineItem', '[{"fieldApiName":"Description","value":"Line edited"}]',
            new List<String>{ String.valueOf(line.Id) });

        System.assertEquals(true, out.isSuccess, 'error: ' + out.errorMessage);
        System.assertEquals('Line edited', [SELECT Description FROM QuoteLineItem WHERE Id = :line.Id].Description);
    }

    // The field exists and is updateable for an admin, but this user has no FLS for it: USER_MODE
    // must refuse rather than write through.
    @isTest
    static void fieldWithoutFlsIsRejectedAndNotWritten() {
        RLM_AI_UpdateRecordFieldsService.UpdateFieldsOutput out = call(
            runAsUser(), 'Quote', '[{"fieldApiName":"Phone","value":"555-0100"}]', null);

        System.assertEquals(false, out.isSuccess, 'a field the user has no FLS for must not be written');
        System.assertEquals(0, out.updatedCount);
        System.assert(String.isNotBlank(out.errorMessage), 'the refusal must be reported, not silent');
        System.assertEquals(null, [SELECT Phone FROM Quote LIMIT 1].Phone);
    }

    @isTest
    static void objectOutsideTheAllowlistIsRejectedForANonAdmin() {
        Account acct = [SELECT Id, Name FROM Account LIMIT 1];

        RLM_AI_UpdateRecordFieldsService.UpdateFieldsOutput out = call(
            runAsUser(), 'Account', '[{"fieldApiName":"Name","value":"Hijacked"}]',
            new List<String>{ String.valueOf(acct.Id) });

        System.assertEquals(false, out.isSuccess);
        System.assert(out.errorMessage.containsIgnoreCase('Unsupported sObject type'), out.errorMessage);
        System.assertEquals(acct.Name, [SELECT Name FROM Account WHERE Id = :acct.Id].Name);
    }
}

@isTest
private class RLM_DocumentGenerationMergeTest {

    // Well-formed 18-char Ids with no DML and no hard-coded Id literal. Local helper on purpose:
    // unpackaged/post_docgen deploys independently of force-app (RLM_TestDataFactory). The 'AAA'
    // checksum suffix is right only for prefixes without uppercase letters, hence Account/ContentVersion.
    private static String fakeId(Schema.SObjectType type, Integer n) {
        return type.getDescribe().getKeyPrefix() + String.valueOf(n).leftPad(12, '0') + 'AAA';
    }

    private static final String REFERENCE_ID = fakeId(Account.SObjectType, 1);
    private static final String CONTENT_VERSION_ID_1 = fakeId(ContentVersion.SObjectType, 1);
    private static final String CONTENT_VERSION_ID_2 = fakeId(ContentVersion.SObjectType, 2);

    private static RLM_DocumentGenerationMerge.Request request(List<Id> recordIds, String title) {
        RLM_DocumentGenerationMerge.Request req = new RLM_DocumentGenerationMerge.Request();
        req.CurrentRecordId = Id.valueOf(REFERENCE_ID); // any well-formed record Id; the class only stores it
        req.recordIds = recordIds;
        req.DocTitle = title;
        return req;
    }

    @isTest
    static void createsAMergePdfProcessAndReturnsItsId() {
        RLM_DocumentGenerationMerge.Request req = request(
            new List<Id>{ Id.valueOf(CONTENT_VERSION_ID_1), Id.valueOf(CONTENT_VERSION_ID_2) },
            'Contract "Pack"\nv1');

        Test.startTest();
        List<RLM_DocumentGenerationMerge.Response> out =
            RLM_DocumentGenerationMerge.MergeDocuments(new List<RLM_DocumentGenerationMerge.Request>{ req });
        Test.stopTest();

        System.assertEquals(1, out.size());
        System.assertNotEquals(null, out[0].MergedRecordId);
        DocumentGenerationProcess dgp = [
            SELECT Type, Status, PdfDocIdentifiersList, RequestText, DocGenApiVersionType
            FROM DocumentGenerationProcess WHERE Id = :out[0].MergedRecordId
        ];
        System.assertEquals('MergePDF', dgp.Type);
        System.assertEquals(CONTENT_VERSION_ID_1 + ',' + CONTENT_VERSION_ID_2, dgp.PdfDocIdentifiersList);
        // The title must round-trip as valid JSON even with quotes and newlines in it.
        Map<String, Object> text = (Map<String, Object>) JSON.deserializeUntyped(dgp.RequestText);
        System.assertEquals('Contract "Pack"\nv1', text.get('title'));
    }

    @isTest
    static void nullIdsInTheListAreDropped() {
        RLM_DocumentGenerationMerge.Request req = request(
            new List<Id>{ null, Id.valueOf(CONTENT_VERSION_ID_1) }, 'Pack');

        List<RLM_DocumentGenerationMerge.Response> out =
            RLM_DocumentGenerationMerge.MergeDocuments(new List<RLM_DocumentGenerationMerge.Request>{ req });

        DocumentGenerationProcess dgp = [
            SELECT PdfDocIdentifiersList FROM DocumentGenerationProcess WHERE Id = :out[0].MergedRecordId
        ];
        System.assertEquals(CONTENT_VERSION_ID_1, dgp.PdfDocIdentifiersList);
    }

    @isTest
    static void everyRequestGetsItsOwnProcess() {
        List<RLM_DocumentGenerationMerge.Request> requests = new List<RLM_DocumentGenerationMerge.Request>();
        for (Integer i = 0; i < 3; i++) {
            requests.add(request(new List<Id>{ Id.valueOf(CONTENT_VERSION_ID_1) }, 'Pack ' + i));
        }

        List<RLM_DocumentGenerationMerge.Response> out = RLM_DocumentGenerationMerge.MergeDocuments(requests);

        System.assertEquals(3, out.size());
        System.assertEquals(3, new Set<Id>{ out[0].MergedRecordId, out[1].MergedRecordId, out[2].MergedRecordId }.size());
    }

    @isTest
    static void nullOrEmptyRequestListThrows() {
        for (List<RLM_DocumentGenerationMerge.Request> bad : new List<List<RLM_DocumentGenerationMerge.Request>>{
            null, new List<RLM_DocumentGenerationMerge.Request>()
        }) {
            try {
                RLM_DocumentGenerationMerge.MergeDocuments(bad);
                System.assert(false, 'missing input must be rejected');
            } catch (IllegalArgumentException e) {
                System.assert(e.getMessage().contains('at least one request'), e.getMessage());
            }
        }
    }

    @isTest
    static void requestWithNoUsableIdsThrows() {
        for (List<Id> ids : new List<List<Id>>{ null, new List<Id>(), new List<Id>{ null } }) {
            try {
                RLM_DocumentGenerationMerge.MergeDocuments(
                    new List<RLM_DocumentGenerationMerge.Request>{ request(ids, 'Pack') });
                System.assert(false, 'a merge with nothing to merge must be rejected');
            } catch (IllegalArgumentException e) {
                System.assert(e.getMessage().contains('at least one non-null Id'), e.getMessage());
            }
        }
        System.assertEquals(0, [SELECT COUNT() FROM DocumentGenerationProcess], 'nothing may be inserted on rejection');
    }
}

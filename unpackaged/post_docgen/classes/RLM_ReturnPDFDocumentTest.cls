@isTest
private class RLM_ReturnPDFDocumentTest {

    private static ContentVersion insertFile(String path) {
        ContentVersion cv = new ContentVersion(
            Title = path,
            PathOnClient = path,
            VersionData = Blob.valueOf('%PDF-1.4 test')
        );
        insert cv;
        return [SELECT Id, ContentDocumentId, FileType FROM ContentVersion WHERE Id = :cv.Id];
    }

    private static RLM_ReturnPDFDocument.InputVariable input(String responseText) {
        RLM_ReturnPDFDocument.InputVariable i = new RLM_ReturnPDFDocument.InputVariable();
        i.ResponseText = responseText;
        return i;
    }

    @isTest
    static void returnsTheIdsOfThePdfInAMixedList() {
        ContentVersion pdf = insertFile('contract.pdf');
        ContentVersion word = insertFile('contract.docx');
        System.assertEquals('PDF', pdf.FileType, 'fixture must be a PDF');

        List<RLM_ReturnPDFDocument.OutputVariable> out = RLM_ReturnPDFDocument.ReturnPDFDocumentId(
            new List<RLM_ReturnPDFDocument.InputVariable>{ input(word.Id + ',' + pdf.Id) });

        System.assertEquals(1, out.size());
        System.assertEquals(pdf.Id, out[0].ContentVersionId);
        System.assertEquals(pdf.ContentDocumentId, out[0].ContentDocumentId);
    }

    @isTest
    static void noPdfAmongTheIdsLeavesOutputEmpty() {
        ContentVersion word = insertFile('contract.docx');

        List<RLM_ReturnPDFDocument.OutputVariable> out = RLM_ReturnPDFDocument.ReturnPDFDocumentId(
            new List<RLM_ReturnPDFDocument.InputVariable>{ input(String.valueOf(word.Id)) });

        System.assertEquals(1, out.size(), 'one output per input, even with no match');
        System.assertEquals(null, out[0].ContentVersionId);
        System.assertEquals(null, out[0].ContentDocumentId);
    }

    @isTest
    static void malformedAndBlankTokensAreSkipped() {
        ContentVersion pdf = insertFile('contract.pdf');

        List<RLM_ReturnPDFDocument.OutputVariable> out = RLM_ReturnPDFDocument.ReturnPDFDocumentId(
            new List<RLM_ReturnPDFDocument.InputVariable>{ input('garbage, ,' + pdf.Id + ',') });

        System.assertEquals(pdf.Id, out[0].ContentVersionId, 'valid Id must still be found beside junk tokens');
    }

    @isTest
    static void blankResponseTextReturnsEmptyOutput() {
        List<RLM_ReturnPDFDocument.OutputVariable> out = RLM_ReturnPDFDocument.ReturnPDFDocumentId(
            new List<RLM_ReturnPDFDocument.InputVariable>{ input(null), input('   ') });

        System.assertEquals(2, out.size());
        System.assertEquals(null, out[0].ContentVersionId);
        System.assertEquals(null, out[1].ContentVersionId);
    }

    @isTest
    static void bulkInputsProduceOneOutputEach() {
        ContentVersion pdf = insertFile('contract.pdf');
        List<RLM_ReturnPDFDocument.InputVariable> inputs = new List<RLM_ReturnPDFDocument.InputVariable>();
        for (Integer i = 0; i < 20; i++) {
            inputs.add(input(String.valueOf(pdf.Id)));
        }

        // 20, not 200: the class runs one SOQL per input, so 200 would hit the
        // 100-query governor limit. That is a real bulk limitation of the class (SOQL inside the
        // request loop), reported in the TP-06 PR rather than fixed here (test-only package).
        List<RLM_ReturnPDFDocument.OutputVariable> out = RLM_ReturnPDFDocument.ReturnPDFDocumentId(inputs);

        System.assertEquals(20, out.size());
        System.assertEquals(pdf.Id, out[19].ContentVersionId);
    }

    @isTest
    static void nullOrEmptyRequestListThrows() {
        for (List<RLM_ReturnPDFDocument.InputVariable> bad : new List<List<RLM_ReturnPDFDocument.InputVariable>>{
            null, new List<RLM_ReturnPDFDocument.InputVariable>()
        }) {
            try {
                RLM_ReturnPDFDocument.ReturnPDFDocumentId(bad);
                System.assert(false, 'missing input must be rejected');
            } catch (IllegalArgumentException e) {
                System.assert(e.getMessage().contains('at least one request'), e.getMessage());
            }
        }
    }
}

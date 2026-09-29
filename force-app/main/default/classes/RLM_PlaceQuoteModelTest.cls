@isTest
private class RLM_PlaceQuoteModelTest {

    private static RLM_PlaceQuoteModel buildModel(Integer recordCount) {
        RLM_PlaceQuoteModel.QuoteGraphModel graph = new RLM_PlaceQuoteModel.QuoteGraphModel();
        graph.graphId = 'quoteGraph1';
        graph.records = new List<RLM_PlaceQuoteModel.ObjectRecordModel>();
        for (Integer i = 0; i < recordCount; i++) {
            RLM_PlaceQuoteModel.ObjectRecordModel rec = new RLM_PlaceQuoteModel.ObjectRecordModel();
            rec.referenceId = 'ref' + i;
            rec.record = new Map<String, Object>{ 'Name' => 'Quote ' + i };
            graph.records.add(rec);
        }

        RLM_PlaceQuoteModel model = new RLM_PlaceQuoteModel();
        model.pricingPref = 'System';
        model.configurationInput = 'Skip';
        model.configurationOptions = new Map<String, Boolean>{
            'validateProductCatalog' => true,
            'validateAmendRenewCancel' => false
        };
        model.graph = graph;
        return model;
    }

    @isTest
    static void roundTripsThroughJson() {
        String payload = JSON.serialize(buildModel(2));
        RLM_PlaceQuoteModel copy = (RLM_PlaceQuoteModel) JSON.deserialize(payload, RLM_PlaceQuoteModel.class);

        System.assertEquals('System', copy.pricingPref);
        System.assertEquals('Skip', copy.configurationInput);
        System.assertEquals(true, copy.configurationOptions.get('validateProductCatalog'));
        System.assertEquals(false, copy.configurationOptions.get('validateAmendRenewCancel'));
        System.assertEquals('quoteGraph1', copy.graph.graphId);
        System.assertEquals(2, copy.graph.records.size());
        System.assertEquals('ref1', copy.graph.records[1].referenceId);
        System.assertEquals('Quote 1', copy.graph.records[1].record.get('Name'));
    }

    @isTest
    static void bulkRecordListSurvivesRoundTrip() {
        Integer total = RLM_TestDataFactory.BULK_SIZE;
        RLM_PlaceQuoteModel copy = (RLM_PlaceQuoteModel) JSON.deserialize(
            JSON.serialize(buildModel(total)), RLM_PlaceQuoteModel.class);

        System.assertEquals(total, copy.graph.records.size());
        System.assertEquals('ref' + (total - 1), copy.graph.records[total - 1].referenceId);
    }

    @isTest
    static void emptyModelRoundTripsWithNullGraph() {
        RLM_PlaceQuoteModel copy = (RLM_PlaceQuoteModel) JSON.deserialize(
            JSON.serialize(new RLM_PlaceQuoteModel()), RLM_PlaceQuoteModel.class);

        System.assertEquals(null, copy.graph);
        System.assertEquals(null, copy.pricingPref);
    }
}

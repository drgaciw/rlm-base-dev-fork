@isTest
private class RLM_PlaceOrderModelTest {

    private static RLM_PlaceOrderModel buildModel(Integer recordCount) {
        RLM_PlaceOrderModel.OrderGraphModel graph = new RLM_PlaceOrderModel.OrderGraphModel();
        graph.graphId = 'orderGraph1';
        graph.records = new List<RLM_PlaceOrderModel.ObjectRecordModel>();
        for (Integer i = 0; i < recordCount; i++) {
            RLM_PlaceOrderModel.ObjectRecordModel rec = new RLM_PlaceOrderModel.ObjectRecordModel();
            rec.referenceId = 'ref' + i;
            rec.record = new Map<String, Object>{ 'Name' => 'Order ' + i };
            graph.records.add(rec);
        }

        RLM_PlaceOrderModel model = new RLM_PlaceOrderModel();
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
        RLM_PlaceOrderModel copy = (RLM_PlaceOrderModel) JSON.deserialize(payload, RLM_PlaceOrderModel.class);

        System.assertEquals('System', copy.pricingPref);
        System.assertEquals('Skip', copy.configurationInput);
        System.assertEquals(true, copy.configurationOptions.get('validateProductCatalog'));
        System.assertEquals(false, copy.configurationOptions.get('validateAmendRenewCancel'));
        System.assertEquals('orderGraph1', copy.graph.graphId);
        System.assertEquals(2, copy.graph.records.size());
        System.assertEquals('ref1', copy.graph.records[1].referenceId);
        System.assertEquals('Order 1', copy.graph.records[1].record.get('Name'));
    }

    @isTest
    static void bulkRecordListSurvivesRoundTrip() {
        Integer total = RLM_TestDataFactory.BULK_SIZE;
        RLM_PlaceOrderModel copy = (RLM_PlaceOrderModel) JSON.deserialize(
            JSON.serialize(buildModel(total)), RLM_PlaceOrderModel.class);

        System.assertEquals(total, copy.graph.records.size());
        System.assertEquals('ref' + (total - 1), copy.graph.records[total - 1].referenceId);
    }

    @isTest
    static void emptyModelRoundTripsWithNullGraph() {
        RLM_PlaceOrderModel copy = (RLM_PlaceOrderModel) JSON.deserialize(
            JSON.serialize(new RLM_PlaceOrderModel()), RLM_PlaceOrderModel.class);

        System.assertEquals(null, copy.graph);
        System.assertEquals(null, copy.pricingPref);
    }
}

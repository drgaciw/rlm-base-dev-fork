@isTest
private class RLM_DFOTenantProvisioningCalloutTest {

    // Well-formed Account Id: no DML, no hard-coded Id literal.
    private static final String ACCOUNT_ID = String.valueOf(RLM_TestDataFactory.wellFormedId(Account.SObjectType, 1));

    private class CalloutMock implements HttpCalloutMock {
        private final Integer statusCode;
        private final String body;
        public Integer calls = 0;
        public HttpRequest lastRequest;

        CalloutMock(Integer statusCode, String body) {
            this.statusCode = statusCode;
            this.body = body;
        }

        public HttpResponse respond(HttpRequest req) {
            calls++;
            lastRequest = req;
            HttpResponse res = new HttpResponse();
            res.setStatusCode(statusCode);
            res.setBody(body);
            return res;
        }
    }

    // DML is committed here so the callout in the test method is not blocked by
    // "uncommitted work pending".
    @TestSetup
    static void setup() {
        Account acct = RLM_TestDataFactory.createAccount();
        Product2 product = RLM_TestDataFactory.createProduct('DFO Provisioning Product');
        PricebookEntry pbe = RLM_TestDataFactory.createStandardPricebookEntry(product.Id, 100);
        Order o = RLM_TestDataFactory.createOrder(acct.Id);
        RLM_TestDataFactory.createOrderItem(o.Id, pbe);
    }

    @isTest
    static void orderItemSourcePostsTheOrderIdToTheTenantEndpoint() {
        OrderItem oi = [SELECT Id, OrderId FROM OrderItem LIMIT 1];
        CalloutMock mock = new CalloutMock(200, '{"tenantId":"t-1"}');
        Test.setMock(HttpCalloutMock.class, mock);

        Test.startTest();
        industriesintegrationfwk.IntegrationCalloutResponse response =
            RLM_DFOTenantProvisioningCallout.executeCallout('guid-1', oi.Id, '{}', new Map<String, Object>());
        Test.stopTest();

        System.assertNotEquals(null, response);
        System.assertEquals(1, mock.calls, 'exactly one callout per provisioning request');
        System.assertEquals('POST', mock.lastRequest.getMethod());
        System.assert(mock.lastRequest.getEndpoint().endsWith('/services/apexrest/QuantumBitTenantEnvironment/createNewTenant'),
            'unexpected endpoint: ' + mock.lastRequest.getEndpoint());
        System.assertEquals('application/json', mock.lastRequest.getHeader('Content-Type'));
        Map<String, Object> sent = (Map<String, Object>) JSON.deserializeUntyped(mock.lastRequest.getBody());
        System.assertEquals(String.valueOf(oi.OrderId), sent.get('orderId'));
    }

    @isTest
    static void nonJsonErrorResponseDoesNotBreakTheProvider() {
        OrderItem oi = [SELECT Id FROM OrderItem LIMIT 1];
        CalloutMock mock = new CalloutMock(500, '<html>upstream error</html>');
        Test.setMock(HttpCalloutMock.class, mock);

        Test.startTest();
        industriesintegrationfwk.IntegrationCalloutResponse response =
            RLM_DFOTenantProvisioningCallout.executeCallout('guid-2', oi.Id, '{}', new Map<String, Object>());
        Test.stopTest();

        System.assertNotEquals(null, response, 'a non-JSON body must be wrapped, not thrown');
        System.assertEquals(1, mock.calls);
    }

    @isTest
    static void unrelatedSourceObjectMakesNoCallout() {
        CalloutMock mock = new CalloutMock(200, '{}');
        Test.setMock(HttpCalloutMock.class, mock);

        Test.startTest();
        industriesintegrationfwk.IntegrationCalloutResponse response =
            RLM_DFOTenantProvisioningCallout.executeCallout('guid-3', ACCOUNT_ID, '{}', new Map<String, Object>());
        Test.stopTest();

        System.assertNotEquals(null, response);
        System.assertEquals(0, mock.calls, 'only OrderItem and FulfillmentOrderLineItem sources may call out');
    }

    @isTest
    static void malformedSourceIdThrows() {
        try {
            RLM_DFOTenantProvisioningCallout.executeCallout('guid-4', 'not-an-id', '{}', new Map<String, Object>());
            System.assert(false, 'a malformed source Id must not be silently accepted');
        } catch (System.StringException e) {
            System.assert(true);
        }
    }

    @isTest
    static void providerDeclaresNoDefaultAttributes() {
        System.assert(new RLM_DFOTenantProvisioningCallout().getProviderAttributes().isEmpty());
    }
}

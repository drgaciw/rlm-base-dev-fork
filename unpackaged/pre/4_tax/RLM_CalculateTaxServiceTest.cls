/**
 * Covers the tax-adapter family in unpackaged/pre/4_tax as one unit, because they share one
 * request/response contract (commercetax.*): RLM_CalculateTaxService, RLM_AvalaraAdapter,
 * RLM_MockTaxAdapter, RLM_MockAppAdapter, RLM_InvalidAdapter.
 *
 * Limits of what can be asserted:
 *  - commercetax response classes expose setters only, so tests assert the response TYPE
 *    (CalculateTaxResponse vs ErrorResponse) and that no exception escapes, not field values.
 *  - RLM_CalculateTaxService returns a canned body under Test.isRunningTest(), so its error branch
 *    (Avalara `error` payload) cannot be driven from a test; the success branch and the guard
 *    paths (no lines, unusable request) are covered.
 *  - commercetax.RequestType has a single value (CalculateTax), so the adapters' `else return null`
 *    branches are unreachable from a test.
 *
 * Every commercetax request object is built with the constructors the platform documents as
 * test-only (they throw outside an Apex test).
 */
@isTest
private class RLM_CalculateTaxServiceTest {

    // Local on purpose: unpackaged/pre is deployed independently of force-app, so this class must
    // not depend on RLM_TestDataFactory.
    private static final Integer BULK_SIZE = 200;

    private class AvalaraMock implements HttpCalloutMock {
        public Integer calls = 0;
        public HttpResponse respond(HttpRequest req) {
            calls++;
            HttpResponse res = new HttpResponse();
            res.setStatusCode(200);
            res.setBody('{}');
            return res;
        }
    }

    private static commercetax.TaxAddressRequest address() {
        return new commercetax.TaxAddressRequest('Seattle', 'US', 47.6, -122.3, '98104', 'WA', '255 S King St', 'LOC1');
    }

    private static commercetax.TaxLineItemRequest line(Double amount, String lineNumber) {
        commercetax.LineTaxAddressesRequest addresses =
            new commercetax.LineTaxAddressesRequest(address(), address(), address(), address(), address());
        return new commercetax.TaxLineItemRequest(addresses, amount, 'desc', 'PROD-1', 1.0, lineNumber, 'P0000000', null);
    }

    private static commercetax.CalculateTaxRequest request(String documentCode, List<commercetax.TaxLineItemRequest> lines) {
        commercetax.CalculateTaxRequest req = new commercetax.CalculateTaxRequest(commercetax.CalculateTaxType.Actual);
        req.documentCode = documentCode;
        req.referenceEntityId = 'REF-ENTITY-1';
        req.currencyIsoCode = 'USD';
        req.taxTransactionType = commercetax.TaxTransactionType.Debit;
        req.sellerDetails = new commercetax.TaxSellerDetailsRequest('testSellerCode');
        req.customerDetails = new commercetax.TaxCustomerDetailsRequest(null, 'CUST-1', null, null);
        req.lineItems = lines;
        return req;
    }

    private static commercetax.TaxEngineContext context(commercetax.CalculateTaxRequest req) {
        return new commercetax.TaxEngineContext(req, commercetax.RequestType.CalculateTax, 'callout:test');
    }

    private static List<commercetax.TaxLineItemRequest> oneLine() {
        return new List<commercetax.TaxLineItemRequest>{ line(100, '1') };
    }

    // ---- RLM_MockTaxAdapter ----

    @isTest
    static void mockTaxAdapterReturnsCalculateTaxResponseForAValidRequest() {
        commercetax.TaxEngineResponse res =
            new RLM_MockTaxAdapter().processRequest(context(request('DOC-1', oneLine())));

        System.assert(res instanceof commercetax.CalculateTaxResponse, 'expected a tax response, got ' + res);
    }

    @isTest
    static void mockTaxAdapterHandlesBulkLines() {
        List<commercetax.TaxLineItemRequest> lines = new List<commercetax.TaxLineItemRequest>();
        for (Integer i = 0; i < BULK_SIZE; i++) {
            lines.add(line(10 + i, String.valueOf(i + 1)));
        }

        commercetax.TaxEngineResponse res = new RLM_MockTaxAdapter().processRequest(context(request('DOC-BULK', lines)));

        System.assert(res instanceof commercetax.CalculateTaxResponse);
    }

    @isTest
    static void mockTaxAdapterRejectsMissingDocumentCode() {
        commercetax.TaxEngineResponse res = new RLM_MockTaxAdapter().processRequest(context(request(null, oneLine())));

        System.assert(res instanceof commercetax.ErrorResponse, 'documentCode is mandatory');
    }

    @isTest
    static void mockTaxAdapterSimulatedErrorCodesReturnErrorResponses() {
        for (String code : new List<String>{
            'TaxEngineError', 'simulateValidationFailureInAdapter',
            'simulateMalformedErrorInAdapter', 'simulateTaxEngineProcessFailure'
        }) {
            commercetax.TaxEngineResponse res = new RLM_MockTaxAdapter().processRequest(context(request(code, oneLine())));
            System.assert(res instanceof commercetax.ErrorResponse, code + ' must produce an ErrorResponse');
        }
    }

    @isTest
    static void mockTaxAdapterUnhandledExceptionPropagates() {
        try {
            new RLM_MockTaxAdapter().processRequest(context(request('simulateUnhandledExceptionInAdapter', oneLine())));
            System.assert(false, 'the simulated divide-by-zero must escape the adapter');
        } catch (System.MathException e) {
            System.assert(true);
        }
    }

    @isTest
    static void mockTaxAdapterNoLinesDocumentCodeOmitsLineItems() {
        commercetax.TaxEngineResponse res = new RLM_MockTaxAdapter().processRequest(context(request('nolines', oneLine())));

        System.assert(res instanceof commercetax.CalculateTaxResponse);
    }

    @isTest
    static void mockTaxAdapterRandomDocCodeAndNullSafeVariants() {
        // 'SetsNullFor…' codes drive the null-address branches without throwing.
        for (String code : new List<String>{ 'SetsNullForResponseWithoutException' }) {
            commercetax.TaxEngineResponse res = new RLM_MockTaxAdapter().processRequest(context(request(code, oneLine())));
            System.assert(res instanceof commercetax.CalculateTaxResponse, code);
        }
        System.assertNotEquals(null, RLM_MockTaxAdapter.getRandomInteger(0, 10));
    }

    // ---- RLM_MockAppAdapter ----

    @isTest
    static void mockAppAdapterReturnsCalculateTaxResponseForAValidRequest() {
        commercetax.TaxEngineResponse res =
            new RLM_MockAppAdapter().processRequest(context(request('DOC-2', oneLine())));

        System.assert(res instanceof commercetax.CalculateTaxResponse);
    }

    @isTest
    static void mockAppAdapterSimulatedErrorsReturnErrorResponses() {
        for (String code : new List<String>{
            'TaxEngineErrorX', 'simulateValidationFailureInAdapter', 'simulateTaxEngineProcessFailure'
        }) {
            commercetax.TaxEngineResponse res = new RLM_MockAppAdapter().processRequest(context(request(code, oneLine())));
            System.assert(res instanceof commercetax.ErrorResponse, code + ' must produce an ErrorResponse');
        }
    }

    @isTest
    static void mockAppAdapterMagicAmountsReturnErrorResponses() {
        for (Double amount : new List<Double>{ 100.999, -100.999, 101, -101 }) {
            commercetax.TaxEngineResponse res = new RLM_MockAppAdapter().processRequest(
                context(request('DOC-3', new List<commercetax.TaxLineItemRequest>{ line(amount, '1') })));
            System.assert(res instanceof commercetax.ErrorResponse, 'amount ' + amount + ' is a simulated failure');
        }
    }

    @isTest
    static void mockAppAdapterReferenceDocumentCodeSimulatesEngineError() {
        commercetax.CalculateTaxRequest req = request('DOC-4', oneLine());
        req.referenceDocumentCode = 'simulateTaxEngineError';

        System.assert(new RLM_MockAppAdapter().processRequest(context(req)) instanceof commercetax.ErrorResponse);
    }

    @isTest
    static void mockAppAdapterUnhandledExceptionPropagates() {
        try {
            new RLM_MockAppAdapter().processRequest(context(request('simulateUnhandledExceptionInAdapter', oneLine())));
            System.assert(false, 'the simulated divide-by-zero must escape the adapter');
        } catch (System.MathException e) {
            System.assert(true);
        }
    }

    @isTest
    static void mockAppAdapterNullVariantsDoNotThrow() {
        for (String code : new List<String>{ 'SetsNullForResponseWithoutException', 'nolines' }) {
            commercetax.TaxEngineResponse res = new RLM_MockAppAdapter().processRequest(context(request(code, oneLine())));
            System.assert(res instanceof commercetax.CalculateTaxResponse, code);
        }
        System.assertNotEquals(null, RLM_MockAppAdapter.getRandomInteger(0, 10));
    }

    // ---- RLM_InvalidAdapter ----

    @isTest
    static void invalidAdapterAlwaysReturnsNull() {
        System.assertEquals(null, new RLM_InvalidAdapter().processRequest(context(request('DOC-5', oneLine()))));
    }

    // ---- RLM_AvalaraAdapter / RLM_CalculateTaxService ----

    @isTest
    static void avalaraAdapterRoutesCalculateTaxToTheService() {
        AvalaraMock mock = new AvalaraMock();
        Test.setMock(HttpCalloutMock.class, mock);

        Test.startTest();
        commercetax.TaxEngineResponse res = new RLM_AvalaraAdapter().processRequest(context(request('DOC-6', oneLine())));
        Test.stopTest();

        // Under a test the service swaps the live body for a canned Avalara response but still
        // issues (and, with a mock, completes) the callout.
        System.assert(res instanceof commercetax.CalculateTaxResponse, 'expected a tax response, got ' + res);
        System.assertEquals(1, mock.calls, 'exactly one Avalara callout per tax request');
    }

    @isTest
    static void calculateTaxServiceReturnsNullWhenThereAreNoLines() {
        commercetax.TaxEngineResponse res = RLM_CalculateTaxService.getTax(
            context(request('DOC-7', new List<commercetax.TaxLineItemRequest>())));

        System.assertEquals(null, res, 'nothing to tax -> no response and no callout');
    }

    @isTest
    static void calculateTaxServiceRethrowsWhenTheRequestCannotBeFramed() {
        commercetax.CalculateTaxRequest req = request('DOC-8', oneLine());
        req.customerDetails = null; // the JSON builder dereferences customerDetails

        try {
            RLM_CalculateTaxService.getTax(context(req));
            System.assert(false, 'an unframeable request must not be swallowed');
        } catch (System.NullPointerException e) {
            System.assert(true);
        }
    }
}

@isTest
private class RLM_AA_Submit_ApprovalTest {

    private static RLM_AA_Submit_Approval.svcParameter params(String flowName) {
        RLM_AA_Submit_Approval.svcParameter p = new RLM_AA_Submit_Approval.svcParameter();
        p.flowName = flowName;
        p.recordId = '0Q0000000000001AAA';
        p.approvalLevel = 'Level1';
        p.comments = 'please approve';
        return p;
    }

    @isTest
    static void parameterHolderKeepsAllFields() {
        RLM_AA_Submit_Approval.svcParameter p = params('Some_Flow');

        System.assertEquals('Some_Flow', p.flowName);
        System.assertEquals('0Q0000000000001AAA', p.recordId);
        System.assertEquals('Level1', p.approvalLevel);
        System.assertEquals('please approve', p.comments);
    }

    // Failure path: an unknown flow API name must surface, not be swallowed, so the calling
    // orchestration sees the submission failed.
    @isTest
    static void unknownFlowNameSurfacesAnError() {
        Boolean threw = false;
        try {
            RLM_AA_Submit_Approval.callFlow(new List<RLM_AA_Submit_Approval.svcParameter>{
                params('RLM_No_Such_Flow_For_Test')
            });
        } catch (Exception e) {
            threw = true;
        }
        System.assert(threw, 'starting a flow that does not exist must fail');
    }

    @isTest
    static void emptyParameterListThrows() {
        try {
            RLM_AA_Submit_Approval.callFlow(new List<RLM_AA_Submit_Approval.svcParameter>());
            System.assert(false, 'an empty invocable input list is a caller bug and must surface');
        } catch (System.ListException e) {
            System.assert(true);
        }
    }

    // Happy path: the class only forwards the five inputs to Flow.Interview. The shipped autolaunched
    // flow that consumes them (RLM_Quote_Smart_Approval etc.) needs a submitted Quote and orchestration
    // runtime, which a hermetic test cannot stand up — that end to end path belongs to the nightly run.
}

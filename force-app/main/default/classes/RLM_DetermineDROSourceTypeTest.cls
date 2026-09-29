@isTest
private class RLM_DetermineDROSourceTypeTest {

    // Well-formed Ids need no DML and no hard-coded Id literal.
    private static final String ACCOUNT_ID = String.valueOf(RLM_TestDataFactory.wellFormedId(Account.SObjectType, 1));
    private static final String ORDER_ITEM_ID = String.valueOf(RLM_TestDataFactory.wellFormedId(OrderItem.SObjectType, 1));

    private static RLM_DetermineDROSourceType.droSourceInfo info(String recordId, List<String> recordIds) {
        RLM_DetermineDROSourceType.droSourceInfo i = new RLM_DetermineDROSourceType.droSourceInfo();
        i.recordId = recordId;
        i.recordIds = recordIds;
        return i;
    }

    @isTest
    static void singleRecordIdReturnsSObjectName() {
        List<String> result = RLM_DetermineDROSourceType.returnDROSourceObjectType(
            new List<RLM_DetermineDROSourceType.droSourceInfo>{ info(ACCOUNT_ID, null) });

        System.assertEquals(1, result.size());
        System.assertEquals('Account', result[0]);
    }

    @isTest
    static void recordIdTakesPrecedenceOverRecordIds() {
        List<String> result = RLM_DetermineDROSourceType.returnDROSourceObjectType(
            new List<RLM_DetermineDROSourceType.droSourceInfo>{
                info(ACCOUNT_ID, new List<String>{ ORDER_ITEM_ID })
            });

        System.assertEquals(new List<String>{ 'Account' }, result);
    }

    @isTest
    static void recordIdsReturnsPluralisedSObjectName() {
        List<String> result = RLM_DetermineDROSourceType.returnDROSourceObjectType(
            new List<RLM_DetermineDROSourceType.droSourceInfo>{
                info(null, new List<String>{ ACCOUNT_ID, ORDER_ITEM_ID })
            });

        // Only the first Id decides the type; the trailing 's' marks the collection form.
        System.assertEquals(new List<String>{ 'Accounts' }, result);
    }

    @isTest
    static void noIdsReturnsEmptyList() {
        List<String> result = RLM_DetermineDROSourceType.returnDROSourceObjectType(
            new List<RLM_DetermineDROSourceType.droSourceInfo>{ info(null, null) });

        System.assert(result.isEmpty(), 'no source Id must yield an empty result, not an error');
    }

    @isTest
    static void malformedRecordIdThrows() {
        try {
            RLM_DetermineDROSourceType.returnDROSourceObjectType(
                new List<RLM_DetermineDROSourceType.droSourceInfo>{ info('not-an-id', null) });
            System.assert(false, 'a malformed record Id must not be silently accepted');
        } catch (System.StringException e) {
            System.assert(e.getMessage().containsIgnoreCase('not-an-id') || e.getMessage().containsIgnoreCase('Id'),
                'unexpected message: ' + e.getMessage());
        }
    }

    @isTest
    static void emptyInputListThrows() {
        try {
            RLM_DetermineDROSourceType.returnDROSourceObjectType(new List<RLM_DetermineDROSourceType.droSourceInfo>());
            System.assert(false, 'an empty invocable input list is a caller bug and must surface');
        } catch (System.ListException e) {
            System.assert(true);
        }
    }
}

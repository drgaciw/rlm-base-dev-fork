// Post-build check: assert the RLM_QuotingAssistant permission set grants what
// RLM_AI_UpdateRecordFieldsService (AccessLevel.USER_MODE) needs at runtime.
//
// Why this is a script and not an Apex test: prepare_agents deploys the classes
// (step 3) long before the permission sets (step 9, after publish_agents), and
// Apex tests cannot see grants that do not exist yet. Run it after prepare_agents
// (nightly: flow ci_verify_agent_permsets, task verify_agent_permset_grants).
//
// Grants asserted (mirror unpackaged/post_agents/permissionsets/RLM_QuotingAssistant.permissionset-meta.xml):
//   Object : Quote edit
//   Fields : Quote.Description / ExpirationDate / Status edit
//            QuoteLineItem.StartDate / EndDate / Description edit
// QuoteLineItem has no ObjectPermissions row by design (master-detail child of Quote;
// its CRUD is derived from the Quote grant), so only its field grants are asserted.
//
// Fails the run (unhandled exception -> non-zero CCI exit) listing EVERY mismatch, so
// one nightly run shows the full picture instead of one blocker per rerun.

// Custom type: several built-in exceptions (e.g. NoAccessException) can only be thrown
// from Visualforce/Aura context, and the built-in Exception is abstract.
public class GrantVerificationException extends Exception {}

final String PERMSET_NAME = 'RLM_QuotingAssistant';
final String OBJECT_EDIT = 'Quote';
final Set<String> FIELD_EDITS = new Set<String>{
    'Quote.Description',
    'Quote.ExpirationDate',
    'Quote.Status',
    'QuoteLineItem.StartDate',
    'QuoteLineItem.EndDate',
    'QuoteLineItem.Description'
};

List<String> problems = new List<String>();

List<PermissionSet> permSets = [SELECT Id FROM PermissionSet WHERE Name = :PERMSET_NAME LIMIT 1];
if (permSets.isEmpty()) {
    // Nothing else can be checked without the permission set.
    throw new GrantVerificationException(
        'verify_agent_permset_grants FAILED: permission set ' + PERMSET_NAME +
        ' does not exist (deploy_agent_permission_sets did not run or failed).'
    );
}
Id permSetId = permSets[0].Id;

// Object grant: query once, look the object up in memory.
Map<String, ObjectPermissions> objectPerms = new Map<String, ObjectPermissions>();
for (ObjectPermissions op : [
    SELECT SobjectType, PermissionsRead, PermissionsEdit
    FROM ObjectPermissions
    WHERE ParentId = :permSetId
]) {
    objectPerms.put(op.SobjectType, op);
}
ObjectPermissions quotePerm = objectPerms.get(OBJECT_EDIT);
if (quotePerm == null) {
    problems.add(OBJECT_EDIT + ': no ObjectPermissions row');
} else if (!quotePerm.PermissionsEdit) {
    problems.add(OBJECT_EDIT + ': PermissionsEdit is false');
}

// Field grants: one query for both objects, then compare against the expected set.
Map<String, FieldPermissions> fieldPerms = new Map<String, FieldPermissions>();
for (FieldPermissions fp : [
    SELECT Field, PermissionsRead, PermissionsEdit
    FROM FieldPermissions
    WHERE ParentId = :permSetId AND SobjectType IN ('Quote', 'QuoteLineItem')
]) {
    fieldPerms.put(fp.Field, fp);
}
List<String> expectedFields = new List<String>(FIELD_EDITS);
expectedFields.sort();
for (String field : expectedFields) {
    FieldPermissions fp = fieldPerms.get(field);
    if (fp == null) {
        problems.add(field + ': no FieldPermissions row');
    } else if (!fp.PermissionsEdit) {
        problems.add(field + ': PermissionsEdit is false');
    }
}

if (!problems.isEmpty()) {
    throw new GrantVerificationException(
        'verify_agent_permset_grants FAILED for ' + PERMSET_NAME + ' (' + problems.size() +
        ' mismatch(es)): ' + String.join(problems, '; ')
    );
}
System.debug(LoggingLevel.ERROR, 'verify_agent_permset_grants OK: ' + PERMSET_NAME +
    ' grants Quote edit and ' + FIELD_EDITS.size() + ' Quote/QuoteLineItem field edits.');

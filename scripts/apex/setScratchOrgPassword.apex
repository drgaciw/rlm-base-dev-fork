// Sets a permanent password for the running scratch-org admin user.
//
// Why: some scratch org definitions (notably the TSO / trialforce-derived
// templates such as tfid-cdo-rlm) flag the admin user to "change password at
// next login". When a Robot/Selenium setup step then logs in via
// `sf org open --url-only` (frontdoor), Salesforce redirects to the
// "Change Your Password" screen instead of the requested Setup page, so every
// UI toggle lookup (prepare_docgen, prepare_revenue_settings, etc.) fails on
// the wrong page. Calling System.setPassword installs a permanent password and
// clears the must-reset flag, so frontdoor login lands directly on Setup.
//
// Scratch-org guard: aborts (no-op) unless the target org's own Organization
// record has the scratch-org signature (IsSandbox = true AND a populated
// TrialExpirationDate — regular sandboxes are IsSandbox = true but never
// expire, so TrialExpirationDate is null there). Never runs against a
// persistent org, sandbox or otherwise.
//
// Password source (A-C4, docs/ARCHITECT_REVIEW.md WP-11): CumulusCI 4.8.1's
// AnonymousApexTask only substitutes %%%PARAM_1%%% / %%%PARAM_2%%% (from the
// task's `param1`/`param2` options); there is no `apex_options` mechanism, so
// the old %%%SCRATCH_ORG_PASSWORD%%% token was never substituted and this
// branch was dead code. Pass a password via:
//   cci task run set_scratch_org_password --org <alias> -o param1 <base64-of-password>
// The value MUST be base64-encoded before passing -o param1: CumulusCI does a
// raw text substitution of %%%PARAM_1%%% into this .apex file's SOURCE before
// it is compiled, with no escaping of its own, so an unescaped `'` or `\` in
// the raw password would corrupt the Apex string literal below (or worse,
// change what the script does). Base64 output is always a safe Apex string
// literal (only [A-Za-z0-9+/=]), so this sidesteps that without needing a
// custom CumulusCI task. Example: `-o param1 "$(printf '%s' 'MyP@ss1!' | base64)"`.
// When param1 is omitted, a fresh random password is generated instead so the
// org never ends up with a predictable password; the generator guarantees at
// least one uppercase, one lowercase, one digit and one special character so
// it always satisfies Salesforce's default password policy (an unconstrained
// random draw from the full charset misses at least one required class about
// 30% of the time in the worst case, e.g. P(no digit) ~= 0.11).
//
// Idempotent: safe to re-run; it simply (re)sets the current password.
String injectedPwdB64 = '%%%PARAM_1%%%';
String pwd;
if (injectedPwdB64 != null && injectedPwdB64.length() > 0 && injectedPwdB64.indexOf('%%%') < 0) {
    pwd = EncodingUtil.base64Decode(injectedPwdB64).toString();
} else {
    String upperChars = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
    String lowerChars = 'abcdefghijkmnpqrstuvwxyz';
    String digitChars = '23456789';
    String specialChars = '!@#$%^*';
    String allChars = upperChars + lowerChars + digitChars + specialChars;
    List<String> requiredSets = new List<String>{ upperChars, lowerChars, digitChars, specialChars };

    List<String> pwdChars = new List<String>();
    for (String reqSet : requiredSets) {
        Integer idx = Math.mod(Math.abs(Crypto.getRandomInteger()), reqSet.length());
        pwdChars.add(reqSet.substring(idx, idx + 1));
    }
    for (Integer i = pwdChars.size(); i < 16; i++) {
        Integer idx = Math.mod(Math.abs(Crypto.getRandomInteger()), allChars.length());
        pwdChars.add(allChars.substring(idx, idx + 1));
    }
    // Fisher-Yates shuffle so the guaranteed classes aren't always in positions 0-3.
    for (Integer i = pwdChars.size() - 1; i > 0; i--) {
        Integer j = Math.mod(Math.abs(Crypto.getRandomInteger()), i + 1);
        String tmp = pwdChars[i];
        pwdChars[i] = pwdChars[j];
        pwdChars[j] = tmp;
    }
    pwd = String.join(pwdChars, '');
}

try {
    List<Organization> orgs = [SELECT IsSandbox, TrialExpirationDate FROM Organization LIMIT 1];
    Boolean isScratchOrg = !orgs.isEmpty() && orgs[0].IsSandbox && orgs[0].TrialExpirationDate != null;
    if (!isScratchOrg) {
        System.debug(LoggingLevel.WARN, 'setScratchOrgPassword aborted: target org does not have the scratch-org signature (IsSandbox + TrialExpirationDate).');
    } else {
        System.setPassword(UserInfo.getUserId(), pwd);
        System.debug('Scratch org admin password set; must-reset flag cleared.');
    }
} catch (Exception e) {
    // Don't fail the build if the org doesn't allow setPassword — stay defensive
    // even though the guard above should already exclude non-scratch orgs.
    System.debug(LoggingLevel.WARN, 'setScratchOrgPassword skipped: ' + e.getMessage());
}

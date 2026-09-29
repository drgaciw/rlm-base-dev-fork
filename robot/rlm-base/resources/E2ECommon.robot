*** Settings ***
Documentation     Shared keywords for E2E functional tests. Provides navigation,
...               QuickAction interaction, async polling, browser lifecycle management,
...               and verification keywords. Authentication is handled by the calling suite.
Library           SeleniumLibrary    timeout=15    implicit_wait=5
Library           Collections
Library           String
Library           Process
Library           DateTime
Library           ${EXECDIR}/robot/rlm-base/resources/WebDriverManager.py    WITH NAME    WebDriverManager
Library           ${EXECDIR}/robot/rlm-base/resources/ChromeOptionsHelper.py
Library           ${EXECDIR}/robot/rlm-base/resources/ChromeDebugHelper.py
Library           ${EXECDIR}/robot/rlm-base/resources/SalesforceAPI.py    WITH NAME    SalesforceAPI

*** Variables ***
${ORG_ALIAS}                ${EMPTY}
${HEADED}                   false
${PAUSE_FOR_RECORDING}      false
${PAGE_LOAD_TIMEOUT}        30s
${SETTLE_TIMEOUT}          15s
${SCREENSHOT_COUNTER}       ${0}

*** Keywords ***

# ── Browser Management ──────────────────────────────────────────────

Open Browser For E2E
    [Documentation]    Opens Chrome in headed (visible + CDP debug) or headless mode
    ...    based on the \${HEADED} variable. Headed mode enables remote debugging
    ...    on port 9222 for Chrome DevTools / CDP connections.
    IF    "${HEADED}" == "true"
        _Open Chrome Headed
    ELSE
        _Open Chrome Headless
    END
    Set Window Size    1920    1080

_Open Chrome Headed
    [Documentation]    Opens Chrome in visible mode with CDP debugging port.
    ${options}=    Get Visible Chrome Options
    ${path}=    WebDriverManager.Get Chrome Driver Path
    IF    "${path}" != "None" and "${path}" != ""
        ${service}=    Evaluate    selenium.webdriver.chrome.service.Service(executable_path=$path)    selenium.webdriver.chrome.service
        Create Webdriver    Chrome    service=${service}    options=${options}
    ELSE
        Create Webdriver    Chrome    options=${options}
    END
    Go To    about:blank

_Open Chrome Headless
    [Documentation]    Opens Chrome in headless mode (same as setup tests).
    ${options}=    Get Headless Chrome Options
    ${path}=    WebDriverManager.Get Chrome Driver Path
    IF    "${path}" != "None" and "${path}" != ""
        ${service}=    Evaluate    selenium.webdriver.chrome.service.Service(executable_path=$path)    selenium.webdriver.chrome.service
        Create Webdriver    Chrome    service=${service}    options=${options}
    ELSE
        Create Webdriver    Chrome    options=${options}
    END
    Go To    about:blank

Close Browser For E2E
    [Documentation]    Closes the browser session.
    Close Browser

# ── Condition Waits (TP-08b: replace fixed Sleeps) ──────────────────
# Strict waits (Wait Until Keyword Succeeds, Wait Until Element ..., REST polls) assert a
# positive signal and fail the test on timeout. The helpers below are BEST-EFFORT: on timeout
# they log a structured WARN `SETTLE_TIMEOUT` line naming the calling keyword and the timeout
# (counted in the e2e stage summary) and continue. Every best-effort wait must be anchored by a
# strict wait or assertion before the next click/input -- tests/test_robot_sleep_ratchet.py
# enforces that.
# E2E path only: never use these from tests/setup/* or SetupToggles.robot.

Wait Until Page Is Settled
    [Documentation]    Best-effort settle for clicks that expose no DOM signal of their own.
    ...    Returns once the document is complete, no Lightning spinner is visible and the DOM
    ...    (shadow roots included) has kept the same node count and text length for
    ...    stable_polls consecutive 500 ms polls. Capped at timeout; on timeout it logs the
    ...    structured WARN SETTLE_TIMEOUT and continues.
    ...
    ...    ⚠ This is NOT an assertion. It cannot see a page that has not started to change
    ...    yet, so anchor every use with a strict wait or assertion before the next click.
    [Arguments]    ${caller}=unknown    ${timeout}=${SETTLE_TIMEOUT}    ${stable_polls}=${2}
    Execute JavaScript    window.__e2eSettle = {sig: null, stable: 0};
    _Wait Best Effort    ${caller}    ${timeout}    500ms    _Page Should Be Settled    ${stable_polls}

_Wait Best Effort
    [Documentation]    Internal keyword — polls a condition keyword; on timeout logs the
    ...    structured SETTLE_TIMEOUT WARN and returns FAIL instead of failing the test.
    [Arguments]    ${caller}    ${timeout}    ${interval}    ${keyword}    @{args}
    ${status}    ${msg}=    Run Keyword And Ignore Error
    ...    Wait Until Keyword Succeeds    ${timeout}    ${interval}    ${keyword}    @{args}
    IF    "${status}" == "FAIL"
        Log    SETTLE_TIMEOUT caller=${caller} waited=${timeout}    WARN
        Log    Last probe result: ${msg}
    END
    RETURN    ${status}

_Page Should Be Settled
    [Documentation]    Internal keyword — one settle probe; fails until the page is quiet.
    ...    Counts nodes and text length only (no serialisation), so it stays cheap on big pages.
    [Arguments]    ${stable_polls}
    ${state}=    Execute JavaScript
    ...    return (function(need){
    ...        function visible(el) {
    ...            var r = el.getBoundingClientRect();
    ...            if (r.width === 0 || r.height === 0) { return false; }
    ...            var cs = getComputedStyle(el);
    ...            return cs.visibility !== 'hidden' && cs.display !== 'none';
    ...        }
    ...        function walk(root, acc, depth) {
    ...            if (depth > 40) { return; }
    ...            var kids = root.childNodes;
    ...            for (var i = 0; i < kids.length; i++) {
    ...                var c = kids[i];
    ...                if (c.nodeType === 3) { acc.t += c.data.length; }
    ...                else if (c.nodeType === 1) {
    ...                    acc.n++;
    ...                    var cl = c.classList;
    ...                    if (c.tagName === 'LIGHTNING-SPINNER' || (cl && (cl.contains('slds-spinner') || cl.contains('slds-spinner_container') || cl.contains('forceLoadingSpinner')))) {
    ...                        if (visible(c)) { acc.spin++; }
    ...                    }
    ...                    if (c.shadowRoot) { walk(c.shadowRoot, acc, depth + 1); }
    ...                    walk(c, acc, depth + 1);
    ...                }
    ...            }
    ...        }
    ...        var st = window.__e2eSettle || (window.__e2eSettle = {sig: null, stable: 0});
    ...        if (document.readyState !== 'complete') { st.sig = null; st.stable = 0; return 'loading'; }
    ...        var acc = {n: 0, t: 0, spin: 0};
    ...        walk(document, acc, 0);
    ...        if (acc.spin > 0) { st.sig = null; st.stable = 0; return 'spinner'; }
    ...        var sig = acc.n + ':' + acc.t;
    ...        if (sig === st.sig) { st.stable++; } else { st.sig = sig; st.stable = 0; }
    ...        return st.stable >= need ? 'settled' : 'changing';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${stable_polls}
    Should Be Equal    ${state}    settled    msg=Page not settled yet (${state}).

Get Dialog Signature
    [Documentation]    Returns 'none' when no dialog or flow is open, otherwise a short hash of
    ...    the dialog text (shadow roots included). Compare the value taken before an action with
    ...    a later one to see that the dialog advanced, changed or closed, without depending on
    ...    any product-specific selector.
    ${sig}=    Execute JavaScript
    ...    return (function(){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        function deepText(node, depth) {
    ...            if (depth > 25) return '';
    ...            var t = '';
    ...            var kids = node.childNodes;
    ...            for (var i = 0; i < kids.length; i++) {
    ...                var c = kids[i];
    ...                if (c.nodeType === 3) { t += c.textContent + ' '; }
    ...                else if (c.nodeType === 1 && c.tagName !== 'STYLE' && c.tagName !== 'SCRIPT') {
    ...                    if (c.shadowRoot) { t += deepText(c.shadowRoot, depth + 1); }
    ...                    t += deepText(c, depth + 1);
    ...                }
    ...            }
    ...            return t;
    ...        }
    ...        var dialogs = deepAll(document, 'flowruntime-flow, section.slds-modal, div.modal-container, lightning-modal', [], 0);
    ...        if (dialogs.length === 0) { return 'none'; }
    ...        var text = '';
    ...        for (var d = 0; d < dialogs.length; d++) { text += deepText(dialogs[d], 0) + '|'; }
    ...        var out = '';
    ...        var prevWasSpace = false;
    ...        for (var k = 0; k < text.length; k++) {
    ...            var code = text.charCodeAt(k);
    ...            var isSpace = (code === 32 || code === 9 || code === 10 || code === 13);
    ...            if (isSpace) {
    ...                if (!prevWasSpace && out.length > 0) { out += ' '; }
    ...                prevWasSpace = true;
    ...            } else {
    ...                out += text.charAt(k);
    ...                prevWasSpace = false;
    ...            }
    ...        }
    ...        var h = 5381;
    ...        for (var m = 0; m < out.length; m++) { h = ((h << 5) + h + out.charCodeAt(m)) | 0; }
    ...        return 'sig:' + dialogs.length + ':' + out.length + ':' + h;
    ...    })()
    RETURN    ${sig}

_Dialog Signature Should Differ From
    [Arguments]    ${before}
    ${now}=    Get Dialog Signature
    Should Not Be Equal    ${now}    ${before}    msg=Dialog has not changed yet.

_Dialog Should Be Open
    ${now}=    Get Dialog Signature
    Should Not Be Equal    ${now}    none    msg=No dialog or flow is open yet.

Wait For Dialog To Change
    [Documentation]    Best-effort: after clicking inside a dialog or flow, waits until its content
    ...    differs from the signature taken BEFORE the click (next screen, or closed), then settles.
    ...    With no dialog before the click it only settles.
    [Arguments]    ${before}    ${caller}=Wait For Dialog To Change    ${timeout}=15s
    IF    "${before}" != "none"
        _Wait Best Effort    ${caller}:dialog-changed    ${timeout}    500ms    _Dialog Signature Should Differ From    ${before}
    END
    Wait Until Page Is Settled    caller=${caller}

Wait For Action Dialog
    [Documentation]    Best-effort: after triggering a QuickAction/flow, waits until a dialog or flow
    ...    is open, then settles. The caller's next keyword waits strictly for its own controls.
    [Arguments]    ${caller}=Wait For Action Dialog    ${timeout}=20s
    _Wait Best Effort    ${caller}:dialog-open    ${timeout}    500ms    _Dialog Should Be Open
    Wait Until Page Is Settled    caller=${caller}

_Location Should Be Lightning
    [Documentation]    Internal keyword — true once the frontdoor redirect has landed on a
    ...    /lightning/ page. Reads the path in JS so a failure message never contains the
    ...    session-bearing URL.
    ${ok}=    Execute JavaScript    return window.location.pathname.indexOf('/lightning/') === 0 ? 'yes' : 'no';
    Should Be Equal    ${ok}    yes    msg=Browser is not on a /lightning/ page yet.

Wait For Quote Line For Product
    [Documentation]    Polls the REST API until the Quote has a line for the named product. This is
    ...    the positive signal that an add-product or configurator commit really persisted.
    [Arguments]    ${quote_id}    ${product_name}    ${timeout}=60s    ${interval}=3s
    SalesforceAPI.Validate Salesforce Id    ${quote_id}
    ${product_id}=    SalesforceAPI.Find Product By Name    ${product_name}
    SalesforceAPI.Validate Salesforce Id    ${product_id}
    ${line_id}=    Wait For Related Record Via API
    ...    SELECT Id FROM QuoteLineItem WHERE QuoteId = '${quote_id}' AND Product2Id = '${product_id}' LIMIT 1
    ...    ${timeout}    ${interval}
    RETURN    ${line_id}

# ── Navigation ───────────────────────────────────────────────────────

Get Authenticated Url
    [Documentation]    Gets an authenticated URL for a Lightning page path using
    ...    \`sf org open --url-only\`. Returns the full URL with session token.
    ...    URL-handling steps are wrapped in Set Log Level NONE to prevent the
    ...    session token from leaking into Robot log.html/CI artifacts.
    [Arguments]    ${page_path}
    Run Keyword If    "${ORG_ALIAS}" == ""    Fail    msg=ORG_ALIAS must be set
    ${prev_level}=    Set Log Level    NONE
    ${result}=    Run Process    sf    org    open    -o    ${ORG_ALIAS}    --url-only    -p    ${page_path}    shell=False
    Run Keyword If    ${result.rc} != 0    Set Log Level    ${prev_level}
    Run Keyword If    ${result.rc} != 0    Fail    msg=sf org open failed: ${result.stderr}
    ${raw}=    Strip String    ${result.stdout}
    ${raw}=    Evaluate    $raw.replace(chr(10), ' ').replace(chr(13), ' ').strip()
    ${url}=    Evaluate    $raw.split('with the following URL:')[-1].strip() if 'with the following URL:' in $raw else $raw
    ${url}=    Strip String    ${url}
    Set Log Level    ${prev_level}
    RETURN    ${url}

Navigate To App
    [Documentation]    Navigates to a Salesforce Lightning app by its display name.
    ...    Uses /lightning/app/<DeveloperName> with an authenticated URL.
    ...    The DeveloperName is derived by replacing spaces with underscores
    ...    and prepending the RLM namespace prefix.
    ...    Set Log Level NONE wraps both URL retrieval and navigation to prevent
    ...    the session token from appearing in Robot log.html/CI artifacts.
    [Arguments]    ${app_name}
    ${app_api_name}=    Evaluate    'RLM_' + $app_name.replace(' ', '_')
    ${prev_level}=    Set Log Level    NONE
    ${url}=    Get Authenticated Url    /lightning/app/c__${app_api_name}
    Go To    ${url}
    Set Log Level    ${prev_level}
    Wait Until Page Contains Element    css:body    timeout=${PAGE_LOAD_TIMEOUT}
    Wait Until Keyword Succeeds    ${PAGE_LOAD_TIMEOUT}    500ms    _Location Should Be Lightning
    Wait Until Page Is Settled    caller=Navigate To App
    Log    Navigated to app: ${app_name}

Navigate To Record
    [Documentation]    Navigates to a Salesforce record page by SObject type and Id.
    ...    Set Log Level NONE wraps both URL retrieval and navigation to prevent
    ...    the session token from appearing in Robot log.html/CI artifacts.
    [Arguments]    ${sobject}    ${record_id}
    ${prev_level}=    Set Log Level    NONE
    ${url}=    Get Authenticated Url    /lightning/r/${sobject}/${record_id}/view
    Go To    ${url}
    Set Log Level    ${prev_level}
    Wait Until Page Contains Element    css:body    timeout=${PAGE_LOAD_TIMEOUT}
    Wait Until Keyword Succeeds    ${PAGE_LOAD_TIMEOUT}    500ms    _Location Should Be Lightning
    Wait Until Page Is Settled    caller=Navigate To Record

Navigate To Account
    [Documentation]    Navigates to an Account record page.
    [Arguments]    ${account_id}
    Navigate To Record    Account    ${account_id}

Navigate To Opportunity
    [Documentation]    Navigates to an Opportunity record page.
    [Arguments]    ${opportunity_id}
    Navigate To Record    Opportunity    ${opportunity_id}

Navigate To Quote
    [Documentation]    Navigates to a Quote record page.
    [Arguments]    ${quote_id}
    Navigate To Record    Quote    ${quote_id}

Navigate To Order
    [Documentation]    Navigates to an Order record page.
    [Arguments]    ${order_id}
    Navigate To Record    Order    ${order_id}

Click Record Page Tab
    [Documentation]    Clicks a tab on a Lightning record page by its label.
    ...    Handles tabs inside shadow DOM (LWC tabset components).
    [Arguments]    ${tab_label}
    # Try XPath first (works for light DOM tabs)
    ${tab}=    Set Variable    xpath=//a[@data-label='${tab_label}' and @role='tab']
    ${found}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${tab}    timeout=10s
    IF    ${found}
        Scroll Element Into View    ${tab}
        Click Element    ${tab}
        Wait Until Keyword Succeeds    10s    500ms    _Record Tab Should Be Selected    ${tab_label}
        Wait Until Page Is Settled    caller=Click Record Page Tab
        RETURN
    END
    # Fallback: shadow DOM traversal
    ${js_result}=    Execute JavaScript
    ...    return (function(label){
    ...        function findAll(root, selector) {
    ...            var found = [];
    ...            var els = root.querySelectorAll(selector);
    ...            for (var i = 0; i < els.length; i++) found.push(els[i]);
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].shadowRoot) found = found.concat(findAll(all[i].shadowRoot, selector));
    ...            }
    ...            return found;
    ...        }
    ...        var tabs = findAll(document, 'a[role="tab"][data-label="' + label + '"]');
    ...        for (var i = 0; i < tabs.length; i++) {
    ...            if (tabs[i].offsetParent !== null) { tabs[i].click(); return 'clicked'; }
    ...        }
    ...        /* Fallback: match by text content */
    ...        var allTabs = findAll(document, 'a[role="tab"]');
    ...        for (var i = 0; i < allTabs.length; i++) {
    ...            if (allTabs[i].textContent.trim() === label && allTabs[i].offsetParent !== null) {
    ...                allTabs[i].click(); return 'clicked_by_text';
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${tab_label}
    Log    Click tab result: ${js_result}
    IF    "${js_result}" == "not_found"
        Capture Step Screenshot    tab_not_found_${tab_label}
        Fail    msg=Tab "${tab_label}" not found on record page.
    END
    Wait Until Keyword Succeeds    10s    500ms    _Record Tab Should Be Selected    ${tab_label}
    Wait Until Page Is Settled    caller=Click Record Page Tab

_Record Tab Should Be Selected
    [Documentation]    Internal keyword — passes once the tab with this label reports
    ...    aria-selected=true (shadow DOM traversed).
    [Arguments]    ${tab_label}
    ${result}=    Execute JavaScript
    ...    return (function(label){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        var tabs = deepAll(document, 'a[role="tab"]', [], 0);
    ...        for (var i = 0; i < tabs.length; i++) {
    ...            var same = tabs[i].getAttribute('data-label') === label || (tabs[i].textContent || '').trim() === label;
    ...            if (same && tabs[i].getAttribute('aria-selected') === 'true') { return 'selected'; }
    ...        }
    ...        return 'not_selected';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${tab_label}
    Should Be Equal    ${result}    selected    msg=Tab "${tab_label}" is not selected yet.

# ── QuickAction / Highlights Panel ──────────────────────────────────

Click Highlights Panel Action
    [Documentation]    Clicks an action button in the Lightning record page highlights
    ...    panel or actions menu. Tries the visible button first, then falls back
    ...    to the overflow "More Actions" menu, then to shadow DOM JS traversal.
    [Arguments]    ${action_label}
    # Try direct button in highlights panel
    ${btn}=    Set Variable    xpath=//runtime_platform_actions-actions-ribbon//button[normalize-space(.)='${action_label}'] | //runtime_platform_actions-action-renderer//a[@title='${action_label}'] | //li[contains(@class,'oneActionsRibbon')]//a[@title='${action_label}']
    ${found}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${btn}    timeout=10s
    IF    ${found}
        Scroll Element Into View    ${btn}
        Click Element    ${btn}
        Wait For Action Dialog    caller=Click Highlights Panel Action
        RETURN
    END
    # Try overflow menu
    ${more_btn}=    Set Variable    xpath=//runtime_platform_actions-actions-ribbon//button[contains(@class,'slds-button_icon-border') or @title='More Actions' or contains(normalize-space(.),'more actions')] | //lightning-button-menu[contains(@class,'action')]//button
    ${more_found}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${more_btn}    timeout=5s
    IF    ${more_found}
        Click Element    ${more_btn}
        ${menu_item}=    Set Variable    xpath=//lightning-menu-item[contains(@data-target-selection-name,'${action_label}') or .//span[normalize-space(.)='${action_label}']] | //a[@title='${action_label}']
        Wait Until Element Is Visible    ${menu_item}    timeout=10s
        Click Element    ${menu_item}
        Wait For Action Dialog    caller=Click Highlights Panel Action
        RETURN
    END
    # Fallback: shadow DOM JS traversal for LWC action buttons
    ${js_result}=    Execute JavaScript
    ...    return (function(label){
    ...        function findAll(root, tag) {
    ...            var found = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === tag) found.push(all[i]);
    ...                if (all[i].shadowRoot) found = found.concat(findAll(all[i].shadowRoot, tag));
    ...            }
    ...            return found;
    ...        }
    ...        /* Try to find and click the overflow menu button via shadow DOM first */
    ...        var ribbon = document.querySelector('runtime_platform_actions-actions-ribbon');
    ...        if (ribbon) {
    ...            var ribbonRoot = ribbon.shadowRoot || ribbon;
    ...            var btns = findAll(ribbonRoot, 'BUTTON');
    ...            /* First try direct action button */
    ...            for (var i = 0; i < btns.length; i++) {
    ...                if (btns[i].textContent.trim() === label) { btns[i].click(); return 'clicked_direct'; }
    ...            }
    ...            /* Try overflow/more actions menu button */
    ...            for (var i = 0; i < btns.length; i++) {
    ...                if (btns[i].title === 'More Actions' || btns[i].getAttribute('aria-label') === 'More Actions') {
    ...                    btns[i].click(); return 'opened_overflow';
    ...                }
    ...            }
    ...        }
    ...        /* Broad search: find any visible button matching label text or name across entire DOM */
    ...        var allBtns = findAll(document, 'BUTTON');
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            if (allBtns[i].offsetParent === null) continue;
    ...            var txt = allBtns[i].textContent.trim();
    ...            var nm = allBtns[i].getAttribute('name') || '';
    ...            if (txt === label || nm === label + 'Order' || nm === label) {
    ...                allBtns[i].click(); return 'clicked_broad';
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${action_label}
    Log    Highlights Panel JS result: ${js_result}
    IF    "${js_result}" == "clicked_direct" or "${js_result}" == "clicked_broad"
        Wait For Action Dialog    caller=Click Highlights Panel Action
        RETURN
    END
    IF    "${js_result}" == "opened_overflow"
        ${menu_item}=    Set Variable    xpath=//lightning-menu-item[contains(@data-target-selection-name,'${action_label}') or .//span[normalize-space(.)='${action_label}']] | //a[@title='${action_label}']
        ${menu_found}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${menu_item}    timeout=10s
        IF    ${menu_found}
            Click Element    ${menu_item}
            Wait For Action Dialog    caller=Click Highlights Panel Action
            RETURN
        END
    END
    Capture Step Screenshot    action_not_found_${action_label}
    Fail    msg=Action button "${action_label}" not found in highlights panel or overflow menu.

Wait For Modal
    [Documentation]    Waits for a Lightning modal dialog to appear.
    [Arguments]    ${timeout}=15s
    ${modal}=    Set Variable    xpath=//div[contains(@class,'modal-container') or contains(@class,'slds-modal')] | //section[contains(@class,'slds-modal')]
    Wait Until Element Is Visible    ${modal}    timeout=${timeout}
    Wait Until Page Is Settled    caller=Wait For Modal

Fill Modal Field
    [Documentation]    Fills a field in a modal dialog by field label.
    ...    Handles both standard input fields and Lightning combobox/lookup fields.
    [Arguments]    ${field_label}    ${value}
    # Try standard input
    ${input}=    Set Variable    xpath=//div[contains(@class,'modal')]//label[normalize-space(.)='${field_label}']/following::input[1] | //div[contains(@class,'modal')]//span[normalize-space(.)='${field_label}']/ancestor::*[contains(@class,'slds-form-element')][1]//input
    ${found}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${input}    timeout=8s
    IF    ${found}
        Click Element    ${input}
        Press Keys    ${input}    CTRL+a    DELETE
        Input Text    ${input}    ${value}
        _Wait Best Effort    Fill Modal Field:value-readback    5s    250ms    Textfield Value Should Be    ${input}    ${value}
        RETURN
    END
    # Try textarea
    ${textarea}=    Set Variable    xpath=//div[contains(@class,'modal')]//label[normalize-space(.)='${field_label}']/following::textarea[1]
    ${ta_found}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${textarea}    timeout=3s
    IF    ${ta_found}
        Click Element    ${textarea}
        Input Text    ${textarea}    ${value}
        RETURN
    END
    Log    WARNING: Could not find field "${field_label}" in modal.    WARN

Select Modal Picklist Value
    [Documentation]    Selects a value from a picklist/combobox field in a modal.
    ...    Tries native <select> first (Aura modals), then Lightning combobox (LWC).
    [Arguments]    ${field_label}    ${value}
    # Strategy 1: Native <select> (common in Aura QuickAction modals)
    ${native_select}=    Set Variable    xpath=(//label[contains(normalize-space(.),'${field_label}')]/following::select[1] | //span[normalize-space(.)='${field_label}']/ancestor::*[.//select][1]//select)[1]
    ${is_native}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${native_select}    timeout=5s
    IF    ${is_native}
        Select From List By Label    ${native_select}    ${value}
        Wait Until Keyword Succeeds    5s    250ms    List Selection Should Be    ${native_select}    ${value}
        RETURN
    END
    # Strategy 2: Lightning combobox (role=combobox)
    ${combobox}=    Set Variable    xpath=//div[contains(@class,'modal')]//label[normalize-space(.)='${field_label}']/following::*[@role='combobox' or contains(@class,'slds-combobox')][1] | //div[contains(@class,'modal')]//span[normalize-space(.)='${field_label}']/ancestor::*[contains(@class,'slds-form-element')][1]//*[@role='combobox']
    ${is_combobox}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${combobox}    timeout=5s
    IF    ${is_combobox}
        Click Element    ${combobox}
        ${option}=    Set Variable    xpath=(//*[@role='option' and contains(normalize-space(.), '${value}')])[1]
        Wait Until Element Is Visible    ${option}    timeout=10s
        Click Element    ${option}
        Wait Until Page Is Settled    caller=Select Modal Picklist Value
        RETURN
    END
    # Strategy 3: Aura <a> picklist trigger
    ${aura_picklist}=    Set Variable    xpath=(//span[normalize-space(.)='${field_label}']/ancestor::div[contains(@class,'form-element')]//a[contains(@class,'select') or contains(@class,'picklist')])[1]
    ${is_aura}=    Run Keyword And Return Status    Wait Until Element Is Visible    ${aura_picklist}    timeout=5s
    IF    ${is_aura}
        Click Element    ${aura_picklist}
        ${aura_option}=    Set Variable    xpath=(//a[@role='menuitemcheckbox' and normalize-space(.)='${value}'] | //li[contains(@class,'uiMenuItem')]//a[normalize-space(.)='${value}'])[1]
        Wait Until Element Is Visible    ${aura_option}    timeout=10s
        Click Element    ${aura_option}
        Wait Until Page Is Settled    caller=Select Modal Picklist Value
        RETURN
    END
    Capture Step Screenshot    picklist_not_found_${field_label}
    Fail    msg=Could not find picklist/combobox for "${field_label}"

Select Lookup Value
    [Documentation]    Types into a lookup/autocomplete search field and selects a result.
    ...    Finds the input by its placeholder text (e.g. "Search Price Books"),
    ...    types the search value, waits for results, and clicks the match.
    [Arguments]    ${placeholder}    ${value}
    ${input}=    Set Variable    xpath=//input[@placeholder='${placeholder}' or @title='${placeholder}' or contains(@placeholder,'${placeholder}')]
    Wait Until Element Is Visible    ${input}    timeout=10s
    Click Element    ${input}
    Input Text    ${input}    ${value}
    Wait Until Page Is Settled    caller=Select Lookup Value
    # Click the matching result — lookup results appear as role=option or in a listbox
    ${result}=    Set Variable    xpath=(//*[@role='option' and contains(normalize-space(.), '${value}')] | //a[contains(@class,'lookup') and contains(normalize-space(.), '${value}')] | //div[contains(@class,'lookup')]//span[contains(normalize-space(.), '${value}')] | //li[contains(@class,'lookup')]//a[contains(normalize-space(.), '${value}')])[1]
    Wait Until Element Is Visible    ${result}    timeout=10s
    Click Element    ${result}
    Wait Until Page Is Settled    caller=Select Lookup Value

Save Modal
    [Documentation]    Clicks the Save button in a modal dialog via JavaScript.
    ...    Handles Aura QuickAction modals (cuf-publisherShareButton),
    ...    Flow navigation bars, and LWC modals. Retries up to 30s for the
    ...    button to appear (flow screens can be slow to render).
    [Arguments]    ${button_label}=Save
    ${before}=    Wait Until Keyword Succeeds    30s    3s    _Click Save Button Tracking Dialog    ${button_label}
    Wait For Dialog To Change    ${before}    caller=Save Modal

_Click Save Button Tracking Dialog
    [Documentation]    Internal keyword — records the dialog signature immediately before the
    ...    click that succeeds, so the caller can wait for that dialog to change or close.
    [Arguments]    ${button_label}
    ${before}=    Get Dialog Signature
    _Click Save Button Via JS    ${button_label}
    RETURN    ${before}

_Click Save Button Via JS
    [Documentation]    Internal keyword — attempts to find and click a save button via JS.
    ...    Traverses shadow DOM boundaries to find buttons inside LWC components.
    ...    Fails if not found (so Wait Until Keyword Succeeds can retry).
    [Arguments]    ${button_label}
    ${result}=    Execute JavaScript
    ...    return (function(label){
    ...        /* Recursively find all <button> elements, traversing shadow roots */
    ...        function findAllButtons(root) {
    ...            var btns = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'BUTTON') btns.push(all[i]);
    ...                if (all[i].shadowRoot) {
    ...                    btns = btns.concat(findAllButtons(all[i].shadowRoot));
    ...                }
    ...            }
    ...            return btns;
    ...        }
    ...        function usable(b) { return !b.disabled && b.getAttribute('aria-disabled') !== 'true'; }
    ...        /* 1. Aura QuickAction footer — no shadow DOM */
    ...        var btn = document.querySelector('button.cuf-publisherShareButton');
    ...        if (btn) {
    ...            var t = btn.textContent.trim();
    ...            if ((t === label || t.indexOf(label) >= 0) && usable(btn)) { btn.click(); return 'clicked_aura_footer:' + t; }
    ...        }
    ...        /* 2. Flow navigation bar — traverse shadow roots */
    ...        var flowEl = document.querySelector('flowruntime-flow');
    ...        if (flowEl) {
    ...            var root = flowEl.shadowRoot || flowEl;
    ...            var navBar = root.querySelector('flowruntime-navigation-bar');
    ...            if (navBar) {
    ...                var navRoot = navBar.shadowRoot || navBar;
    ...                var navBtns = findAllButtons(navRoot);
    ...                for (var i = 0; i < navBtns.length; i++) {
    ...                    var t = navBtns[i].textContent.trim();
    ...                    if ((t === label || t.indexOf(label) >= 0) && usable(navBtns[i])) { navBtns[i].click(); return 'clicked_flow_nav_shadow:' + t; }
    ...                }
    ...            }
    ...            /* Also try all buttons in the flow element via shadow traversal */
    ...            var flowBtns = findAllButtons(root);
    ...            for (var i = 0; i < flowBtns.length; i++) {
    ...                var t = flowBtns[i].textContent.trim();
    ...                if ((t === label || t.indexOf(label) >= 0) && usable(flowBtns[i])) { flowBtns[i].click(); return 'clicked_flow_shadow:' + t; }
    ...            }
    ...        }
    ...        /* 3. slds-modal footer */
    ...        var footer = document.querySelector('footer.slds-modal__footer');
    ...        if (footer) {
    ...            var fBtns = findAllButtons(footer);
    ...            for (var i = 0; i < fBtns.length; i++) {
    ...                var t = fBtns[i].textContent.trim();
    ...                if ((t === label || t.indexOf(label) >= 0) && usable(fBtns[i])) { fBtns[i].click(); return 'clicked_modal_footer:' + t; }
    ...            }
    ...        }
    ...        /* 4. Broad search — all buttons including shadow DOM */
    ...        var allBtns = findAllButtons(document);
    ...        for (var j = 0; j < allBtns.length; j++) {
    ...            var t = allBtns[j].textContent.trim();
    ...            if ((t === label || t.indexOf(label) >= 0) && allBtns[j].offsetParent !== null && usable(allBtns[j])) {
    ...                allBtns[j].click(); return 'clicked_visible_shadow:' + t;
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${button_label}
    Log    Save Modal JS result: ${result}
    IF    "${result}" == "not_found"
        Capture Step Screenshot    save_button_not_found
        Fail    msg=${button_label} button not found (or still disabled) in modal via JavaScript (will retry).
    END

Advance Through Flow Screens
    [Documentation]    Iteratively advances through all screens in a Flow-based modal.
    ...    Clicks Next/Finish/Done/Create Order buttons until the flow completes or
    ...    no more flow buttons are found. Handles flows with 1 or more screens.
    ...    Fails if the flow/modal is still open after max_screens iterations to
    ...    surface stuck or unexpectedly deep flows rather than silently continuing.
    [Arguments]    ${max_screens}=${10}
    FOR    ${i}    IN RANGE    ${max_screens}
        Capture Step Screenshot    flow_screen_${i}
        ${pair}=    _Click Flow Action Button
        ${btn_result}=    Set Variable    ${pair}[0]
        ${before}=    Set Variable    ${pair}[1]
        IF    "${btn_result}" == "no_button_found" and ("${before}" != "none" or ${i} == 0)
            ${status}    ${retried}=    Run Keyword And Ignore Error
            ...    Wait Until Keyword Succeeds    15s    1s    _Click Flow Action Button Or Fail
            IF    "${status}" == "PASS"
                ${btn_result}=    Set Variable    ${retried}[0]
                ${before}=    Set Variable    ${retried}[1]
            END
        END
        Log    Flow screen ${i}: ${btn_result}
        IF    "${btn_result}" == "no_button_found"
            Log    No more flow buttons found after ${i} screens.
            RETURN
        END
        Wait For Dialog To Change    ${before}    caller=Advance Through Flow Screens    timeout=30s
        # Check if flow/modal has closed (we're back on the record page)
        ${flow_still_open}=    Run Keyword And Return Status    Page Should Contain Element
        ...    xpath=//flowruntime-flow | //div[contains(@class,'modal-container')] | //section[contains(@class,'slds-modal')]
        IF    not ${flow_still_open}
            Log    Flow/modal closed after clicking ${btn_result}.
            RETURN
        END
    END
    # If we exhaust max_screens without the flow closing, fail explicitly
    ${flow_still_open}=    Run Keyword And Return Status    Page Should Contain Element
    ...    xpath=//flowruntime-flow | //div[contains(@class,'modal-container')] | //section[contains(@class,'slds-modal')]
    IF    ${flow_still_open}
        Fail    msg=Flow did not complete after ${max_screens} screens. The flow may have more screens than expected or may be stuck. Increase max_screens or investigate the flow state.
    END

_Click Flow Action Button
    [Documentation]    Internal keyword — clicks the first enabled flow/modal action button
    ...    (Next, Finish, Done, ...). Returns a two-item list: the JS result
    ...    ('clicked:<label>' or 'no_button_found') and the dialog signature taken just before
    ...    the attempt, so the caller can wait for that dialog to change.
    ${before}=    Get Dialog Signature
    ${btn_result}=    Execute JavaScript
    ...    return (function(){
    ...        var labels = ['Next', 'Finish', 'Done', 'Create Order', 'Create Orders', 'Submit', 'Save', 'Confirm'];
    ...        function findAllButtons(root) {
    ...            var btns = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'BUTTON') btns.push(all[i]);
    ...                if (all[i].shadowRoot) btns = btns.concat(findAllButtons(all[i].shadowRoot));
    ...            }
    ...            return btns;
    ...        }
    ...        function usable(b) { return !b.disabled && b.getAttribute('aria-disabled') !== 'true'; }
    ...        /* 1. Flow navigation bar buttons (with shadow DOM traversal) */
    ...        var flowEl = document.querySelector('flowruntime-flow');
    ...        if (flowEl) {
    ...            var fRoot = flowEl.shadowRoot || flowEl;
    ...            var navBar = fRoot.querySelector('flowruntime-navigation-bar');
    ...            if (navBar) {
    ...                var navRoot = navBar.shadowRoot || navBar;
    ...                var navBtns = findAllButtons(navRoot);
    ...                for (var i = 0; i < navBtns.length; i++) {
    ...                    var txt = navBtns[i].textContent.trim();
    ...                    for (var j = 0; j < labels.length; j++) {
    ...                        if (txt === labels[j] && usable(navBtns[i])) { navBtns[i].click(); return 'clicked:' + txt; }
    ...                    }
    ...                }
    ...            }
    ...        }
    ...        /* 2. Modal footer buttons (with shadow DOM traversal) */
    ...        var footer = document.querySelector('footer.slds-modal__footer');
    ...        if (footer) {
    ...            var fBtns = findAllButtons(footer);
    ...            for (var i = 0; i < fBtns.length; i++) {
    ...                var txt = fBtns[i].textContent.trim();
    ...                for (var j = 0; j < labels.length; j++) {
    ...                    if (txt === labels[j] && usable(fBtns[i])) { fBtns[i].click(); return 'clicked:' + txt; }
    ...                }
    ...            }
    ...        }
    ...        /* 3. Broad search — all buttons including shadow DOM */
    ...        var allBtns = findAllButtons(document);
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            if (allBtns[i].offsetParent === null) continue;
    ...            var txt = allBtns[i].textContent.trim();
    ...            for (var j = 0; j < labels.length; j++) {
    ...                if (txt === labels[j] && usable(allBtns[i])) { allBtns[i].click(); return 'clicked:' + txt; }
    ...            }
    ...        }
    ...        return 'no_button_found';
    ...    })()
    ${pair}=    Create List    ${btn_result}    ${before}
    RETURN    ${pair}

_Click Flow Action Button Or Fail
    [Documentation]    Internal keyword — retry wrapper: fails until an enabled button exists.
    ${pair}=    _Click Flow Action Button
    Should Not Be Equal    ${pair}[0]    no_button_found    msg=No enabled flow button yet (will retry).
    RETURN    ${pair}

# ── Create Order ───────────────────────────────────────────────────

Select Order Creation Method
    [Documentation]    Selects "Create Single Order" in the Create Order flow's
    ...    order-creation-method-picker and clicks Next/Finish.
    ...    The picker uses radio inputs inside runtime_rca-order-creation-method-picker
    ...    which is nested in shadow DOM.
    Wait Until Keyword Succeeds    15s    3s    _Select Single Order Radio Via JS
    # Click Finish to advance past the picker screen
    Save Modal    Finish

_Select Single Order Radio Via JS
    [Documentation]    Internal keyword — finds and clicks the Create Single Order radio via JS.
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        function deepQueryAll(root, selector) {
    ...            var found = [];
    ...            var els = root.querySelectorAll(selector);
    ...            for (var i = 0; i < els.length; i++) found.push(els[i]);
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].shadowRoot) found = found.concat(deepQueryAll(all[i].shadowRoot, selector));
    ...                if (all[i].tagName === 'SLOT') {
    ...                    try {
    ...                        var assigned = all[i].assignedElements({flatten: true});
    ...                        for (var j = 0; j < assigned.length; j++) {
    ...                            found = found.concat(deepQueryAll(assigned[j], selector));
    ...                        }
    ...                    } catch(e) {}
    ...                }
    ...            }
    ...            return found;
    ...        }
    ...        /* Find radio with value="CreateSingleOrder" */
    ...        var radios = deepQueryAll(document, 'input[value="CreateSingleOrder"]');
    ...        for (var i = 0; i < radios.length; i++) {
    ...            radios[i].click();
    ...            return radios[i].checked ? 'selected' : 'click_did_not_take';
    ...        }
    ...        /* Fallback: find the visual picker div with data-id="single-order" */
    ...        var pickers = deepQueryAll(document, 'div[data-id="single-order"]');
    ...        for (var i = 0; i < pickers.length; i++) {
    ...            var radio = pickers[i].querySelector('input[type="radio"]');
    ...            if (radio) { radio.click(); return 'selected_by_picker'; }
    ...            var label = pickers[i].querySelector('label');
    ...            if (label) { label.click(); return 'selected_by_label'; }
    ...        }
    ...        return 'not_found';
    ...    })()
    Log    Select Order Creation Method JS result: ${result}
    IF    "${result}" == "not_found" or "${result}" == "click_did_not_take"
        Capture Step Screenshot    order_method_not_found
        Fail    msg=Create Single Order radio not found or not checked (${result}) (will retry).
    END

# ── Browse Catalogs ────────────────────────────────────────────────

Click Browse Catalogs
    [Documentation]    Clicks the Browse Catalogs button on a Quote record page.
    ...    Traverses shadow DOM to find the button (name="BrowseCatalog").
    ...    If a "Choose Price Book" modal appears, saves it with Standard Price Book.
    Wait Until Keyword Succeeds    30s    3s    _Click Browse Catalogs Via JS
    _Wait Best Effort    Click Browse Catalogs:surface-rendered    30s    1s    _Browse Catalogs Surface Should Be Rendered
    # Handle Choose Price Book modal if it appears (retry to allow modal to render)
    Wait Until Keyword Succeeds    15s    2s    _Dismiss Price Book Modal If Present
    _Wait Best Effort    Click Browse Catalogs:catalogs-shown    30s    1s    _Browse Catalogs Surface Should Show Catalogs
    Wait Until Page Is Settled    caller=Click Browse Catalogs

_Browse Catalogs Surface State
    [Documentation]    Internal keyword — 'price_book_modal' while the Choose Price Book modal is up,
    ...    'catalogs' once the catalog picker, a catalog heading or the product search input is
    ...    rendered, otherwise 'unknown'. Same signals as _Detect Catalog Picker State, name-agnostic.
    ${state}=    Execute JavaScript
    ...    return (function(){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        var h1s = deepAll(document, 'h1', [], 0);
    ...        for (var i = 0; i < h1s.length; i++) {
    ...            if (h1s[i].textContent.trim().indexOf('Price Book') >= 0) { return 'price_book_modal'; }
    ...        }
    ...        var heads = deepAll(document, 'h1,h2', [], 0);
    ...        for (var k = 0; k < heads.length; k++) {
    ...            if (heads[k].textContent.trim().indexOf('Catalog: ') === 0) { return 'catalogs'; }
    ...        }
    ...        if (deepAll(document, 'tr[data-row-key-value]', [], 0).length > 0) { return 'catalogs'; }
    ...        if (deepAll(document, 'input[name="enter-search"]', [], 0).length > 0) { return 'catalogs'; }
    ...        return 'unknown';
    ...    })()
    RETURN    ${state}

_Browse Catalogs Surface Should Be Rendered
    ${state}=    _Browse Catalogs Surface State
    Should Not Be Equal    ${state}    unknown    msg=Browse Catalogs has not rendered yet.

_Browse Catalogs Surface Should Show Catalogs
    ${state}=    _Browse Catalogs Surface State
    Should Be Equal    ${state}    catalogs    msg=Browse Catalogs is not showing catalogs yet (${state}).

_Price Book Modal Should Be Gone
    ${state}=    _Browse Catalogs Surface State
    Should Not Be Equal    ${state}    price_book_modal    msg=Choose Price Book modal is still open.

_Dismiss Price Book Modal If Present
    [Documentation]    If a "Choose Price Book" modal appears, clicks Save.
    ...    The modal DOM is: some-component (shadow host) → lightning-modal →
    ...    lightning-modal-footer (shadow host) → slot → lightning-button (shadow host) → button.
    ...    Slotted lightning-button elements are light DOM children of lightning-modal-footer,
    ...    so we must traverse from the light DOM side, not from inside the shadow root.
    ...    Fails if modal is found but Save cannot be clicked (allows retry wrapper).
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        /* Recursively traverse shadow DOM to find elements matching a selector */
    ...        function deepQueryAll(root, selector) {
    ...            var found = [];
    ...            var els = root.querySelectorAll(selector);
    ...            for (var i = 0; i < els.length; i++) found.push(els[i]);
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].shadowRoot) {
    ...                    found = found.concat(deepQueryAll(all[i].shadowRoot, selector));
    ...                }
    ...                /* Also check slotted content via assignedElements */
    ...                if (all[i].tagName === 'SLOT') {
    ...                    try {
    ...                        var assigned = all[i].assignedElements({flatten: true});
    ...                        for (var j = 0; j < assigned.length; j++) {
    ...                            found = found.concat(deepQueryAll(assigned[j], selector));
    ...                            if (assigned[j].matches && assigned[j].matches(selector)) found.push(assigned[j]);
    ...                        }
    ...                    } catch(e) {}
    ...                }
    ...            }
    ...            return found;
    ...        }
    ...        /* Step 1: Check if any Price Book modal is present */
    ...        var headings = deepQueryAll(document, 'h1');
    ...        var hasPriceBookModal = false;
    ...        for (var i = 0; i < headings.length; i++) {
    ...            if (headings[i].textContent.trim().indexOf('Price Book') >= 0) {
    ...                hasPriceBookModal = true; break;
    ...            }
    ...        }
    ...        if (!hasPriceBookModal) return 'no_modal';
    ...        /* Step 2: Find the Save button — try multiple strategies */
    ...        /* 2a: Find lightning-button[data-id="saveButton"] and click its inner button */
    ...        var wrappers = deepQueryAll(document, 'lightning-button[data-id="saveButton"]');
    ...        for (var i = 0; i < wrappers.length; i++) {
    ...            var btn = (wrappers[i].shadowRoot)
    ...                ? wrappers[i].shadowRoot.querySelector('button')
    ...                : wrappers[i].querySelector('button');
    ...            if (btn) { btn.click(); return 'clicked_save_wrapper'; }
    ...        }
    ...        /* 2b: Find button[name="save-button"] anywhere in the DOM */
    ...        var saveBtns = deepQueryAll(document, 'button[name="save-button"]');
    ...        for (var i = 0; i < saveBtns.length; i++) {
    ...            if (saveBtns[i].offsetParent !== null) {
    ...                saveBtns[i].click();
    ...                return 'clicked_save_by_name';
    ...            }
    ...        }
    ...        /* 2c: Find any visible button with text "Save" */
    ...        var allBtns = deepQueryAll(document, 'button');
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            if (allBtns[i].textContent.trim() === 'Save' && allBtns[i].offsetParent !== null) {
    ...                allBtns[i].click();
    ...                return 'clicked_save_by_text';
    ...            }
    ...        }
    ...        return 'modal_found_but_save_not_clicked';
    ...    })()
    Log    Price Book modal result: ${result}
    IF    "${result}" == "no_modal"
        Log    No Price Book modal detected — continuing.
        RETURN
    END
    IF    "${result}" == "modal_found_but_save_not_clicked"
        Fail    msg=Price Book modal found but Save button could not be clicked (will retry).
    END
    Wait Until Keyword Succeeds    15s    500ms    _Price Book Modal Should Be Gone

_Click Browse Catalogs Via JS
    [Documentation]    Internal keyword — finds and clicks Browse Catalogs via JS with shadow DOM traversal.
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        function findAllButtons(root) {
    ...            var btns = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'BUTTON') btns.push(all[i]);
    ...                if (all[i].shadowRoot) btns = btns.concat(findAllButtons(all[i].shadowRoot));
    ...            }
    ...            return btns;
    ...        }
    ...        var allBtns = findAllButtons(document);
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            if (allBtns[i].getAttribute('name') === 'BrowseCatalog' ||
    ...                allBtns[i].textContent.trim() === 'Browse Catalogs') {
    ...                allBtns[i].click();
    ...                return 'clicked';
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })()
    Log    Browse Catalogs JS result: ${result}
    IF    "${result}" == "not_found"
        Capture Step Screenshot    browse_catalogs_not_found
        Fail    msg=Browse Catalogs button not found (will retry).
    END

Select Catalog By Name
    [Documentation]    Selects a catalog by name in the All Catalogs datatable and clicks Next.
    ...    The datatable uses radio buttons for single selection. Each row has
    ...    data-cell-value on the Name <th> element matching the catalog name.
    ...    Also handles a late-arriving Choose Price Book modal (race condition).
    ...
    ...    When a Default Catalog is configured in Product Discovery Settings (see
    ...    configure_product_discovery_settings.robot), Browse Catalogs skips the All
    ...    Catalogs picker entirely and opens directly into Browse Products for that
    ...    catalog — there is no datatable to select from and no Next button. Detect
    ...    that case up front and skip the picker interaction instead of failing.
    ...
    ...    The direct-browse heading and the legacy picker datatable are checked together,
    ...    every retry, for the full window the legacy path itself gets (30s) — checking one
    ...    for a short window and then unconditionally falling back to the other is a race: a
    ...    slow-rendering direct-browse heading would fall through to the legacy picker wait,
    ...    which can never succeed because no datatable exists in that build.
    [Arguments]    ${catalog_name}
    ${status}    ${detected}=    Run Keyword And Ignore Error
    ...    Wait Until Keyword Succeeds    30s    1s    _Catalog Picker State Should Be Known    ${catalog_name}
    ${state}=    Set Variable If    "${status}" == "PASS"    ${detected}    unknown
    IF    "${state}" == "already_browsing"
        Log    Catalog picker skipped — Browse Catalogs opened directly into "${catalog_name}" (Default Catalog configured).
        RETURN
    END
    Wait Until Keyword Succeeds    30s    3s    _Dismiss Or Select Catalog    ${catalog_name}
    # Click Next in the flow navigation bar (Save Modal skips a disabled button until the selection
    # registers, then waits for the dialog to advance)
    Save Modal    Next

_Catalog Picker State Should Be Known
    [Documentation]    Internal keyword — fails while neither the direct-browse heading nor the
    ...    picker datatable has rendered; returns the state once one has.
    [Arguments]    ${catalog_name}
    ${state}=    _Detect Catalog Picker State    ${catalog_name}
    Should Not Be Equal    ${state}    unknown    msg=Catalog picker state still unknown.
    RETURN    ${state}

_Detect Catalog Picker State
    [Documentation]    Internal keyword — checks, in one pass, whether Browse Catalogs opened
    ...    directly into product browsing for ${catalog_name} (Default Catalog configured; no
    ...    picker datatable will ever appear) or whether the legacy All Catalogs picker
    ...    datatable is present (rows keyed by `data-row-key-value`, same traversal
    ...    `_Select Catalog Radio Via JS` uses). Returns 'already_browsing', 'picker_present',
    ...    or 'unknown' if neither has rendered yet — the caller retries on 'unknown'.
    [Arguments]    ${catalog_name}
    ${result}=    Execute JavaScript
    ...    return (function(name){
    ...        function findHeadings(root, acc) {
    ...            root.querySelectorAll('h1,h2').forEach(function(el){acc.push(el);});
    ...            root.querySelectorAll('*').forEach(function(el){if(el.shadowRoot)findHeadings(el.shadowRoot,acc);});
    ...        }
    ...        var heads = []; findHeadings(document, heads);
    ...        for (var i=0;i<heads.length;i++) {
    ...            if (heads[i].textContent.trim() === ('Catalog: ' + name)) return 'already_browsing';
    ...        }
    ...        function findRows(root, acc) {
    ...            root.querySelectorAll('tr[data-row-key-value]').forEach(function(el){acc.push(el);});
    ...            root.querySelectorAll('*').forEach(function(el){if(el.shadowRoot)findRows(el.shadowRoot,acc);});
    ...        }
    ...        var rows = []; findRows(document, rows);
    ...        if (rows.length > 0) { return 'picker_present'; }
    ...        return 'unknown';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${catalog_name}
    RETURN    ${result}

_Dismiss Or Select Catalog
    [Documentation]    Internal keyword — dismisses any Price Book modal, then selects the catalog.
    ...    If the Price Book modal is still showing, dismiss it and fail (will retry).
    [Arguments]    ${catalog_name}
    # Check for and dismiss Price Book modal if it appeared late
    _Dismiss Price Book Modal If Present
    # Now try to select the catalog
    _Select Catalog Radio Via JS    ${catalog_name}

_Select Catalog Radio Via JS
    [Documentation]    Internal keyword — finds the catalog row and clicks its radio button.
    ...    Traverses shadow DOM to find datatable rows inside LWC components.
    [Arguments]    ${catalog_name}
    ${result}=    Execute JavaScript
    ...    return (function(name){
    ...        function findRows(root) {
    ...            var rows = [];
    ...            var trs = root.querySelectorAll('tr[data-row-key-value]');
    ...            for (var i = 0; i < trs.length; i++) rows.push(trs[i]);
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].shadowRoot) {
    ...                    var shadowRows = findRows(all[i].shadowRoot);
    ...                    for (var j = 0; j < shadowRows.length; j++) rows.push(shadowRows[j]);
    ...                }
    ...            }
    ...            return rows;
    ...        }
    ...        function findInputs(root) {
    ...            var inputs = [];
    ...            var all = root.querySelectorAll('input[type="radio"]');
    ...            for (var i = 0; i < all.length; i++) inputs.push(all[i]);
    ...            var els = root.querySelectorAll('*');
    ...            for (var i = 0; i < els.length; i++) {
    ...                if (els[i].shadowRoot) {
    ...                    var shadowInputs = findInputs(els[i].shadowRoot);
    ...                    for (var j = 0; j < shadowInputs.length; j++) inputs.push(shadowInputs[j]);
    ...                }
    ...            }
    ...            return inputs;
    ...        }
    ...        var rows = findRows(document);
    ...        for (var i = 0; i < rows.length; i++) {
    ...            var nameCell = rows[i].querySelector('th[data-cell-value="' + name + '"]');
    ...            if (nameCell) {
    ...                var radios = findInputs(rows[i]);
    ...                if (radios.length > 0) { radios[0].click(); return 'selected:' + name; }
    ...                var radio = rows[i].querySelector('input[type="radio"]');
    ...                if (radio) { radio.click(); return 'selected_direct:' + name; }
    ...            }
    ...        }
    ...        /* Fallback: search by text content */
    ...        for (var i = 0; i < rows.length; i++) {
    ...            var th = rows[i].querySelector('th[data-label="Name"]');
    ...            if (th && th.textContent.trim().indexOf(name) >= 0) {
    ...                var radios = findInputs(rows[i]);
    ...                if (radios.length > 0) { radios[0].click(); return 'selected_by_text:' + name; }
    ...                var radio = rows[i].querySelector('input[type="radio"]');
    ...                if (radio) { radio.click(); return 'selected_by_text_direct:' + name; }
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${catalog_name}
    Log    Select Catalog JS result: ${result}
    IF    "${result}" == "not_found"
        Capture Step Screenshot    catalog_not_found
        Fail    msg=Catalog "${catalog_name}" not found in datatable (will retry).
    END

Search Product In Catalog
    [Documentation]    Waits for the product catalog to load, then searches for a product
    ...    by name using the search input (name="enter-search") and presses Enter.
    [Arguments]    ${product_name}
    # Wait for the product catalog search input to appear (indicates catalog has loaded)
    Wait Until Keyword Succeeds    30s    3s    _Find Product Search Input
    Wait Until Page Is Settled    caller=Search Product In Catalog
    ${rows_before}=    Get Product Rows Signature
    # Set search value via native setter (triggers LWC reactivity)
    ${input_set}=    Execute JavaScript
    ...    return (function(name){
    ...        function findInputs(root) {
    ...            var inputs = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'INPUT') inputs.push(all[i]);
    ...                if (all[i].shadowRoot) inputs = inputs.concat(findInputs(all[i].shadowRoot));
    ...            }
    ...            return inputs;
    ...        }
    ...        var allInputs = findInputs(document);
    ...        for (var i = 0; i < allInputs.length; i++) {
    ...            if (allInputs[i].getAttribute('name') === 'enter-search' ||
    ...                (allInputs[i].getAttribute('placeholder') && allInputs[i].getAttribute('placeholder').indexOf('Search for products') >= 0)) {
    ...                /* Use native setter to trigger LWC change detection */
    ...                var nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    ...                allInputs[i].focus();
    ...                nativeSetter.call(allInputs[i], name);
    ...                allInputs[i].dispatchEvent(new Event('input', {bubbles: true, composed: true}));
    ...                allInputs[i].dispatchEvent(new Event('change', {bubbles: true, composed: true}));
    ...                return 'set:' + allInputs[i].getAttribute('name');
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${product_name}
    Log    Search input set result: ${input_set}
    IF    "${input_set}" == "not_found"
        Capture Step Screenshot    product_search_not_found
        Fail    msg=Product search input not found.
    END
    # Press Enter via Selenium (more reliable than JS KeyboardEvent for LWC)
    _Press Enter On Search Input
    _Wait Best Effort    Search Product In Catalog:results-changed    10s    500ms    _Product Rows Signature Should Differ From    ${rows_before}
    Wait Until Page Is Settled    caller=Search Product In Catalog

Get Product Rows Signature
    [Documentation]    Returns the product row count plus a short hash of their leading text, so
    ...    a search can be seen to have re-rendered the result list.
    ${sig}=    Execute JavaScript
    ...    return (function(){
    ...        var rows = document.querySelectorAll('runtime_industries_cpq-product-row');
    ...        var h = 5381;
    ...        for (var i = 0; i < rows.length; i++) {
    ...            var root = rows[i].shadowRoot || rows[i];
    ...            var t = (root.textContent || '').slice(0, 80);
    ...            for (var k = 0; k < t.length; k++) { h = ((h << 5) + h + t.charCodeAt(k)) | 0; }
    ...        }
    ...        return 'rows:' + rows.length + ':' + h;
    ...    })()
    RETURN    ${sig}

_Product Rows Signature Should Differ From
    [Arguments]    ${before}
    ${now}=    Get Product Rows Signature
    Should Not Be Equal    ${now}    ${before}    msg=Product list has not changed yet.

_Press Enter On Search Input
    [Documentation]    Internal keyword — sends Enter key to the product search input via Selenium.
    ...    Falls back to JS keyboard event dispatch if Selenium can't find the input.
    # Try Selenium Press Keys on the active/focused element
    ${active}=    Execute JavaScript    return document.activeElement ? document.activeElement.tagName : 'NONE'
    IF    "${active}" == "INPUT"
        Press Keys    ${NONE}    RETURN
        RETURN
    END
    # Fallback: find the input and use Selenium
    ${input_found}=    Run Keyword And Return Status    Wait Until Element Is Visible
    ...    xpath=//input[@name='enter-search' or contains(@placeholder,'Search for products')]    timeout=3s
    IF    ${input_found}
        Press Keys    xpath=//input[@name='enter-search' or contains(@placeholder,'Search for products')]    RETURN
        RETURN
    END
    # Last resort: JS event dispatch with composed: true for shadow DOM
    Execute JavaScript
    ...    (function(){
    ...        function findInputs(root) {
    ...            var inputs = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'INPUT') inputs.push(all[i]);
    ...                if (all[i].shadowRoot) inputs = inputs.concat(findInputs(all[i].shadowRoot));
    ...            }
    ...            return inputs;
    ...        }
    ...        var allInputs = findInputs(document);
    ...        for (var i = 0; i < allInputs.length; i++) {
    ...            if (allInputs[i].getAttribute('name') === 'enter-search' ||
    ...                (allInputs[i].getAttribute('placeholder') && allInputs[i].getAttribute('placeholder').indexOf('Search for products') >= 0)) {
    ...                allInputs[i].focus();
    ...                var opts = {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, composed: true, cancelable: true};
    ...                allInputs[i].dispatchEvent(new KeyboardEvent('keydown', opts));
    ...                allInputs[i].dispatchEvent(new KeyboardEvent('keypress', opts));
    ...                allInputs[i].dispatchEvent(new KeyboardEvent('keyup', opts));
    ...                /* Also try submitting closest form if present */
    ...                var form = allInputs[i].closest('form');
    ...                if (form) form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
    ...                break;
    ...            }
    ...        }
    ...    })()

_Find Product Search Input
    [Documentation]    Internal keyword — verifies the product search input is present.
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        function findInputs(root) {
    ...            var inputs = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'INPUT') inputs.push(all[i]);
    ...                if (all[i].shadowRoot) inputs = inputs.concat(findInputs(all[i].shadowRoot));
    ...            }
    ...            return inputs;
    ...        }
    ...        var allInputs = findInputs(document);
    ...        for (var i = 0; i < allInputs.length; i++) {
    ...            if (allInputs[i].getAttribute('name') === 'enter-search' ||
    ...                (allInputs[i].getAttribute('placeholder') && allInputs[i].getAttribute('placeholder').indexOf('Search for products') >= 0)) {
    ...                return 'found';
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })()
    IF    "${result}" == "not_found"
        Fail    msg=Product search input not yet available (will retry).
    END

Add Product By Name
    [Documentation]    Finds a product row by name in the Browse Catalogs results and clicks
    ...    its "Add" button. The product must be visible in the current search results.
    [Arguments]    ${product_name}
    Wait Until Keyword Succeeds    30s    3s    _Click Add Button For Product    ${product_name}
    Wait Until Page Is Settled    caller=Add Product By Name

_Click Add Button For Product
    [Documentation]    Internal keyword — finds the product row and clicks its Add button via JS.
    [Arguments]    ${product_name}
    ${result}=    Execute JavaScript
    ...    return (function(name){
    ...        function findAllButtons(root) {
    ...            var btns = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'BUTTON') btns.push(all[i]);
    ...                if (all[i].shadowRoot) btns = btns.concat(findAllButtons(all[i].shadowRoot));
    ...            }
    ...            return btns;
    ...        }
    ...        /* Find product rows */
    ...        var rows = document.querySelectorAll('runtime_industries_cpq-product-row');
    ...        for (var i = 0; i < rows.length; i++) {
    ...            var root = rows[i].shadowRoot || rows[i];
    ...            var titleEl = root.querySelector('div[title="' + name + '"]');
    ...            if (!titleEl) {
    ...                /* fallback: check text content */
    ...                var divs = root.querySelectorAll('div.heading-style, div[data-id]');
    ...                for (var d = 0; d < divs.length; d++) {
    ...                    if (divs[d].textContent.trim() === name) { titleEl = divs[d]; break; }
    ...                }
    ...            }
    ...            if (titleEl) {
    ...                var btns = findAllButtons(root);
    ...                for (var b = 0; b < btns.length; b++) {
    ...                    if (btns[b].getAttribute('name') === 'Add' ||
    ...                        btns[b].textContent.trim() === 'Add') {
    ...                        btns[b].click();
    ...                        return 'added:' + name;
    ...                    }
    ...                }
    ...                return 'add_button_not_found';
    ...            }
    ...        }
    ...        /* Fallback: search all visible Add buttons near product name text */
    ...        var allBtns = findAllButtons(document);
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            if ((allBtns[i].getAttribute('name') === 'Add' || allBtns[i].textContent.trim() === 'Add')
    ...                && allBtns[i].getAttribute('title') === 'Add') {
    ...                allBtns[i].click();
    ...                return 'added_fallback';
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${product_name}
    Log    Add Product JS result: ${result}
    IF    "${result}" == "not_found" or "${result}" == "add_button_not_found"
        Capture Step Screenshot    add_product_not_found
        Fail    msg=Product "${product_name}" or its Add button not found (will retry).
    END

Click Save Quote In Catalog
    [Documentation]    Clicks the "Save Quote" button in the Browse Catalogs modal if present.
    ...    Waits for the button to become enabled before clicking. The button has
    ...    data-id="objectActionButton" and title="Save Quote".
    ...
    ...    Newer Browse Catalogs builds auto-save each product addition immediately (the
    ...    Quote Summary total behind the modal updates live) and have no Save Quote button
    ...    at all — only "Close". Detect absence up front with a quick, retried presence probe
    ...    (NOT the enablement wait below) before falling back to auto-save/Close — a button
    ...    that is present but slow to enable must still get the full enablement wait, not be
    ...    mistaken for an absent one and have its modal closed unsaved.
    ${status}    ${ignored}=    Run Keyword And Ignore Error
    ...    Wait Until Keyword Succeeds    5s    1s    _Save Quote Button Should Be Present
    ${present}=    Set Variable If    "${status}" == "PASS"    yes    no
    ${before}=    Get Dialog Signature
    IF    "${present}" == "yes"
        Wait Until Keyword Succeeds    30s    2s    _Click Save Quote Via JS
    ELSE
        Log    Save Quote button not present — Browse Catalogs auto-saves; closing modal instead.
        Wait Until Keyword Succeeds    30s    3s    _Click Close Browse Catalogs Modal
    END
    Wait For Dialog To Change    ${before}    caller=Click Save Quote In Catalog    timeout=30s

_Save Quote Button Should Be Present
    ${present}=    _Save Quote Button Present
    Should Be Equal    ${present}    yes    msg=Save Quote button not present yet.

_Save Quote Button Present
    [Documentation]    Internal keyword — quick, non-retrying check for whether the Save Quote
    ...    button exists in the DOM at all, regardless of its enabled/disabled state.
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        function findAllButtons(root) {
    ...            var btns = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'BUTTON') btns.push(all[i]);
    ...                if (all[i].shadowRoot) btns = btns.concat(findAllButtons(all[i].shadowRoot));
    ...            }
    ...            return btns;
    ...        }
    ...        var allBtns = findAllButtons(document);
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            if (allBtns[i].getAttribute('title') === 'Save Quote' || allBtns[i].textContent.trim() === 'Save Quote') {
    ...                return 'yes';
    ...            }
    ...        }
    ...        return 'no';
    ...    })()
    RETURN    ${result}

_Click Close Browse Catalogs Modal
    [Documentation]    Internal keyword — clicks the "Close" button in the Browse Catalogs
    ...    modal footer via JS with shadow DOM traversal.
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        function findAllButtons(root) {
    ...            var btns = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'BUTTON') btns.push(all[i]);
    ...                if (all[i].shadowRoot) btns = btns.concat(findAllButtons(all[i].shadowRoot));
    ...            }
    ...            return btns;
    ...        }
    ...        var allBtns = findAllButtons(document);
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            if (allBtns[i].textContent.trim() === 'Close') {
    ...                allBtns[i].click();
    ...                return 'clicked';
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })()
    IF    "${result}" == "not_found"
        Fail    msg=Close button not found in Browse Catalogs modal (will retry).
    END

_Click Save Quote Via JS
    [Documentation]    Internal keyword — finds and clicks Save Quote button via JS.
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        function findAllButtons(root) {
    ...            var btns = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === 'BUTTON') btns.push(all[i]);
    ...                if (all[i].shadowRoot) btns = btns.concat(findAllButtons(all[i].shadowRoot));
    ...            }
    ...            return btns;
    ...        }
    ...        var allBtns = findAllButtons(document);
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            var btn = allBtns[i];
    ...            if ((btn.getAttribute('title') === 'Save Quote' || btn.textContent.trim() === 'Save Quote')
    ...                && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
    ...                btn.click();
    ...                return 'clicked';
    ...            }
    ...        }
    ...        /* Check if button exists but is disabled */
    ...        for (var i = 0; i < allBtns.length; i++) {
    ...            if (allBtns[i].getAttribute('title') === 'Save Quote' || allBtns[i].textContent.trim() === 'Save Quote') {
    ...                return 'found_but_disabled';
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })()
    Log    Save Quote JS result: ${result}
    IF    "${result}" == "not_found"
        Capture Step Screenshot    save_quote_not_found
        Fail    msg=Save Quote button not found (will retry).
    END
    IF    "${result}" == "found_but_disabled"
        Fail    msg=Save Quote button found but still disabled (will retry).
    END

# ── Bundle Configurator ────────────────────────────────────────────

Configure Bundle Line
    [Documentation]    Opens the product configurator on a bundle PARENT quote line, selects an
    ...    optional component, and commits with "Save & Exit".
    ...
    ...    ⚠ The configurator is reached from the row-level actions dropdown on the RIGHT of each
    ...    line ("Show Actions" → Configure). It is NOT a gear icon and NOT the "+" affordance
    ...    beside it.
    ...    ⚠ Configure the BUNDLE PARENT only. Child lines carry their own action menus; opening
    ...    one of those configures the wrong product.
    ...
    ...    Every selector below was read off the live DOM on 2026-07-28, not inferred.
    ...
    ...    ⚠ The retries here are LOAD-BEARING, not padding: on a live run the menu items, the
    ...    modal tabs and the modal footer each miss on their first attempt and succeed on a
    ...    later one. Screenshots from those attempts are suffixed `_retry` — seeing
    ...    `configurator_tab_retry.png` in a results folder does NOT mean the run failed.
    [Arguments]    ${quote_id}    ${line_name}    ${option_name}    ${tab_label}=${EMPTY}
    Navigate To Quote    ${quote_id}
    Wait Until Page Is Settled    caller=Configure Bundle Line
    Capture Step Screenshot    before_line_action_open
    Wait Until Keyword Succeeds    60s    3s    _Open Line Action Menu    ${line_name}
    Capture Step Screenshot    after_line_action_open
    Wait Until Keyword Succeeds    30s    2s    _Click Line Action    Configure
    Capture Step Screenshot    configurator_opened
    IF    "${tab_label}" != "${EMPTY}"
        Wait Until Keyword Succeeds    60s    3s    _Select Configurator Tab    ${tab_label}
    END
    Wait Until Keyword Succeeds    60s    3s    _Select Configurator Option    ${option_name}
    Capture Step Screenshot    configurator_option_selected
    ${before}=    Get Dialog Signature
    Wait Until Keyword Succeeds    30s    3s    _Commit Configurator
    Wait For Dialog To Change    ${before}    caller=Configure Bundle Line    timeout=60s
    Wait For Quote Line For Product    ${quote_id}    ${option_name}
    Capture Step Screenshot    configurator_saved

_Open Line Action Menu
    [Documentation]    Internal keyword — opens the row-level actions dropdown for a quote line.
    ...
    ...    The line grid is ag-Grid, and it is split into separate PINNED-LEFT / CENTER row
    ...    containers per visual row — confirmed live: the `div[role="row"]` matching the product
    ...    name's `row-id` has a bounding rect only ~250px wide (pinned-left section: checkbox,
    ...    name, disclosure toggle only); the "+"/actions-trigger icons at the row's far right live
    ...    in a DIFFERENT `div[role="row"]` container that does NOT share the same `row-id`/
    ...    `row-index` attribute (or isn't reachable from the same shadow-DOM subtree) — row-id
    ...    joining across sections does not work here, despite being standard ag-Grid behavior
    ...    elsewhere.
    ...    ⚠ The row-action icon is `visibility:hidden` until the row is hovered (confirmed live
    ...    via computed style) — CSS-gated, same as ag-Grid's stock hover-reveal actions column.
    ...    We must dispatch a genuine, trusted `Mouse Over` on the row BEFORE searching for the
    ...    icon, not after: searching first and hovering only on success is circular (the icon
    ...    a pre-hover search finds is never the real trigger). This is a two-phase JS call: find
    ...    the row and stash it, hover it from Robot (trusted event), THEN search for the icon.
    ...    ⚠ `icon-name` is NOT a reliable discriminator — the disclosure toggle AND the real
    ...    actions-trigger icon can both report an empty `icon-name` depending on the render pass.
    ...    Position is reliable: the disclosure toggle sits near the row's left edge (~x=110); the
    ...    real actions trigger sits in the right ~40% of the viewport. Filter candidates on
    ...    `left > innerWidth * 0.6`, excluding the decorative "utility:lock" icon by name, then
    ...    take the rightmost survivor.
    ...    ⚠ We DO NOT scope the icon search to any row container. We take the product-name row's
    ...    vertical CENTER (`getBoundingClientRect()`, not `top`) and search the ENTIRE document
    ...    (all shadow roots) for clickable elements (`button`, `a`, `[role="button"]`,
    ...    `lightning-icon`, `lightning-button-icon` — the real trigger is a plain `button`, not
    ...    an icon) whose own vertical center is within 15px of it — this finds the trigger
    ...    regardless of which ag-Grid section container (pinned-left vs center) it actually
    ...    renders in.
    ...    ⚠ A raw JS `.click()` on the found element is NOT equivalent to a real click — it does
    ...    not check visibility (so it "succeeds" against a still-hidden button) and dispatches an
    ...    untrusted event that some LWC/Aura components reject, surfacing as an empty dropdown +
    ...    a genuine "Sorry to interrupt / CSS Error" toast. We return the DOM element itself
    ...    (Robot/Selenium wraps it as a real WebElement) and use native `Click Element` — a
    ...    trusted click — after `scrollIntoView`.
    ...    Clicking a bare `lightning-icon` does nothing — walk up to the nearest real clickable
    ...    ancestor (`button`, `a`, a `lightning-button-icon`'s shadow-root `button`, or
    ...    `role="button"`), crossing shadow-root boundaries via `getRootNode().host` when
    ...    `parentElement` is null. It is not a `lightning-button-menu` any more either.
    ...    ⚠ Previously, clicking the disclosure toggle by mistake collapsed the bundle's child
    ...    lines AND reliably produced the same "Sorry to interrupt / CSS Error" — do not
    ...    reintroduce a fallback that clicks the leftmost/disclosure icon.
    ...    ⚠ Hierarchy level does NOT identify the bundle parent — every row is `ag-row-level-0`,
    ...    children included. Match on the product name.
    [Arguments]    ${line_name}
    ${row_result}=    Execute JavaScript
    ...    return (function(name){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        var scrollers = deepAll(document, '.ag-center-cols-viewport, .ag-body-horizontal-scroll-viewport, [class*="scroll"]', [], 0);
    ...        for (var s = 0; s < scrollers.length; s++) { scrollers[s].scrollLeft = scrollers[s].scrollWidth; }
    ...        var rows = deepAll(document, 'div[role="row"]', [], 0);
    ...        var targetRow = null;
    ...        for (var i = 0; i < rows.length; i++) {
    ...            if ((rows[i].innerText || '').indexOf(name) !== -1) { targetRow = rows[i]; break; }
    ...        }
    ...        if (!targetRow) { return 'line_not_found'; }
    ...        window.__e2eRow = targetRow;
    ...        return 'row_found';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${line_name}
    Log    Find quote line row: ${row_result}
    IF    "${row_result}" != "row_found"
        Capture Step Screenshot    line_action_menu_retry
        Fail    msg=Could not find quote line "${line_name}" (${row_result}) (will retry).
    END
    ${row_element}=    Execute JavaScript    return window.__e2eRow
    Execute JavaScript    arguments[0].scrollIntoView({block: 'center', inline: 'center'});    ARGUMENTS    ${row_element}
    Mouse Over    ${row_element}
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        function clickableAncestor(el) {
    ...            var cur = el;
    ...            var depth = 0;
    ...            while (cur && depth < 15) {
    ...                if (cur.tagName === 'BUTTON' || cur.tagName === 'A') { return cur; }
    ...                if (cur.tagName === 'LIGHTNING-BUTTON-ICON' && cur.shadowRoot) {
    ...                    var b = cur.shadowRoot.querySelector('button');
    ...                    if (b) { return b; }
    ...                }
    ...                if (cur.getAttribute && cur.getAttribute('role') === 'button') { return cur; }
    ...                var root = cur.getRootNode ? cur.getRootNode() : null;
    ...                cur = cur.parentElement || (root && root.host) || null;
    ...                depth++;
    ...            }
    ...            return null;
    ...        }
    ...        var targetRow = window.__e2eRow;
    ...        var targetRect = targetRow.getBoundingClientRect();
    ...        var targetCenterY = (targetRect.top + targetRect.bottom) / 2;
    ...        var allClickable = deepAll(document, 'button, a, [role="button"], lightning-icon, lightning-button-icon', [], 0);
    ...        var rowClickable = allClickable.filter(function(el){
    ...            var r = el.getBoundingClientRect();
    ...            if (r.width === 0 || r.height === 0) { return false; }
    ...            var cy = (r.top + r.bottom) / 2;
    ...            return Math.abs(cy - targetCenterY) < 15;
    ...        });
    ...        var candidates = rowClickable.filter(function(el){
    ...            var r = el.getBoundingClientRect();
    ...            var n = (el.getAttribute('icon-name') || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.title || '');
    ...            if (n.indexOf('lock') !== -1) { return false; }
    ...            return r.left > (window.innerWidth * 0.6);
    ...        });
    ...        var byRight = candidates.slice().sort(function(x, y){
    ...            return y.getBoundingClientRect().left - x.getBoundingClientRect().left;
    ...        });
    ...        for (var c = 0; c < byRight.length; c++) {
    ...            var target = clickableAncestor(byRight[c]);
    ...            if (target) {
    ...                window.__e2eTarget = target;
    ...                var rr = byRight[c].getBoundingClientRect();
    ...                return 'menu_target_found:' + byRight[c].tagName.toLowerCase() + '@' + Math.round(rr.left);
    ...            }
    ...        }
    ...        var dump = rowClickable.map(function(el){
    ...            var r = el.getBoundingClientRect();
    ...            return el.tagName.toLowerCase() + '(' + (el.getAttribute('icon-name') || el.getAttribute('aria-label') || '?') + ')@' + Math.round(r.left);
    ...        });
    ...        return 'row_action_not_found:[centerY=' + Math.round(targetCenterY) + ' vw=' + window.innerWidth + ' icons=' + dump.join(',') + ']';
    ...    })()
    Log    Open line action menu: ${result}
    IF    not $result.startswith("menu_target_found")
        Capture Step Screenshot    line_action_menu_retry
        Fail    msg=Could not open the actions menu for quote line "${line_name}" (${result}) (will retry).
    END
    ${target_element}=    Execute JavaScript    return window.__e2eTarget
    Execute JavaScript    arguments[0].scrollIntoView({block: 'center', inline: 'center'});    ARGUMENTS    ${target_element}
    ${diag}=    Execute JavaScript
    ...    var el = arguments[0]; var r = el.getBoundingClientRect(); var cs = getComputedStyle(el);
    ...    return JSON.stringify({tag: el.tagName, rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)], display: cs.display, visibility: cs.visibility, pointerEvents: cs.pointerEvents, opacity: cs.opacity, vw: window.innerWidth, vh: window.innerHeight, elAtCenter: (document.elementFromPoint(r.left + r.width/2, r.top + r.height/2) || {}).tagName});
    ...    ARGUMENTS    ${target_element}
    Log    Target element diagnostic before click: ${diag}
    Wait Until Element Is Visible    ${target_element}    timeout=5s
    Click Element    ${target_element}

_Click Line Action
    [Documentation]    Internal keyword — clicks a named item in the open row-action menu.
    ...
    ...    ⚠ The menu items are rendered ASYNCHRONOUSLY after the trigger is clicked — they do
    ...    not exist in the same JS tick. That is why this is a separate, retried keyword rather
    ...    than part of _Open Line Action Menu. Verified live 2026-07-28: querying immediately
    ...    after the click returns zero items.
    [Arguments]    ${action_label}
    ${result}=    Execute JavaScript
    ...    return (function(label){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        var items = deepAll(document, 'lightning-menu-item', [], 0);
    ...        var seen = [];
    ...        for (var i = 0; i < items.length; i++) {
    ...            var a = items[i].shadowRoot ? items[i].shadowRoot.querySelector('a[role="menuitem"]') : null;
    ...            if (!a) { continue; }
    ...            var t = (a.textContent || '').trim();
    ...            seen.push(t);
    ...            if (t === label) {
    ...                window.__e2eTarget = a;
    ...                return 'target_found';
    ...            }
    ...        }
    ...        var menuitems = deepAll(document, '[role="menuitem"]', [], 0);
    ...        for (var m = 0; m < menuitems.length; m++) {
    ...            var mt = (menuitems[m].textContent || '').trim();
    ...            if (mt === label) { window.__e2eTarget = menuitems[m]; return 'target_found_via_role_menuitem'; }
    ...        }
    ...        var panels = deepAll(document, 'div.modal-container, section.slds-modal, div[role="dialog"], div[role="menu"], ul[role="menu"]', [], 0);
    ...        var dump = [];
    ...        for (var p = 0; p < panels.length; p++) {
    ...            var kids = panels[p].querySelectorAll('*');
    ...            var kidTags = [];
    ...            for (var q = 0; q < Math.min(kids.length, 40); q++) { kidTags.push(kids[q].tagName.toLowerCase()); }
    ...            dump.push(panels[p].tagName.toLowerCase() + '.' + (panels[p].className || '') + '[' + kidTags.join(',') + ']');
    ...        }
    ...        var errBoxes = deepAll(document, '.auraErrorBox', [], 0);
    ...        var errText = errBoxes.map(function(e){ return (e.textContent || '').trim().slice(0, 300); }).join(' /// ');
    ...        return 'not_found:[' + seen.join('|') + '] menuitems:[' + menuitems.map(function(e){return (e.textContent||'').trim();}).join('|') + '] panels:[' + dump.join(' ;; ') + '] err:[' + errText + ']';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${action_label}
    Log    Click line action: ${result}
    IF    not ("${result}" == "target_found" or "${result}" == "target_found_via_role_menuitem")
        Capture Step Screenshot    click_line_action_retry
        Fail    msg=Row action "${action_label}" not clickable yet (${result}) (will retry).
    END
    ${target_element}=    Execute JavaScript    return window.__e2eTarget
    Execute JavaScript    arguments[0].scrollIntoView({block: 'center', inline: 'center'});    ARGUMENTS    ${target_element}
    Click Element    ${target_element}

_Select Configurator Tab
    [Documentation]    Internal keyword — selects an option-group tab inside the configurator by
    ...    its `data-label`. Retried because the modal takes several seconds to render.
    [Arguments]    ${tab_label}
    ${result}=    Execute JavaScript
    ...    return (function(label){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        var tabs = deepAll(document, 'a[role="tab"]', [], 0);
    ...        var seen = [];
    ...        for (var i = 0; i < tabs.length; i++) {
    ...            var l = tabs[i].getAttribute('data-label');
    ...            if (!l) { continue; }
    ...            seen.push(l);
    ...            if (l === label) {
    ...                tabs[i].click();
    ...                return 'tab_selected';
    ...            }
    ...        }
    ...        return 'tab_not_found:[' + seen.join('|') + ']';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${tab_label}
    Log    Select configurator tab: ${result}
    IF    "${result}" != "tab_selected"
        Capture Step Screenshot    configurator_tab_retry
        Fail    msg=Configurator tab "${tab_label}" not found (${result}) (will retry).
    END

_Select Configurator Option
    [Documentation]    Internal keyword — ticks an optional component's checkbox in the
    ...    configurator. Idempotent: an already-selected option is a success, not a re-click.
    ...
    ...    ⚠ `textContent` does NOT cross shadow boundaries, and each option renders its product
    ...    name inside a nested shadow root — so a plain textContent match finds nothing and the
    ...    option looks absent. The deepText walker below is required, not defensive coding.
    ...    ⚠ The option list for a tab renders asynchronously after the tab is selected, so this
    ...    is retried.
    [Arguments]    ${option_name}
    ${result}=    Execute JavaScript
    ...    return (function(name){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        function deepText(node, depth) {
    ...            if (depth > 25) return '';
    ...            var t = '';
    ...            var kids = node.childNodes;
    ...            for (var i = 0; i < kids.length; i++) {
    ...                var c = kids[i];
    ...                if (c.nodeType === 3) { t += c.textContent + ' '; }
    ...                else if (c.nodeType === 1) {
    ...                    if (c.shadowRoot) { t += deepText(c.shadowRoot, depth + 1); }
    ...                    t += deepText(c, depth + 1);
    ...                }
    ...            }
    ...            return t;
    ...        }
    ...        function squash(s) {
    ...            var out = '';
    ...            var prevWasSpace = false;
    ...            for (var i = 0; i < s.length; i++) {
    ...                var code = s.charCodeAt(i);
    ...                var isSpace = (code === 32 || code === 9 || code === 10 || code === 13);
    ...                if (isSpace) {
    ...                    if (!prevWasSpace && out.length > 0) { out += ' '; }
    ...                    prevWasSpace = true;
    ...                } else {
    ...                    out += s.charAt(i);
    ...                    prevWasSpace = false;
    ...                }
    ...            }
    ...            return out;
    ...        }
    ...        var opts = deepAll(document, 'runtime_industries_cfg-option', [], 0);
    ...        var seen = [];
    ...        for (var i = 0; i < opts.length; i++) {
    ...            var root = opts[i].shadowRoot || opts[i];
    ...            var txt = squash(deepText(root, 0));
    ...            seen.push(txt.slice(0, 30));
    ...            if (txt.indexOf(name) === -1) { continue; }
    ...            var cb = deepAll(root, 'input[type="checkbox"]', [], 0)[0];
    ...            if (!cb) { return 'option_has_no_checkbox'; }
    ...            if (cb.checked) { return 'already_selected'; }
    ...            cb.click();
    ...            return cb.checked ? 'selected' : 'click_did_not_take';
    ...        }
    ...        return 'option_not_found:[' + seen.join('|') + ']';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${option_name}
    Log    Select configurator option: ${result}
    IF    "${result}" != "selected" and "${result}" != "already_selected"
        Capture Step Screenshot    configurator_option_retry
        Fail    msg=Could not select configurator option "${option_name}" (${result}) (will retry).
    END

_Commit Configurator
    [Documentation]    Internal keyword — commits the configuration via "Save & Exit".
    ...    ⚠ "Save & Exit" both saves and closes; there is no separate close step.
    ${result}=    Execute JavaScript
    ...    return (function(){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        var btns = deepAll(document, 'button', [], 0);
    ...        for (var i = 0; i < btns.length; i++) {
    ...            var b = btns[i];
    ...            if (b.disabled || b.getAttribute('aria-disabled') === 'true') { continue; }
    ...            if ((b.textContent || '').trim() === 'Save & Exit') {
    ...                b.click();
    ...                return 'committed';
    ...            }
    ...        }
    ...        return 'commit_button_not_found';
    ...    })()
    Log    Commit configurator: ${result}
    IF    "${result}" != "committed"
        Capture Step Screenshot    configurator_commit_retry
        Fail    msg=Configurator "Save & Exit" not clickable (${result}) (will retry).
    END

# ── Setup Helpers ──────────────────────────────────────────────────

Lookup Test Account
    [Documentation]    Looks up the test Account by name and sets ACCOUNT_ID as a suite variable.
    ...    Fails if the Account is not found in the org.
    ${acc_id}=    SalesforceAPI.Find Account By Name    ${TEST_ACCOUNT_NAME}
    Set Suite Variable    ${ACCOUNT_ID}    ${acc_id}
    Log    Using Account: ${TEST_ACCOUNT_NAME} (${acc_id})

# ── Composite Workflow Keywords ───────────────────────────────────

Reset Test Account
    [Documentation]    Navigates to the test Account and runs the Reset Account flow.
    ...    Clears transactional data (Opportunities, Quotes, Orders, Assets).
    [Arguments]    ${account_id}
    Navigate To Account    ${account_id}
    Click Highlights Panel Action    Reset Account
    Advance Through Flow Screens
    Dismiss Toast If Present
    Capture Step Screenshot    account_reset

Create Opportunity From Account
    [Documentation]    Creates an Opportunity via the New Opportunity QuickAction on an Account page.
    ...    Returns the new Opportunity Id found via API.
    [Arguments]    ${account_id}
    Navigate To Account    ${account_id}
    Click Highlights Panel Action    New Opportunity
    Wait For Modal
    Save Modal
    SalesforceAPI.Validate Salesforce Id    ${account_id}
    ${opp_id}=    Wait For Related Record Via API
    ...    SELECT Id FROM Opportunity WHERE AccountId = '${account_id}' ORDER BY CreatedDate DESC LIMIT 1
    Dismiss Toast If Present
    Log    Created Opportunity: ${opp_id}
    RETURN    ${opp_id}

Create Quote From Opportunity
    [Documentation]    Creates a Quote via the New Quote QuickAction on an Opportunity page.
    ...    Returns the new Quote Id found via API.
    [Arguments]    ${opportunity_id}
    Navigate To Opportunity    ${opportunity_id}
    Click Highlights Panel Action    New Quote
    Save Modal    Save
    SalesforceAPI.Validate Salesforce Id    ${opportunity_id}
    ${q_id}=    Wait For Related Record Via API
    ...    SELECT Id FROM Quote WHERE OpportunityId = '${opportunity_id}' ORDER BY CreatedDate DESC LIMIT 1
    Dismiss Toast If Present
    Log    Created Quote: ${q_id}
    RETURN    ${q_id}

Add Products Via Browse Catalogs
    [Documentation]    Opens Browse Catalogs on a Quote, selects a catalog, searches for a product,
    ...    adds it, and saves the quote. Handles the Choose Price Book modal if it appears.
    [Arguments]    ${quote_id}    ${catalog_name}    ${product_name}
    Navigate To Quote    ${quote_id}
    Click Browse Catalogs
    Select Catalog By Name    ${catalog_name}
    Search Product In Catalog    ${product_name}
    Add Product By Name    ${product_name}
    Click Save Quote In Catalog
    Capture Step Screenshot    products_added
    Wait For Quote Line For Product    ${quote_id}    ${product_name}

Create Order From Quote
    [Documentation]    Creates a single Order from a Quote via the Create Order flow.
    ...    Selects "Create Single Order" and advances through the flow.
    ...    Returns the new Order Id found via API.
    [Arguments]    ${quote_id}
    Navigate To Quote    ${quote_id}
    Click Highlights Panel Action    Create Order
    Select Order Creation Method
    Advance Through Flow Screens
    Dismiss Toast If Present
    SalesforceAPI.Validate Salesforce Id    ${quote_id}
    ${order_id}=    Wait For Related Record Via API
    ...    SELECT Id FROM Order WHERE QuoteId = '${quote_id}' ORDER BY CreatedDate DESC LIMIT 1
    Log    Created Order: ${order_id}
    RETURN    ${order_id}

Activate Order
    [Documentation]    Navigates to an Order, clicks Activate, confirms the dialog,
    ...    and waits for the Order status to become Activated.
    [Arguments]    ${order_id}
    Navigate To Order    ${order_id}
    Click Highlights Panel Action    Activate
    Confirm Modal Action    Activate
    Dismiss Toast If Present
    Wait For Field Value Via API    Order    ${order_id}    Status    Activated
    Capture Step Screenshot    order_activated

Confirm Modal Action
    [Documentation]    Clicks a confirmation button inside a modal dialog footer.
    ...    Retries for up to 15 seconds to allow the modal to render.
    ...    Used for standard Aura confirmation dialogs (e.g. "Activate order?").
    [Arguments]    ${button_label}=Activate
    ${before}=    Get Dialog Signature
    Wait Until Keyword Succeeds    15s    2s    _Click Modal Footer Button    ${button_label}
    Wait For Dialog To Change    ${before}    caller=Confirm Modal Action

_Click Modal Footer Button
    [Documentation]    Internal keyword — finds and clicks a button inside a modal footer via JS.
    [Arguments]    ${button_label}
    ${result}=    Execute JavaScript
    ...    return (function(label){
    ...        var footers = document.querySelectorAll('div.modal-footer, div.slds-modal__footer, footer.slds-modal__footer');
    ...        for (var f = 0; f < footers.length; f++) {
    ...            var btns = footers[f].querySelectorAll('button');
    ...            for (var i = 0; i < btns.length; i++) {
    ...                var txt = btns[i].textContent.trim();
    ...                var title = btns[i].getAttribute('title') || '';
    ...                if (txt === label || title === label) {
    ...                    btns[i].click();
    ...                    return 'clicked';
    ...                }
    ...            }
    ...        }
    ...        return 'not_found';
    ...    })(arguments[0])
    ...    ARGUMENTS    ${button_label}
    Log    Modal footer button result: ${result}
    IF    "${result}" == "not_found"
        Capture Step Screenshot    modal_button_not_found
        Fail    msg=${button_label} button not found in modal footer (will retry).
    END

# ── Record ID Extraction ────────────────────────────────────────────

Get Record Id From Url
    [Documentation]    Extracts a Salesforce record Id from the current page URL.
    ...    Returns the 18-character Id from a URL like /lightning/r/SObject/001.../view.
    ${url}=    Get Location
    ${id}=    Evaluate    __import__('re').search(r'/([a-zA-Z0-9]{15,18})/view', $url).group(1) if __import__('re').search(r'/([a-zA-Z0-9]{15,18})/view', $url) else ''
    IF    "${id}" == ""
        # Try alternate URL patterns (e.g. after flow completion)
        ${id}=    Evaluate    __import__('re').search(r'/([a-zA-Z0-9]{15,18})(?:\\?|$|#)', $url).group(1) if __import__('re').search(r'/([a-zA-Z0-9]{15,18})(?:\\?|$|#)', $url) else ''
    END
    RETURN    ${id}

Wait For Record Page And Get Id
    [Documentation]    Waits for a record page to load and extracts the record Id from the URL.
    [Arguments]    ${sobject}    ${timeout}=30s
    Wait Until Keyword Succeeds    ${timeout}    3s    _Page Url Should Contain Record    ${sobject}
    Wait Until Page Is Settled    caller=Wait For Record Page And Get Id
    ${id}=    Get Record Id From Url
    RETURN    ${id}

_Page Url Should Contain Record
    [Arguments]    ${sobject}
    ${url}=    Get Location
    Should Match Regexp    ${url}    /lightning/r/${sobject}/[a-zA-Z0-9]{15,18}

# ── Async Wait Keywords ─────────────────────────────────────────────

Wait For Field Value Via API
    [Documentation]    Polls a record field via REST API until it matches the expected value.
    ...    Uses Wait Until Keyword Succeeds for retry logic.
    [Arguments]    ${sobject}    ${record_id}    ${field_name}    ${expected_value}    ${timeout}=${ASYNC_TIMEOUT}    ${interval}=${ASYNC_POLL_INTERVAL}
    Wait Until Keyword Succeeds    ${timeout}    ${interval}
    ...    SalesforceAPI.Verify Field Value Via API    ${sobject}    ${record_id}    ${field_name}    ${expected_value}

Wait For Related Record Via API
    [Documentation]    Polls a SOQL query until at least one record is returned.
    ...    Returns the Id of the first matching record.
    [Arguments]    ${soql}    ${timeout}=${ASYNC_TIMEOUT}    ${interval}=${ASYNC_POLL_INTERVAL}
    ${id}=    Wait Until Keyword Succeeds    ${timeout}    ${interval}
    ...    SalesforceAPI.Verify Related Record Exists    ${soql}
    RETURN    ${id}

# ── Verification ─────────────────────────────────────────────────────

Verify Page Contains Text
    [Documentation]    Asserts that the current page contains the specified text.
    [Arguments]    ${text}    ${timeout}=15s
    Wait Until Page Contains    ${text}    timeout=${timeout}

# ── Screenshots ──────────────────────────────────────────────────────

Capture Step Screenshot
    [Documentation]    Captures a screenshot with a descriptive step-name prefix.
    ...    Increments a counter to ensure unique filenames.
    [Arguments]    ${step_name}=step
    ${counter}=    Evaluate    ${SCREENSHOT_COUNTER} + 1
    Set Suite Variable    ${SCREENSHOT_COUNTER}    ${counter}
    Capture Page Screenshot    filename=e2e_${counter}_${step_name}.png

# ── Toast Handling ───────────────────────────────────────────────────

Dismiss Toast If Present
    [Documentation]    Clicks the close button on any visible Salesforce toast messages.
    ...    Uses both XPath and shadow DOM JS traversal for LWC toast components.
    ${close_btns}=    Get WebElements    xpath=//button[contains(@class, 'toastClose') or (@title='Close' and ancestor::*[contains(@class, 'toast')])]
    FOR    ${btn}    IN    @{close_btns}
        ${visible}=    Run Keyword And Return Status    Element Should Be Visible    ${btn}
        Run Keyword If    ${visible}    Click Element    ${btn}
    END
    # Fallback: dismiss toasts inside shadow DOM (LWC lightning-notification)
    Execute JavaScript
    ...    (function(){
    ...        function findAll(root, tag) {
    ...            var found = [];
    ...            var all = root.querySelectorAll('*');
    ...            for (var i = 0; i < all.length; i++) {
    ...                if (all[i].tagName === tag) found.push(all[i]);
    ...                if (all[i].shadowRoot) found = found.concat(findAll(all[i].shadowRoot, tag));
    ...            }
    ...            return found;
    ...        }
    ...        var toasts = document.querySelectorAll('lightning-notification-toast, div.forceToastManager');
    ...        for (var t = 0; t < toasts.length; t++) {
    ...            var root = toasts[t].shadowRoot || toasts[t];
    ...            var btns = findAll(root, 'BUTTON');
    ...            for (var i = 0; i < btns.length; i++) {
    ...                if (btns[i].title === 'Close' || btns[i].getAttribute('aria-label') === 'Close') {
    ...                    try { btns[i].click(); } catch(e) {}
    ...                }
    ...            }
    ...        }
    ...    })()
    _Wait Best Effort    Dismiss Toast If Present:toast-gone    3s    250ms    _Toast Should Be Gone

_Toast Should Be Gone
    [Documentation]    Internal keyword — passes once no toast notification is visible.
    ${count}=    Execute JavaScript
    ...    return (function(){
    ...        function deepAll(root, sel, out, depth) {
    ...            if (depth > 25) return out;
    ...            var els = root.querySelectorAll(sel);
    ...            for (var i = 0; i < els.length; i++) { out.push(els[i]); }
    ...            var all = root.querySelectorAll('*');
    ...            for (var j = 0; j < all.length; j++) {
    ...                if (all[j].shadowRoot) { deepAll(all[j].shadowRoot, sel, out, depth + 1); }
    ...            }
    ...            return out;
    ...        }
    ...        var toasts = deepAll(document, '.slds-notify_toast', [], 0);
    ...        var shown = 0;
    ...        for (var i = 0; i < toasts.length; i++) {
    ...            var r = toasts[i].getBoundingClientRect();
    ...            if (r.width > 0 && r.height > 0) { shown++; }
    ...        }
    ...        return shown;
    ...    })()
    Should Be Equal As Integers    ${count}    0    msg=Toast still visible.

# ── Recording / Debug ───────────────────────────────────────────────

Pause For Recording If Enabled
    [Documentation]    Pauses test execution when \${PAUSE_FOR_RECORDING} is true.
    ...    Use this at key steps to inspect the DOM via Chrome DevTools (port 9222).
    ...    Press Enter in the terminal to resume.
    [Arguments]    ${message}=Test paused for recording. Press Enter to continue.
    IF    "${PAUSE_FOR_RECORDING}" == "true"
        Log    ${message}    WARN
        ${cdp_url}=    Get Cdp Websocket Url
        Log    CDP WebSocket URL: ${cdp_url}    WARN
        Evaluate    print("\\n" + "=" * 60 + "\\n  PAUSED: ${message}\\n  CDP: " + """${cdp_url}""" + "\\n" + "=" * 60)
        Evaluate    input("  Press Enter to resume...")
        Evaluate    print("  RESUMED\\n" + "=" * 60 + "\\n")
    END

# ── Verification ─────────────────────────────────────────────────────

Verify Assets Exist On Account
    [Documentation]    Checks that at least 1 Asset exists on the Account. Fails if not (for retry).
    [Arguments]    ${account_id}
    ${asset_count}=    SalesforceAPI.Get Asset Count For Account    ${account_id}
    Log    Asset count: ${asset_count}
    Should Be True    ${asset_count} > 0
    ...    msg=No assets yet on Account ${account_id} (will retry).

Verify Renewal Opportunity Includes Product
    [Documentation]    Asserts the renewal Opportunity produced on order activation carries a
    ...    line for ${product_name}. Polls, because the flow is asynchronous.
    ...
    ...    ⚠ THIS is the assertion that detects issue #63 — the Order status does NOT.
    ...    The renewal is created by `RLM_CreateUpdateRenewalOpportunities`, whose TriggerType is
    ...    **PlatformEvent**. When it fails, the Order still reaches Activated, no error toast
    ...    appears, and no AsyncApexJob is marked Failed — the only observable is that the flow's
    ...    output never arrives. A test that stops at "Order is Activated" therefore PASSES while
    ...    #63 is live, which is precisely how #63 survived.
    ...
    ...    Live evidence 2026-07-28: activation at 20:07:54 produced 6 assets at 20:07:57 and the
    ...    renewal Opportunity at 20:08:00 with 5 lines including Software Maintenance @ 5400.
    ...    The preceding run, whose order had no maintenance line, produced 4 (28,500 vs 33,900 —
    ...    a difference of exactly 5,400).
    ...
    ...    Scoped to `Opportunity.Name = 'Renewal Forecast Opportunity'` — the constant
    ...    `RLM_CreateUpdateRenewalOpportunities` sets on the Opportunity it creates (the only
    ...    field the flow deterministically sets that this test can match on). Without this,
    ...    the query would also match an OpportunityLineItem synced onto the SOURCE Opportunity
    ...    from the Quote (standard Quote-Opportunity line sync), which would pass this
    ...    assertion even if the renewal flow never fired — defeating the point of the check.
    [Arguments]    ${account_id}    ${product_name}
    SalesforceAPI.Validate Salesforce Id    ${account_id}
    ${product_id}=    SalesforceAPI.Find Product By Name    ${product_name}
    SalesforceAPI.Validate Salesforce Id    ${product_id}
    ${line_id}=    Wait For Related Record Via API
    ...    SELECT Id FROM OpportunityLineItem WHERE Opportunity.AccountId = '${account_id}' AND Opportunity.Name = 'Renewal Forecast Opportunity' AND Product2Id = '${product_id}' ORDER BY CreatedDate DESC LIMIT 1
    Log    Renewal opportunity line for ${product_name}: ${line_id}
    RETURN    ${line_id}

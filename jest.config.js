const fs = require('fs');
const path = require('path');
const { jestConfig } = require('@salesforce/sfdx-lwc-jest/config');

const projectRoot = __dirname;

// sfdx-lwc-jest resolves `c/<bundle>` only inside sfdx-project.json
// `packageDirectories`. Some bundles are deployed by CCI by path and are not
// listed there (e.g. unpackaged/post_payments_ext). Find every `lwc` directory
// outside the package directories and map just those bundles, so normal
// resolution stays untouched for everything else.
const packageDirectories = require('./sfdx-project.json').packageDirectories.map(
    (d) => d.path.replace(/\\/g, '/')
);

function findLwcRoots(dir) {
    const found = [];
    for (const entry of fs.readdirSync(path.join(projectRoot, dir), {
        withFileTypes: true
    })) {
        if (!entry.isDirectory() || entry.name === 'node_modules') continue;
        const rel = `${dir}/${entry.name}`;
        if (entry.name === 'lwc') found.push(rel);
        else found.push(...findLwcRoots(rel));
    }
    return found;
}

const isInPackage = (p) =>
    packageDirectories.some((d) => p === d || p.startsWith(`${d}/`));

const allLwcRoots = ['force-app', 'unpackaged']
    .filter((d) => fs.existsSync(path.join(projectRoot, d)))
    .flatMap(findLwcRoots)
    .sort();
const outOfPackageRoots = allLwcRoots.filter((p) => !isInPackage(p));

// Pinned on purpose: a new gap, or a fix in sfdx-project.json, must update
// this list (and the mapping below) in the same change.
const EXPECTED_OUT_OF_PACKAGE_ROOTS = ['unpackaged/post_payments_ext/lwc'];
if (
    JSON.stringify(outOfPackageRoots) !==
    JSON.stringify(EXPECTED_OUT_OF_PACKAGE_ROOTS)
) {
    throw new Error(
        'LWC roots outside sfdx-project.json packageDirectories changed.\n' +
            `  expected: ${JSON.stringify(EXPECTED_OUT_OF_PACKAGE_ROOTS)}\n` +
            `  found:    ${JSON.stringify(outOfPackageRoots)}\n` +
            'Update EXPECTED_OUT_OF_PACKAGE_ROOTS in jest.config.js.'
    );
}

// `c/<bundle>` -> <root>/<bundle>/<bundle>.js for out-of-package bundles only.
const outOfPackageMappings = {};
const outOfPackageBundles = [];
for (const root of outOfPackageRoots) {
    for (const entry of fs.readdirSync(path.join(projectRoot, root), {
        withFileTypes: true
    })) {
        const name = entry.name;
        if (
            entry.isDirectory() &&
            fs.existsSync(path.join(projectRoot, root, name, `${name}.js`))
        ) {
            outOfPackageMappings[`^c/${name}$`] =
                `<rootDir>/${root}/${name}/${name}.js`;
            outOfPackageBundles.push(`${root}/${name}`);
        }
    }
}
console.log(
    `[jest.config] LWC bundles outside sfdx-project.json packageDirectories: ${outOfPackageBundles.join(', ') || '(none)'}`
);

module.exports = {
    ...jestConfig,
    roots: allLwcRoots.map((p) => `<rootDir>/${p}`),
    modulePathIgnorePatterns: ['<rootDir>/.localdevserver'],
    testPathIgnorePatterns: ['/node_modules/', '/__mocks__/'],
    clearMocks: true,
    collectCoverageFrom: [
        ...allLwcRoots.map((p) => `${p}/**/*.js`),
        '!**/__tests__/**',
        '!**/__mocks__/**'
    ],
    // Coverage floor = measured baseline, rounded down. Target is 70/55/70/70,
    // reached by a +5 points per quarter ratchet; floors are only ever raised,
    // never lowered. See docs/references/test-plan-2026-09.md (TP-07, TP-07b,
    // section 4.3).
    coverageThreshold: {
        // Two figures, deliberately labelled. Jest subtracts every per-path
        // entry below from `global`, so:
        //   - ALL-FILES measured (what the TP-07b acceptance criterion of
        //     >= 40/30/45/40 is judged against): 60.91/47.93/64.45/62.59
        //     (stmts/branches/fns/lines).
        //   - REMAINING-BUNDLES measured (the 46 bundles without a per-path
        //     entry; this is what `global` is checked against):
        //     40.04/27.36/46.42/40.37, rounded down to 40/27/46/40. That is why
        //     global.branches is 27, not 30 or 47.
        // Do NOT "fix" `global` to the all-files number: it would fail the
        // gate. Architect ruling A, 2026-09-29. Each partition is ratcheted up
        // from its own measured value, never lowered.
        global: { statements: 40, branches: 27, functions: 46, lines: 40 },
        // Per-bundle floors (TP-07b): measured values rounded down, so a
        // regression concentrated in one of these bundles cannot hide in the
        // global average.
        './unpackaged/post_large_stx/lwc/rlmSetUpQuoteWizard/rlmSetUpQuoteWizard.js':
            { statements: 90, branches: 71, functions: 94, lines: 92 },
        './unpackaged/post_billing_ui/lwc/rlmBsgOverview/rlmBsgOverview.js':
            { statements: 75, branches: 59, functions: 82, lines: 81 },
        './unpackaged/post_large_stx/lwc/rlmSetUpQuoteHierarchyTree/rlmSetUpQuoteHierarchyTree.js':
            { statements: 91, branches: 79, functions: 98, lines: 96 },
        './unpackaged/post_utils/lwc/rlmDecisionTableManager/rlmDecisionTableManager.js':
            { statements: 91, branches: 75, functions: 98, lines: 95 },
        './unpackaged/post_utils/lwc/rlmUsageUploader/rlmUsageUploader.js':
            { statements: 95, branches: 84, functions: 97, lines: 97 }
    },
    coverageDirectory: 'coverage',
    coverageReporters: ['text-summary', 'lcov', 'json-summary'],
    moduleNameMapper: {
        ...jestConfig.moduleNameMapper,
        '^@rlm/lwc-test-utils$': '<rootDir>/jest/lwc-test-utils.js',
        ...outOfPackageMappings
    }
};

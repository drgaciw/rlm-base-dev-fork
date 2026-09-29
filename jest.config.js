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
    // Coverage floor = measured baseline after the smoke tranche (TP-07), rounded
    // down. Target is 50/40/50/50, reached by a +5 points per quarter ratchet;
    // the floor is only ever raised, never lowered. See
    // docs/references/test-plan-2026-09.md (TP-07, section 4.3).
    coverageThreshold: {
        global: { statements: 27, branches: 16, functions: 34, lines: 28 }
    },
    coverageDirectory: 'coverage',
    coverageReporters: ['text-summary', 'lcov', 'json-summary'],
    moduleNameMapper: {
        ...jestConfig.moduleNameMapper,
        ...outOfPackageMappings
    }
};

// Fails when config/sf-cli/package.json or package-lock.json disagree with the pins in
// config/tool-versions.env. Called by the setup-toolchain composite action before `npm ci`.
// Inputs come from the environment (the action sources tool-versions.env into this step first):
//   SF_CLI_DIR (default config/sf-cli), SF_CLI_VERSION, SFDMU_VERSION, CODE_ANALYZER_VERSION.
// Node built-ins only: this runs before anything is installed.
import { readFileSync } from "node:fs";
import { join } from "node:path";

const dir = process.env.SF_CLI_DIR || "config/sf-cli";

// npm package name -> the tool-versions.env key that pins it.
const PINS = {
  "@salesforce/cli": "SF_CLI_VERSION",
  sfdmu: "SFDMU_VERSION",
  "@salesforce/plugin-code-analyzer": "CODE_ANALYZER_VERSION",
};

const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
const lock = JSON.parse(readFileSync(join(dir, "package-lock.json"), "utf8"));
const rootDeps = (lock.packages?.[""] ?? {}).dependencies ?? {};

const problems = [];
for (const [name, key] of Object.entries(PINS)) {
  const want = process.env[key];
  if (!want) {
    problems.push(`${key} is not set (config/tool-versions.env)`);
    continue;
  }
  const declared = pkg.dependencies?.[name];
  const locked = lock.packages?.[`node_modules/${name}`];
  if (declared !== want) {
    problems.push(`${dir}/package.json pins ${name}@${declared ?? "(missing)"}, ${key} is ${want}`);
  }
  if (rootDeps[name] !== want) {
    problems.push(`${dir}/package-lock.json root records ${name}@${rootDeps[name] ?? "(missing)"}, ${key} is ${want}`);
  }
  if (!locked || locked.version !== want) {
    problems.push(`${dir}/package-lock.json resolves ${name} to ${locked?.version ?? "(missing)"}, ${key} is ${want}`);
  } else if (!locked.integrity || !locked.resolved) {
    problems.push(`${dir}/package-lock.json entry for ${name} has no resolved/integrity`);
  }
}

if (problems.length > 0) {
  for (const problem of problems) console.log(`::error::${problem}`);
  console.log(
    "::error::Bump config/tool-versions.env and config/sf-cli (package.json + `npm install --package-lock-only`) together, in one PR.",
  );
  process.exit(1);
}
console.log(
  "sf CLI lock OK: " + Object.entries(PINS).map(([name, key]) => `${name}@${process.env[key]}`).join(", "),
);

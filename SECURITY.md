# Security

## Scope

This repository (`rlm-base-dev`) is a Salesforce Revenue Lifecycle Management
build, demo, and enablement environment: CumulusCI tasks and flows, SFDMU
data plans, Apex/LWC metadata, and the AI agent tooling (skills, rules,
scripts) that operates on them. It is not a distributed product or library
with its own release artifact; "the software" below means this repository's
own build/deploy tooling and metadata, not the Salesforce platform or
Revenue Cloud itself. Report platform-level Salesforce vulnerabilities
through Salesforce's own channels, not this repository's issue tracker.

## Supported Branches

| Branch | Status |
|---|---|
| `main` | Supported. Current Release 264 (Winter '27, API v68.0) line; security fixes land here first. |
| `264` | Supported. Release 264 development branch, kept in sync with `main`. |
| `262` | Maintenance only, through 262 GA. |
| `release/262` | Frozen Release 262 GA reference. Not maintained; do not report issues against it in isolation — confirm against `main` first. |

Older `release/*` snapshots and frozen per-release documentation corpora
(`docs/salesforce/**`) are historical references and are not maintained for
security fixes.

## Reporting a Vulnerability

We take the security of our software products and services seriously, which includes all source code repositories managed through our GitHub organizations.

If you believe you have found a security vulnerability, please report it to us as described below.

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report any security issue through the Salesforce vulnerability submission portal at [https://www.sfdc.co/SubmitVuln](https://www.sfdc.co/SubmitVuln) as soon as it is discovered. This repo limits its runtime dependencies in order to reduce the total cost of ownership as much as can be, but all consumers should remain vigilant and have their security stakeholders review all third-party products (3PP) like this one and their dependencies.

The portal is the supported intake and follow-up channel. If you do not receive an acknowledgment, submit a follow-up through the same portal referencing your original report.

Please include the requested information listed below (as much as you can provide) to help us better understand the nature and scope of the possible issue:

- Type of issue (buffer overflow, SQL injection, cross-site scripting, etc.)
- Full paths of source file(s) related to the vulnerability
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

This information will help us triage your report more quickly.

## Preferred Languages

We prefer all communications to be in English.

## Policy

Salesforce follows the principle of [Responsible Disclosure](https://en.wikipedia.org/wiki/Responsible_disclosure).
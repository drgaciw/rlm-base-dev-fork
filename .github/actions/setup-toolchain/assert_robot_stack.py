"""F2 guard (docs/references/test-plan-2026-09.md, TP-02), run by the setup-toolchain action.

cumulusci==4.8.1 declares `selenium<4` and `robotframework-seleniumlibrary<6`;
robot/requirements.txt needs selenium>=4.49 / SeleniumLibrary>=6.9. One resolve of both is
ResolutionImpossible, so the action installs them in two pip calls and the *final environment* is
what matters. A "fix the pip warning" change that re-resolves them together would downgrade
selenium to 3.x and break every Robot suite while the other steps still passed. This fails on that,
and on any pip-check finding beyond the two known CumulusCI conflicts.
"""
import importlib.metadata as md
import re
import subprocess
import sys

import selenium
import SeleniumLibrary

selenium_version = selenium.__version__
selenium_library_version = SeleniumLibrary.__version__
print(f"selenium {selenium_version}, SeleniumLibrary {selenium_library_version}")
failures = []
if selenium_version.split(".")[0] != "4":
    failures.append(f"selenium major must be 4, found {selenium_version} "
                    "(CumulusCI's selenium<4 pin won the resolve)")
if tuple(int(part) for part in re.findall(r"\d+", selenium_library_version)[:3]) < (6, 9, 0):
    failures.append(f"SeleniumLibrary must be >= 6.9.0, found {selenium_library_version}")
# The distribution metadata must agree with the imported modules, so a stale
# or shadowed copy on sys.path cannot satisfy the import check alone.
for dist, imported in (("selenium", selenium_version),
                       ("robotframework-seleniumlibrary", selenium_library_version)):
    if md.version(dist) != imported:
        failures.append(f"{dist} metadata {md.version(dist)} != imported {imported}")

# The only conflicts pip check may report: the two CumulusCI 4.8.1 upper bounds the
# robot stack deliberately overrides. Anything else is a real broken requirement.
allowed = re.compile(
    r"^cumulusci \S+ has requirement (selenium|robotframework-seleniumlibrary)<\d[\d.]*, "
    r"but you have \1 \S+\.$")
check = subprocess.run([sys.executable, "-m", "pip", "check"],
                       capture_output=True, text=True, encoding="utf-8", check=False)
print(f"pip check (exit {check.returncode}):")
print(check.stdout.rstrip() or "(no output)")
if check.returncode != 0:
    lines = [line.strip() for line in check.stdout.splitlines() if line.strip()]
    unexpected = [line for line in lines if not allowed.match(line)]
    if not lines:
        failures.append(f"pip check exited {check.returncode} with no output: "
                        f"{check.stderr!r}")
    elif unexpected:
        failures.append("pip check reported conflicts beyond the allow-listed "
                        "CumulusCI selenium pins:\n  " + "\n  ".join(unexpected))

if failures:
    for failure in failures:
        print(f"::error::{failure}")
    sys.exit(1)
try:
    md.version("cumulusci")
    cumulusci_installed = True
except md.PackageNotFoundError:
    cumulusci_installed = False  # robot without cci: there is no CumulusCI pin to have been lifted
if check.returncode == 0 and cumulusci_installed:
    print("::notice::CumulusCI no longer pins selenium<4 or SeleniumLibrary<6; "
          "drop this allow-list and the requirements-file comments (F2 resolved)")
print("robot stack OK: selenium 4.x and SeleniumLibrary >= 6.9 with only the known CumulusCI conflicts")

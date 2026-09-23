"""Shared Salesforce REST helpers for CumulusCI task modules.

Small, dependency-free functions for the pieces every hand-rolled REST task
in this repo re-implements: resolving the API version, building auth
headers, building a `services/data` base URL, and issuing a request with a
default timeout so a slow or hung endpoint cannot block a build indefinitely.

Deliberately plain functions rather than a mixin/base class: callers already
extend different CumulusCI base task classes (``BaseTask``,
``BaseSalesforceTask``, ``SFDXBaseTask``), so importing functions avoids an
MRO/inheritance decision for each one.
"""
import json
import os
from typing import Any, Dict, Optional

import requests

#: (connect, read) timeout in seconds, passed to every `requests` call made
#: through :func:`request` unless the caller overrides it. Prevents a stalled
#: connection or a slow endpoint from hanging a build indefinitely.
DEFAULT_TIMEOUT = (10, 120)

_FALLBACK_API_VERSION = "68.0"


def api_version(
    org_config: Any = None,
    project_config: Any = None,
    override: Optional[str] = None,
    start_dir: Optional[str] = None,
) -> str:
    """Resolve the Salesforce API version to use for a REST call.

    Preference order: an explicit ``override`` (e.g. a task option), the
    org's own ``api_version``, the project's configured package API version,
    then ``sourceApiVersion`` from the nearest ``sfdx-project.json``. Only
    falls back to a hard-coded default if none of those resolve.
    """
    if override:
        return str(override)
    if org_config is not None:
        org_version = getattr(org_config, "api_version", None)
        if org_version:
            return str(org_version)
    if project_config is not None:
        project_version = getattr(
            project_config, "project__package__api_version", None
        )
        if project_version:
            return str(project_version)
    return _sfdx_project_api_version(start_dir) or _FALLBACK_API_VERSION


def _sfdx_project_api_version(start_dir: Optional[str] = None) -> Optional[str]:
    """Read ``sourceApiVersion`` from the nearest ``sfdx-project.json``.

    Walks upward from ``start_dir`` (default: the current working directory)
    so this works whether the caller runs from the repo root or a
    subdirectory.
    """
    directory = os.path.abspath(start_dir or os.getcwd())
    while True:
        candidate = os.path.join(directory, "sfdx-project.json")
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError):
                return None
            version = data.get("sourceApiVersion")
            return str(version) if version else None
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def headers(access_token: str, content_type: Optional[str] = "application/json") -> Dict[str, str]:
    """Build standard Bearer-auth headers for a Salesforce REST call."""
    result = {"Authorization": f"Bearer {access_token}"}
    if content_type:
        result["Content-Type"] = content_type
    return result


def base_url(instance_url: str, version: str, tooling: bool = False) -> str:
    """Build the ``services/data`` base URL for a given API version.

    With ``tooling=True``, returns the Tooling API base
    (``.../v{version}/tooling``) instead of the standard REST base.
    """
    segment = "/tooling" if tooling else ""
    return f"{instance_url.rstrip('/')}/services/data/v{version}{segment}"


def request(method: str, url: str, *, timeout=DEFAULT_TIMEOUT, **kwargs) -> requests.Response:
    """``requests.request`` with a default timeout so callers can't forget one.

    Accepts the same keyword arguments as ``requests.request`` (``headers``,
    ``json``, ``params``, ``data``, etc.); pass ``timeout=`` explicitly to
    override the default.
    """
    return requests.request(method, url, timeout=timeout, **kwargs)

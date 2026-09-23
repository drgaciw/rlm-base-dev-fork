# syntax=docker/dockerfile:1
#
# Revenue Cloud Base Foundations — self-contained build environment.
#
# Bakes the full local toolchain (Python 3.13 + CumulusCI, Node LTS + Salesforce
# CLI + SFDMU v5, Robot Framework + headless Chromium) plus a snapshot of the
# repo and the friendly `rlm` wrapper CLI and a bundled Claude Code agent, so a
# user who knows nothing about git / cci / sf can connect orgs and build them.
#
# Build (from repo root):   docker build -f docker/Dockerfile -t rlm-base:latest .
# Run:                      docker/rlm            (host launcher — see docker/README.md)
#
# The toolchain mirrors docs/guides/dev-environment-setup.md, but pinned for a
# reproducible container instead of pyenv/nvm/direnv version managers.

# Tool versions are pinned from config/tool-versions.env, not hard-coded here.
# docker-publish.yml loads that file and passes each value as a --build-arg;
# a plain `docker build` (no --build-arg) falls back to the defaults below,
# which are kept in sync with config/tool-versions.env by convention — bump
# both in the same PR.
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim-bookworm

ARG NODE_VERSION=24.16.0
ARG CUMULUSCI_VERSION=4.8.1
ARG SF_CLI_VERSION=2.147.7
ARG SFDMU_VERSION=5.8.0
ARG DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# Environment that must be in place for every `sf`/`cci` invocation.
#   - Generic UNIX keychain → store auth as plain JSON under ~/.sfdx (no OS
#     keyring exists in a headless container).
#   - Disable telemetry/auto-update so the CLI never prompts or self-mutates.
#
# SF_TEMP_SHOW_SECRETS is intentionally NOT set here as an image-wide ENV:
# that would suppress token redaction for every `sf`/`cci` invocation inside
# the container, not just the specific calls that need to read a token. It is
# instead scoped to `cci` only via a shim at /usr/local/bin/cci (see below),
# which mirrors the per-invocation pattern documented in
# docs/guides/dev-environment-setup.md §6 and used by
# .github/workflows/prepare-rlm-org.yml — `sf` called directly still redacts.
# ---------------------------------------------------------------------------
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIPX_HOME=/opt/pipx \
    PIPX_BIN_DIR=/usr/local/bin \
    CHROME_BIN=/usr/bin/chromium \
    SF_USE_GENERIC_UNIX_KEYCHAIN=true \
    SFDX_USE_GENERIC_UNIX_KEYCHAIN=true \
    SF_DISABLE_TELEMETRY=true \
    SF_DISABLE_AUTOUPDATE=true \
    npm_config_update_notifier=false \
    npm_config_fund=false \
    npm_config_audit=false

# ---------------------------------------------------------------------------
# OS packages: git, a headless browser + driver for the Robot UI steps in
# prepare_rlm_org (prepare_docgen, prepare_ux, ...), and small utilities the
# wrapper CLI relies on (jq, tini for PID 1 signal handling).
# ---------------------------------------------------------------------------
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git jq less nano tini procps socat \
        chromium chromium-driver fonts-liberation libnss3 libxss1 libasound2; \
    rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Node.js (pinned exact version, not just major) → Salesforce CLI (sf, pinned)
# + Claude Code, installed globally.
# ---------------------------------------------------------------------------
RUN set -eux; \
    NODE_MAJOR="${NODE_VERSION%%.*}"; \
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -; \
    apt-get install -y --no-install-recommends "nodejs=${NODE_VERSION}-1nodesource1"; \
    apt-mark hold nodejs; \
    rm -rf /var/lib/apt/lists/*; \
    npm install -g "@salesforce/cli@${SF_CLI_VERSION}" @anthropic-ai/claude-code; \
    npm cache clean --force; \
    node --version; sf --version

# ---------------------------------------------------------------------------
# Python tooling: CumulusCI in an isolated pipx venv (bins published to
# /usr/local/bin), plus the Robot Framework deps injected into that same venv
# so CCI can drive `robot`. PyYAML goes in the system interpreter for the build
# harness (scripts/build_harness, which runs under the ambient `python3`).
# robot/requirements.txt is copied first so this layer caches independently of
# repo source churn.
#
# setuptools capped at <77: CumulusCI imports `fs`, which does
# `pkg_resources.declare_namespace` — setuptools >=77 dropped the deprecated
# pkg_resources shim, so an uncapped inject here breaks with
# "ModuleNotFoundError: No module named 'pkg_resources'". Same cap as
# scripts/ai/pr_gate.py's CO_REQUIRES for cumulusci. `--force` is required:
# without it, pipx sees a (too-new) setuptools already present in the venv —
# pulled in transitively by `pipx install cumulusci` itself — and silently
# skips the inject ("already seems to be installed. Not modifying"), so the
# version cap below never actually applies without it.
# ---------------------------------------------------------------------------
COPY robot/requirements.txt /tmp/robot-requirements.txt
RUN set -eux; \
    pip install pipx PyYAML; \
    pipx install "cumulusci==${CUMULUSCI_VERSION}"; \
    pipx inject cumulusci --force "setuptools>=75.4,<77"; \
    pipx inject cumulusci --force -r /tmp/robot-requirements.txt; \
    rm -f /tmp/robot-requirements.txt; \
    cci version

# Scope SF_TEMP_SHOW_SECRETS (see the ENV block above) to `cci` only: move
# pipx's real `cci` entrypoint aside and put a shim in its former place
# (PIPX_BIN_DIR=/usr/local/bin, so this is exactly where callers — `rlm-cli`,
# an interactive shell, `cci org import` — already look). `sf` invoked
# directly is untouched and keeps token redaction.
RUN set -eux; \
    mv /usr/local/bin/cci /usr/local/bin/cci-real; \
    printf '%s\n' \
        '#!/bin/sh' \
        '# Shim: see docker/Dockerfile for why this scopes SF_TEMP_SHOW_SECRETS to cci only.' \
        'export SF_TEMP_SHOW_SECRETS=true' \
        'exec /usr/local/bin/cci-real "$@"' \
        > /usr/local/bin/cci; \
    chmod +x /usr/local/bin/cci

# ---------------------------------------------------------------------------
# Non-root runtime user. SFDMU is installed as this user, pinned exact, so the
# plugin (which lives under ~/.local/share/sf, *outside* the persisted state
# dirs) is baked into the image and survives a fresh state volume. The final
# step asserts the baked plugin still meets the repo floor of 5.6.4
# (upsert-matching fix for relationship externalIds landed in the 5.6.4
# release, commit 50be987; matches validate_setup's required_sfdmu_version) —
# `sort -V -C` exits non-zero, failing the build, if it sorts below 5.6.4.
# ---------------------------------------------------------------------------
RUN set -eux; \
    useradd --create-home --uid 1000 --shell /bin/bash rlm; \
    su -s /bin/bash rlm -c 'mkdir -p ~/.config/sf && printf "%s" "[\"sfdmu\"]" > ~/.config/sf/unsignedPluginAllowList.json'; \
    su -s /bin/bash rlm -c "sf plugins install sfdmu@${SFDMU_VERSION}"; \
    su -s /bin/bash rlm -c 'v=$(sf plugins | grep -i sfdmu | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -1); echo "sfdmu $v"; printf "5.6.4\n%s\n" "$v" | sort -V -C'

# ---------------------------------------------------------------------------
# Baked repo snapshot + wrapper CLI, entrypoint, and interactive banner.
# ---------------------------------------------------------------------------
COPY --chown=rlm:rlm . /opt/rlm-base-dev
COPY docker/rlm-cli        /usr/local/bin/rlm
COPY docker/entrypoint.sh  /usr/local/bin/rlm-entrypoint
COPY docker/setup-state.sh /usr/local/bin/rlm-setup-state
COPY docker/motd.sh        /etc/profile.d/zz-rlm-motd.sh
RUN chmod +x /usr/local/bin/rlm /usr/local/bin/rlm-entrypoint /usr/local/bin/rlm-setup-state; \
    # Pre-create the state dir owned by rlm so a fresh *named* volume mounted
    # here inherits rlm ownership (Docker seeds an empty volume from the image
    # dir's perms). Without this, uid-1000 can't write to the root-owned volume.
    mkdir -p /home/rlm/.rlm-state; \
    chown -R rlm:rlm /home/rlm/.rlm-state

# CumulusCI requires the project to be a git repository (it reads branch/commit/
# remote from git). The baked snapshot ships without history (.git is excluded
# from the build context), so initialize a single-commit repo here — run as the
# rlm user so .git is rlm-owned and git doesn't flag "dubious ownership". A
# mounted /work repo brings its own .git and is unaffected.
RUN su -s /bin/bash rlm -c 'set -eux; cd /opt/rlm-base-dev; \
    export GIT_AUTHOR_NAME="RLM Build" GIT_AUTHOR_EMAIL="build@rlm.local"; \
    export GIT_COMMITTER_NAME="RLM Build" GIT_COMMITTER_EMAIL="build@rlm.local"; \
    git init -q; \
    git symbolic-ref HEAD refs/heads/main; \
    git add -A; \
    git commit -qm "Baked snapshot of rlm-base-dev"; \
    git remote add origin https://github.com/bgaldino/rlm-base-dev || true'

# HOME is set here (not earlier) so root's build steps above don't pollute the
# rlm home dir with root-owned cache files.
ENV HOME=/home/rlm \
    RLM_BAKED_REPO=/opt/rlm-base-dev \
    RLM_STATE_DIR=/home/rlm/.rlm-state \
    BASH_ENV=/home/rlm/.rlm-env

USER rlm
WORKDIR /opt/rlm-base-dev

# tini reaps zombies (sf/cci spawn child processes); entrypoint wires up the
# persistent state volume and chooses the baked vs. mounted repo.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/rlm-entrypoint"]
CMD ["shell"]

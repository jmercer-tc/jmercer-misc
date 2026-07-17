#!/bin/sh
#
# bootstrap-jail-packages.sh
#
# Pre-installs the native FreeBSD toolchain opencode will need to actually
# act on Proxmox/VM automation tasks (create VMs via IaC, configure them via
# Ansible, hit the Proxmox API with curl/jq). Run this ONCE as root inside
# the jail, after linux-rl9 is installed but before creating the opencode
# user - or any time later to add missing tools.
#
# Run from the jail host:
#   jexec opencode sh /path/to/bootstrap-jail-packages.sh
#
# Or copy it into the jail and run it there as root.
#
# NOTE: these are all native FreeBSD packages, installed into the jail's
# normal FreeBSD userland - NOT into the /compat/linux tree. opencode's own
# bash tool spawns child processes (git, tofu, ansible, curl, jq, etc.)
# using the calling user's normal PATH, which resolves to these, not to
# anything under /compat/linux. /compat/linux exists only to satisfy Bun's
# own runtime requirements.

set -eu

pkg install -y \
    git \
    curl \
    jq \
    opentofu \
    ansible \
    python311 \
    py311-pip \
    rsync \
    bash \
    ripgrep \
    tmux \
    gmake \
    pkgconf \
    ca_root_nss

echo "Done. Installed: git curl jq opentofu ansible python311 py311-pip rsync bash ripgrep tmux gmake pkgconf ca_root_nss"

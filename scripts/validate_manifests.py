#!/usr/bin/env python3
"""
scripts/validate_manifests.py

Checks the rendered manifests against the Pod Security "restricted" profile that
manifests/rbac/namespace-and-rbac.yaml enforces on the aiops namespace.

Schema validation (kubeconform) is not enough on its own. Every one of these
Deployments was schema-valid while still being rejected outright at admission,
because `restricted` demands four settings that a valid manifest can simply
omit. Without a check like this, "the YAML is fine" and "the pods will start"
look identical right up until a deploy fails.

Usage:
    kubectl kustomize . | python3 scripts/validate_manifests.py
    python3 scripts/validate_manifests.py rendered.yaml
"""

from __future__ import annotations

import sys

import yaml

POD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}


def pod_spec_of(doc: dict) -> dict | None:
    kind = doc.get("kind")
    if kind not in POD_KINDS:
        return None
    if kind == "CronJob":
        return doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    return doc["spec"]["template"]["spec"]


def check_restricted(doc: dict, spec: dict) -> list[str]:
    """Return a list of restricted-profile violations for one workload."""
    name = f"{doc['kind']}/{doc['metadata']['name']}"
    problems: list[str] = []

    pod_sc = spec.get("securityContext") or {}

    if pod_sc.get("runAsNonRoot") is not True:
        problems.append(f"{name}: pod securityContext.runAsNonRoot must be true")

    # seccompProfile may sit on the pod or on every container; pod level is the
    # sane place for it.
    seccomp = (pod_sc.get("seccompProfile") or {}).get("type")
    if seccomp not in {"RuntimeDefault", "Localhost"}:
        problems.append(
            f"{name}: pod securityContext.seccompProfile.type must be "
            f"RuntimeDefault or Localhost (got {seccomp!r})"
        )

    for container in spec.get("containers", []):
        cname = f"{name} container/{container['name']}"
        c_sc = container.get("securityContext") or {}

        if c_sc.get("allowPrivilegeEscalation") is not False:
            problems.append(f"{cname}: allowPrivilegeEscalation must be false")

        dropped = (c_sc.get("capabilities") or {}).get("drop") or []
        if "ALL" not in dropped:
            problems.append(f"{cname}: capabilities.drop must include ALL")

        if c_sc.get("privileged"):
            problems.append(f"{cname}: privileged is not permitted")

        # Not required by the profile, but a read-only root filesystem needs a
        # writable /tmp or any incidental temp write becomes a crash loop.
        if c_sc.get("readOnlyRootFilesystem"):
            mounts = {m.get("mountPath") for m in container.get("volumeMounts", [])}
            writable = mounts & {"/tmp", "/data", "/var/tmp"}
            if not writable:
                problems.append(
                    f"{cname}: readOnlyRootFilesystem is set but no writable "
                    "scratch volume is mounted"
                )

    return problems


def check_no_committed_secrets(doc: dict) -> list[str]:
    """
    A Secret in the applied set overwrites real credentials on every deploy.
    This is how the platform used to come up holding the string "REPLACE_ME".
    """
    if doc.get("kind") != "Secret":
        return []
    name = doc["metadata"]["name"]
    return [
        f"Secret/{name} is part of the applied set: applying it would overwrite "
        "the real credentials. Keep it out of kustomization.yaml."
    ]


def main() -> int:
    raw = (
        open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    )
    docs = [d for d in yaml.safe_load_all(raw) if d]

    problems: list[str] = []
    workloads = 0

    for doc in docs:
        problems += check_no_committed_secrets(doc)
        spec = pod_spec_of(doc)
        if spec is None:
            continue
        workloads += 1
        problems += check_restricted(doc, spec)

    if problems:
        print(f"✗ {len(problems)} policy violation(s):\n")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(
        f"✓ {workloads} workload(s) across {len(docs)} resources satisfy the "
        "restricted Pod Security profile; no Secret in the applied set"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

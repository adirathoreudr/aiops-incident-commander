"""
executor/meta.py
Read-only metadata API — used by the collector to fetch
rollout history and by the UI to list current deployments.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from kubernetes import client as k8s_client, config as k8s_config

log = logging.getLogger("executor.meta")

MetaRouter = APIRouter()

_loaded = False


def _ensure_k8s() -> None:
    global _loaded
    if _loaded:
        return
    try:
        k8s_config.load_incluster_config()
    except Exception:
        try:
            k8s_config.load_kube_config()
        except Exception as e:
            log.warning("Could not load k8s config: %s", e)
    _loaded = True


@MetaRouter.get("/rollout-history")
async def rollout_history(namespace: str = "default", deployment: str = ""):
    """
    Returns recent ReplicaSet history for a deployment,
    which represents rollout events.
    """
    _ensure_k8s()
    try:
        apps_v1 = k8s_client.AppsV1Api()

        if deployment:
            dep = apps_v1.read_namespaced_deployment(name=deployment, namespace=namespace)
            selector = dep.spec.selector.match_labels
            label_selector = ",".join(f"{k}={v}" for k, v in selector.items())
        else:
            label_selector = ""

        rs_list = apps_v1.list_namespaced_replica_set(
            namespace=namespace,
            label_selector=label_selector,
        )

        events = []
        for rs in sorted(rs_list.items, key=lambda x: x.metadata.creation_timestamp or datetime.min, reverse=True)[:5]:
            containers = rs.spec.template.spec.containers or []
            image = containers[0].image if containers else "unknown"
            revision = rs.metadata.annotations.get("deployment.kubernetes.io/revision", "0") if rs.metadata.annotations else "0"
            events.append({
                "deployment":  deployment or rs.metadata.name,
                "namespace":   namespace,
                "image":       image,
                "revision":    int(revision),
                "started_at":  rs.metadata.creation_timestamp.isoformat() if rs.metadata.creation_timestamp else datetime.now(timezone.utc).isoformat(),
                "status":      "complete" if (rs.status.ready_replicas or 0) > 0 else "inactive",
            })

        return {"events": events}
    except Exception as e:
        log.warning("rollout_history error (%s/%s): %s", namespace, deployment, e)
        return {"events": []}


@MetaRouter.get("/deployments")
async def list_deployments(namespace: str = "default"):
    """Returns list of deployments in namespace for UI dropdowns."""
    _ensure_k8s()
    try:
        apps_v1 = k8s_client.AppsV1Api()
        deps = apps_v1.list_namespaced_deployment(namespace=namespace)
        return {
            "deployments": [
                {
                    "name":          d.metadata.name,
                    "namespace":     d.metadata.namespace,
                    "replicas":      d.spec.replicas,
                    "ready":         d.status.ready_replicas or 0,
                    "image":         (d.spec.template.spec.containers[0].image
                                      if d.spec.template.spec.containers else "unknown"),
                }
                for d in deps.items
            ]
        }
    except Exception as e:
        log.warning("list_deployments error (%s): %s", namespace, e)
        return {"deployments": []}


@MetaRouter.get("/namespaces")
async def list_namespaces():
    """Returns all non-system namespaces."""
    _ensure_k8s()
    try:
        core_v1 = k8s_client.CoreV1Api()
        ns_list = core_v1.list_namespace()
        skip = {"kube-system", "kube-public", "kube-node-lease"}
        return {
            "namespaces": [
                n.metadata.name
                for n in ns_list.items
                if n.metadata.name not in skip
            ]
        }
    except Exception as e:
        log.warning("list_namespaces error: %s", e)
        return {"namespaces": ["default"]}

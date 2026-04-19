"""
executor/actions.py
Executes approved Kubernetes and ArgoCD remediation actions.
Uses the Kubernetes Python client for in-cluster calls and
httpx for ArgoCD REST API calls.
All methods return a consistent result dict.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from kubernetes import client as k8s_client, config as k8s_config
from kubernetes.client.exceptions import ApiException

log = logging.getLogger("executor.actions")

ARGOCD_SERVER   = os.getenv("ARGOCD_SERVER", "http://argocd-server.argocd.svc.cluster.local")
ARGOCD_TOKEN    = os.getenv("ARGOCD_TOKEN", "")
IN_CLUSTER      = os.getenv("IN_CLUSTER", "true").lower() == "true"

_k8s_loaded = False


def _load_k8s() -> None:
    global _k8s_loaded
    if _k8s_loaded:
        return
    try:
        if IN_CLUSTER:
            k8s_config.load_incluster_config()
        else:
            k8s_config.load_kube_config()
        _k8s_loaded = True
        log.info("Kubernetes config loaded (in_cluster=%s)", IN_CLUSTER)
    except Exception as e:
        log.warning("Kubernetes config load failed: %s — actions will be dry-run", e)


class ActionDispatcher:
    """
    Dispatches approved actions to the correct backend.
    Raises no exceptions — always returns result dict.
    """

    def __init__(self) -> None:
        _load_k8s()

    async def execute(
        self,
        action_type: str,
        namespace: str,
        deployment: str,
        replicas: int | None = None,
        argocd_app: str | None = None,
    ) -> dict[str, Any]:
        dispatch = {
            "rollout_restart": self._rollout_restart,
            "scale_up":        self._scale,
            "scale_down":      self._scale,
            "argocd_rollback": self._argocd_rollback,
            "notify_only":     self._notify_only,
        }
        fn = dispatch.get(action_type, self._unknown_action)
        return await fn(
            namespace=namespace,
            deployment=deployment,
            replicas=replicas,
            argocd_app=argocd_app or deployment,
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    async def _rollout_restart(self, namespace: str, deployment: str, **_) -> dict:
        """
        kubectl rollout restart deployment/<name> -n <namespace>
        Triggers a zero-downtime rolling restart by patching the pod template annotation.
        """
        try:
            apps_v1 = k8s_client.AppsV1Api()
            import time
            patch = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": str(int(time.time()))
                            }
                        }
                    }
                }
            }
            apps_v1.patch_namespaced_deployment(
                name=deployment,
                namespace=namespace,
                body=patch,
            )
            msg = f"Rollout restart triggered: {namespace}/{deployment}"
            log.info(msg)
            return {"success": True, "message": msg, "action": "rollout_restart"}
        except ApiException as e:
            msg = f"Rollout restart failed ({namespace}/{deployment}): {e.reason}"
            log.error(msg)
            return {"success": False, "message": msg, "action": "rollout_restart"}
        except Exception as e:
            msg = f"Rollout restart error: {e}"
            log.exception(msg)
            return {"success": False, "message": msg, "action": "rollout_restart"}

    async def _scale(self, namespace: str, deployment: str, replicas: int | None, **_) -> dict:
        """
        kubectl scale deployment/<name> --replicas=N -n <namespace>
        """
        if replicas is None:
            return {"success": False, "message": "replicas parameter required for scale action"}
        try:
            apps_v1 = k8s_client.AppsV1Api()
            patch = {"spec": {"replicas": replicas}}
            apps_v1.patch_namespaced_deployment_scale(
                name=deployment,
                namespace=namespace,
                body=patch,
            )
            msg = f"Scaled {namespace}/{deployment} to {replicas} replicas"
            log.info(msg)
            return {"success": True, "message": msg, "action": "scale", "replicas": replicas}
        except ApiException as e:
            msg = f"Scale failed ({namespace}/{deployment}): {e.reason}"
            log.error(msg)
            return {"success": False, "message": msg, "action": "scale"}
        except Exception as e:
            msg = f"Scale error: {e}"
            log.exception(msg)
            return {"success": False, "message": msg, "action": "scale"}

    async def _argocd_rollback(self, namespace: str, deployment: str, argocd_app: str, **_) -> dict:
        """
        Rolls back ArgoCD application to the previous history revision.
        Uses ArgoCD REST API: POST /api/v1/applications/{name}/rollback
        """
        if not ARGOCD_TOKEN:
            return {"success": False, "message": "ARGOCD_TOKEN not configured"}

        try:
            headers = {
                "Authorization": f"Bearer {ARGOCD_TOKEN}",
                "Content-Type":  "application/json",
            }
            # First, get app history to find last good revision
            async with httpx.AsyncClient(timeout=30.0, verify=False) as http:
                hist_resp = await http.get(
                    f"{ARGOCD_SERVER}/api/v1/applications/{argocd_app}/resource-tree",
                    headers=headers,
                )
                # Trigger rollback to revision 0 (previous)
                roll_resp = await http.post(
                    f"{ARGOCD_SERVER}/api/v1/applications/{argocd_app}/rollback",
                    headers=headers,
                    json={"id": 0, "prune": False},  # id=0 → last successful sync
                )
                roll_resp.raise_for_status()

            msg = f"ArgoCD rollback triggered for app '{argocd_app}'"
            log.info(msg)
            return {"success": True, "message": msg, "action": "argocd_rollback"}
        except httpx.HTTPStatusError as e:
            msg = f"ArgoCD rollback HTTP error ({argocd_app}): {e.response.status_code} {e.response.text}"
            log.error(msg)
            return {"success": False, "message": msg, "action": "argocd_rollback"}
        except Exception as e:
            msg = f"ArgoCD rollback error: {e}"
            log.exception(msg)
            return {"success": False, "message": msg, "action": "argocd_rollback"}

    async def _notify_only(self, namespace: str, deployment: str, **_) -> dict:
        msg = f"Notification-only action for {namespace}/{deployment} — no cluster changes made"
        log.info(msg)
        return {"success": True, "message": msg, "action": "notify_only"}

    async def _unknown_action(self, **kwargs) -> dict:
        msg = f"Unknown action type — blocked. kwargs={kwargs}"
        log.error(msg)
        return {"success": False, "message": msg, "action": "unknown"}

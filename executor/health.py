"""
executor/health.py
Post-action recovery verification.
Polls Kubernetes until the deployment is healthy or timeout elapses.
"""

from __future__ import annotations

import asyncio
import logging
import os

from kubernetes import client as k8s_client

log = logging.getLogger("executor.health")

RECOVERY_TIMEOUT_S = int(os.getenv("RECOVERY_TIMEOUT_SECONDS", "120"))
POLL_INTERVAL_S = float(os.getenv("RECOVERY_POLL_INTERVAL", "5.0"))

# The kubernetes client is synchronous. Called directly from a coroutine it
# blocks the event loop for the whole round trip, which stalls everything else
# the process is serving — including /healthz. With a liveness probe at
# periodSeconds 30 and failureThreshold 3, a Kubernetes API server that stops
# answering gets the executor killed by the kubelet in the middle of a
# remediation. Every such call therefore goes through asyncio.to_thread.


class HealthChecker:
    """
    Waits for a deployment to reach its desired replica count with all pods ready.
    Returns True if recovered within timeout, False otherwise.
    """

    async def wait_for_recovery(
        self,
        namespace: str,
        deployment: str,
        timeout: int = RECOVERY_TIMEOUT_S,
    ) -> bool:
        if not deployment:
            return True  # nothing to check

        log.info(
            "Waiting for recovery: %s/%s (timeout=%ds)", namespace, deployment, timeout
        )
        elapsed = 0.0

        while elapsed < timeout:
            try:
                healthy = await asyncio.to_thread(
                    self._is_deployment_healthy, namespace, deployment
                )
                if healthy:
                    log.info(
                        "Recovery confirmed: %s/%s (elapsed=%.0fs)",
                        namespace,
                        deployment,
                        elapsed,
                    )
                    return True
            except Exception as e:
                log.warning(
                    "Health check error for %s/%s: %s", namespace, deployment, e
                )

            await asyncio.sleep(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S

        log.warning("Recovery timeout: %s/%s after %ds", namespace, deployment, timeout)
        return False

    def _is_deployment_healthy(self, namespace: str, deployment: str) -> bool:
        apps_v1 = k8s_client.AppsV1Api()
        dep = apps_v1.read_namespaced_deployment_status(
            name=deployment, namespace=namespace
        )
        spec_replicas = dep.spec.replicas or 1
        ready_replicas = dep.status.ready_replicas or 0
        updated_replicas = dep.status.updated_replicas or 0

        log.debug(
            "%s/%s: desired=%d ready=%d updated=%d",
            namespace,
            deployment,
            spec_replicas,
            ready_replicas,
            updated_replicas,
        )
        return ready_replicas >= spec_replicas and updated_replicas >= spec_replicas

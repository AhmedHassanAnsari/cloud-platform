"""Kubernetes manifest generation utilities for Sprint 3.

The DevOps Agent now needs to generate a Deployment and Service manifest that
references the exact image that was pushed to GHCR. The manifests are written to a
dedicated ``deployment/`` directory – the only location that this sprint is
allowed to touch.

The generator is deliberately lightweight: it builds a minimal, valid set of
YAML files using Python f‑strings. The values required for the manifests are
collected interactively by the agent (namespace, replica count, ports, etc.)
when they are not already known. All prompts are routed through the agent's
``_ask_user`` helper so the test suite can monkey‑patch it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple


class K8sManifestGenerator:
    """Generate simple Deployment and Service YAMLs.

    The generator does **not** attempt to cover every possible Kubernetes feature –
    it only implements what the sprint specifications require. The goal is to keep
    the output deterministic and easy to test.
    """

    def __init__(self) -> None:
        pass

    # ---------------------------------------------------------------------
    # Deployment generation
    # ---------------------------------------------------------------------
    def generate_deployment_yaml(
        self,
        *,
        app_name: str,
        namespace: str,
        image: str,
        replicas: int = 1,
        container_port: int = 80,
        resources: Tuple[Dict[str, str] | None, Dict[str, str] | None] = (None, None),
    ) -> str:
        """Return a Deployment manifest as a string.

        Args:
            app_name: Name of the Deployment (used also for the ``app`` label).
            namespace: Kubernetes namespace.
            image: Full image reference (``registry/user/project:tag``).
            replicas: Number of pod replicas.
            container_port: Port the container exposes.
            resources: ``(requests, limits)`` where each is a dict mapping
                ``cpu`` / ``memory`` to a string value. ``None`` means the field
                is omitted.
        """
        requests, limits = resources
        resources_block = ""
        if requests or limits:
            resources_block = "        resources:\n"
            if requests:
                resources_block += "          requests:\n"
                for k, v in requests.items():
                    resources_block += f"            {k}: \"{v}\"\n"
            if limits:
                resources_block += "          limits:\n"
                for k, v in limits.items():
                    resources_block += f"            {k}: \"{v}\"\n"

        deployment_yaml = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
  namespace: {namespace}
  labels:
    app: {app_name}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {app_name}
  template:
    metadata:
      labels:
        app: {app_name}
    spec:
      containers:
        - name: {app_name}-container
          image: {image}
          ports:
            - containerPort: {container_port}
{resources_block if resources_block else ""}"""
        return deployment_yaml

    # ---------------------------------------------------------------------
    # Service generation
    # ---------------------------------------------------------------------
    def generate_service_yaml(
        self,
        *,
        app_name: str,
        namespace: str,
        service_type: str = "ClusterIP",
        service_port: int = 80,
        target_port: int = 80,
    ) -> str:
        """Return a Service manifest as a string.

        Args:
            app_name: Used for the selector label.
            namespace: Namespace for the Service.
            service_type: ``ClusterIP``, ``NodePort`` or ``LoadBalancer``.
            service_port: Port exposed by the Service.
            target_port: Port the pod/container listens on.
        """
        service_yaml = f"""apiVersion: v1
kind: Service
metadata:
  name: {app_name}-svc
  namespace: {namespace}
spec:
  selector:
    app: {app_name}
  type: {service_type}
  ports:
    - protocol: TCP
      port: {service_port}
      targetPort: {target_port}
"""
        return service_yaml

    # ---------------------------------------------------------------------
    # Convenience wrapper – generate both files at once
    # ---------------------------------------------------------------------
    def generate_all(
        self,
        *,
        app_name: str,
        namespace: str,
        image: str,
        replicas: int = 1,
        container_port: int = 80,
        service_type: str = "ClusterIP",
        service_port: int = 80,
        target_port: int = 80,
        resources: Tuple[Dict[str, str] | None, Dict[str, str] | None] = (None, None),
    ) -> Dict[str, str]:
        """Generate a dict mapping filenames to manifest contents.

        The dict contains ``deployment.yaml`` and ``service.yaml`` keys.
        """
        deployment = self.generate_deployment_yaml(
            app_name=app_name,
            namespace=namespace,
            image=image,
            replicas=replicas,
            container_port=container_port,
            resources=resources,
        )
        service = self.generate_service_yaml(
            app_name=app_name,
            namespace=namespace,
            service_type=service_type,
            service_port=service_port,
            target_port=target_port,
        )
        return {"deployment.yaml": deployment, "service.yaml": service}

# End of file

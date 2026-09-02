"""Simple Dapr client for fire‑and‑forget service invocation.

The DevOps Agent needs to notify the AIOps Employee once a deployment has
successfully rolled out. Dapr is expected to be running locally on the default
HTTP port (``3500``) and the AIOps service name is provided via the
``AIOPS_APP_ID`` environment variable – falling back to ``aiops``.

We deliberately avoid pulling in a heavyweight SDK; a tiny ``urllib`` call is
sufficient for the hand‑off and keeps the runtime footprint small. The function
returns ``True`` on a 2xx response and ``False`` otherwise.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def invoke_aiops_deployment_notification(
    *,
    image_reference: str,
    deployment_name: str,
    namespace: str,
    manifests_dir: str | None = None,
) -> bool:
    """Send a deployment notification to the AIOps Employee via Dapr.

    The payload is intentionally minimal – the AIOps side only needs to know that
    a deployment succeeded and which image was used. ``manifests_dir`` is
    included for debugging purposes but is optional.
    """
    dapr_port = os.getenv("DAPR_HTTP_PORT", "3500")
    target_app = os.getenv("AIOPS_APP_ID", "aiops")
    url = f"http://localhost:{dapr_port}/v1.0/invoke/{target_app}/method/deployment"

    payload = {
        "image_reference": image_reference,
        "deployment_name": deployment_name,
        "namespace": namespace,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if manifests_dir:
        payload["manifests_dir"] = manifests_dir
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            if 200 <= status < 300:
                logger.info("AIOps handover notification succeeded (status %s)", status)
                return True
            logger.error("AIOps handover failed with status %s", status)
    except urllib.error.HTTPError as e:
        logger.error("AIOps handover HTTP error: %s (%s)", e.code, e.reason)
    except urllib.error.URLError as e:
        logger.error("AIOps handover connection error: %s", e.reason)
    except Exception as e:
        logger.exception("Unexpected error during AIOps handover: %s", e)
    return False

# End of file

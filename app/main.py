# POC — throwaway proxy in front of the Rafay kubeconfig API.
# Shortcut taken: no auth on the proxy itself, minimal error handling,
# config read once at startup. Harden before any real use.
#
# Purpose: expose a single local endpoint that fetches a cluster's
# kubeconfig YAML from Rafay so callers don't handle the API key directly.

import logging

from fastapi import FastAPI, HTTPException, Response
from pydantic_settings import BaseSettings, SettingsConfigDict
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("rafay_proxy")


class Settings(BaseSettings):
    """Config loaded from the local .env file (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    API_URL: str
    API_KEY: str


settings = Settings()
app = FastAPI(title="Rafay API proxy (POC)")

# Rafay kubeconfig endpoint template.
KUBECONFIG_PATH = "/apis/infra.k8smgmt.io/v3/projects/{project}/clusters/{name}/kubeconfig"


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/kubeconfig")
async def kubeconfig(project: str, name: str):
    """Fetch a cluster kubeconfig YAML from Rafay and return it verbatim.

    project (Rafay project) and name (cluster) are required query params.
    """
    url = settings.API_URL.rstrip("/") + KUBECONFIG_PATH.format(project=project, name=name)
    headers = {
        "accept": "application/x-rafay-yaml",
        "X-API-KEY": settings.API_KEY,
    }

    # Log the outbound request. X-API-KEY is omitted on purpose — never log secrets.
    logger.info("Rafay request: GET %s (accept=%s)", url, headers["accept"])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        # Operational fault reaching Rafay — fail with context, not the key.
        logger.error("Rafay request failed: GET %s — %s", url, exc)
        raise HTTPException(status_code=502, detail=f"Failed to reach Rafay: {exc}") from exc

    # Log the response: status, size, and body (truncated on error).
    if resp.status_code == 200:
        logger.info("Rafay response: %s (%d bytes)", resp.status_code, len(resp.content))
    else:
        logger.warning("Rafay response: %s — %s", resp.status_code, resp.text[:500])

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Rafay returned {resp.status_code}: {resp.text[:500]}",
        )

    # Pass the YAML straight through.
    return Response(content=resp.text, media_type="application/yaml")

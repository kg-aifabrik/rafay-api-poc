# POC — throwaway proxy in front of the Rafay kubeconfig API.
# Shortcut taken: no auth on the proxy itself, minimal error handling,
# config read once at startup. Harden before any real use.
#
# Purpose: expose a single local endpoint that fetches a cluster's
# kubeconfig YAML from Rafay so callers don't handle the API key directly.

from fastapi import FastAPI, HTTPException, Response
from pydantic_settings import BaseSettings, SettingsConfigDict
import httpx


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

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        # Operational fault reaching Rafay — fail with context, not the key.
        raise HTTPException(status_code=502, detail=f"Failed to reach Rafay: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Rafay returned {resp.status_code}: {resp.text[:500]}",
        )

    # Pass the YAML straight through.
    return Response(content=resp.text, media_type="application/yaml")

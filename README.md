# rafay-api-poc

POC project to call Rafay APIs for various functions needed for the AiFabrik Compute
Provisioning Service.

This repo contains a minimal [FastAPI](https://fastapi.tiangolo.com/) +
[uvicorn](https://www.uvicorn.org/) server that acts as a **proxy** in front of the
Rafay **Cluster Kubeconfig** API. You call one local endpoint; it adds the Rafay API
key, calls Rafay, and returns the kubeconfig YAML verbatim — so callers never handle
the key directly.

> **POC notice:** this is throwaway code. The proxy has no authentication of its own
> and only minimal error handling. Harden it (proxy auth, structured logging, retries,
> tests) before any real use.

---

## Prerequisites

- **Python 3.11+** (developed on 3.13).
- **[uv](https://docs.astral.sh/uv/)** — the Python package/-env manager used here.
  - macOS: `brew install uv`
  - Linux/macOS (script): `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - If you'd rather not use uv, see [Without uv](#without-uv) below.
- A **Rafay API key** with access to the target project/cluster
  (Rafay console → *My Tools* → *Manage Keys*, or your org's key process).

---

## Setup

```bash
# 1. From the repo root, install dependencies into a local virtualenv (.venv/).
uv sync

# 2. Create your local config from the template.
cp .env.example .env

# 3. Edit .env and fill in the four fields (see table below).
#    .env is gitignored — never commit your real key.
```

### `.env` fields

`.env` holds only the Rafay connection/credentials. Project and cluster are passed
per-request as query params (see [Endpoints](#endpoints)).

| Field          | Meaning                                  | Example                                              |
| -------------- | ---------------------------------------- | ---------------------------------------------------- |
| `API_URL`      | Rafay console base URL (no trailing `/`) | `https://console.gruve-ctl.paas.dev.rafay-edge.net`  |
| `API_KEY`      | Rafay API key (sent as `X-API-KEY`)      | `ra2.xxxxxxxx…`                                      |
| `LOG_FILE_NAME`| Base name for the log file               | `rafay-api-poc` → logs at `/tmp/rafay-api-poc.log`   |

---

## Run

```bash
uv run uvicorn app.main:app --reload --port 8099
```

The server starts on `http://127.0.0.1:8099`. `--reload` auto-restarts on code changes
(drop it for a non-dev run). Pick any free port if `8099` is taken.

You should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8099 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

---

## Endpoints

| Method & path  | Purpose                                                            |
| -------------- | ------------------------------------------------------------------ |
| `GET /healthz` | Liveness check — returns `{"status": "ok"}`.                       |
| `GET /kubeconfig` | Fetches the kubeconfig YAML for a project/cluster.              |
| `GET /docs`    | Interactive Swagger UI to try the endpoints from a browser.        |

`GET /kubeconfig` requires two query params:

| Param     | Meaning                       |
| --------- | ----------------------------- |
| `project` | Rafay project owning the cluster |
| `name`    | Cluster to fetch the kubeconfig for |

Both are required — omitting either returns `422`.

### Try it

```bash
# Health check
curl localhost:8099/healthz

# Kubeconfig for a specific project/cluster
curl "localhost:8099/kubeconfig?project=platform-catalog&name=aifabrik-dev"
```

A successful call returns the kubeconfig YAML (`Content-Type: application/yaml`).

Under the hood the proxy calls:

```
GET {API_URL}/apis/infra.k8smgmt.io/v3/projects/{project}/clusters/{name}/kubeconfig
    accept: application/x-rafay-yaml
    X-API-KEY: <API_KEY>
```

---

## Logs

Each request/response to Rafay is logged to both the console and a file at
`/tmp/<LOG_FILE_NAME>.log` (default **`/tmp/rafay-api-poc.log`**). The API key is
never logged. Tail it with:

```bash
tail -f /tmp/rafay-api-poc.log
```

---

## Tests

```bash
uv run pytest -v
```

The suite mocks the Rafay call (no network) and includes a test that a successful
proxy response is a **valid Kubernetes kubeconfig** — it parses as YAML and has
`apiVersion: v1`, `kind: Config`, and non-empty `clusters`/`contexts`/`users`.

---

## Troubleshooting

| Symptom | Likely cause / fix |
| ------- | ------------------ |
| `500 … api key not found` | `API_KEY` in `.env` is wrong/placeholder. Use a valid Rafay key. |
| `404` from Rafay | The `project` or `name` param doesn't exist, or `API_URL` is wrong. |
| `422` from the proxy | Missing required `project` or `name` query param. |
| `502 Failed to reach Rafay` | Network/DNS issue or `API_URL` unreachable from your machine. |
| `pydantic … field required` at startup | A field is missing in `.env`. All four are required. |
| Port already in use | Re-run with a different `--port`. |

---

## Without uv

If you prefer stock Python tooling:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install "fastapi>=0.115" "uvicorn[standard]>=0.34" "httpx>=0.28" "pydantic-settings>=2.7"
uvicorn app.main:app --reload --port 8099
```

---

## Project layout

```
.
├── app/
│   └── main.py        # FastAPI proxy (the whole app)
├── tests/
│   └── test_main.py   # pytest suite (mocks Rafay; no network)
├── .env.example       # config template — copy to .env
├── pyproject.toml     # dependencies (managed by uv)
└── README.md
```

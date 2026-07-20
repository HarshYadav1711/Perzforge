# Perzforge serving contract v1

Any registered model can be deployed as an inference endpoint if its artifact
prefix satisfies this contract. The platform does **not** impose a training
framework — only a small, predictable process boundary.

## Artifact layout

Under the model's MinIO prefix (e.g. `models/<user>/<name>/<version>/`):

```
serve.py          # required
<any other files> # weights, configs, tokenizers, …
```

`serve.py` must be at the **root** of the artifact prefix (not nested).

## Required API

`serve.py` must expose:

```python
def predict(payload: dict) -> dict:
    ...
```

- `payload` is a JSON object (decoded dict).
- The return value must be JSON-serializable (dict).
- Import-time side effects should be limited to loading weights / building the
  model; requests call `predict` only.

## Runtime

On deploy, the platform:

1. Downloads the artifact prefix to a host directory.
2. Starts the standard runner image (`docker/serve-runner.Dockerfile`) with
   that directory mounted **read-only** at `/model`.
3. Attaches the container to the `perzforge-serving` Docker bridge network.
4. Probes `GET /healthz` until ready (or fails after 60s).

The runner loads `/model/serve.py`, exposes:

| Method | Path       | Behavior                          |
|--------|------------|-----------------------------------|
| GET    | `/healthz` | `{ "status": "ok" }`              |
| POST   | `/predict` | body → `predict(body)` → JSON out |

Hardening matches job containers (B3) except networking: serving containers
need a reachable network; GPU is **off** by default.

## Calling a live endpoint

```
POST /api/v1/endpoints/{route}/predict
Authorization: Bearer <jwt|api-key with llm:invoke>
Content-Type: application/json

{ ... arbitrary JSON object ... }
```

Any authenticated caller with `llm:invoke` (or a JWT user role that includes
it) may invoke the endpoint. Ownership is **not** required for predict;
ownership **is** required to stop.

## Non-goals (v1)

Autoscaling, GPU inference endpoints, canary / versioned routing, and public
unauthenticated exposure are out of scope.

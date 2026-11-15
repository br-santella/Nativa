# Deploy

The public demo has two parts:

| Part | Where | URL |
|---|---|---|
| Frontend (`frontend/`) | Vercel, rebuilt on every push to `main` | https://nativa-tau.vercel.app |
| Engine API (`motor_field_shift/`) | Azure VM running Docker Compose | https://52-240-157-74.sslip.io |

## Files

| File | Purpose |
|---|---|
| `../Dockerfile` | API image: Python 3.12, dependencies from `uv.lock`, code in `src/` and `api/`, versioned inputs in `data/` |
| `../.dockerignore` | Keeps `.venv`, `data/raw`, `data/processed`, docs and ingestion scripts out of the image |
| `entrypoint.sh` | Syncs `data/raw` and `data/processed` from a Hugging Face dataset, then starts `uvicorn` on port 7860 |
| `compose.yaml` | Runs the API and Caddy; the data and the certificates live in named volumes |
| `Caddyfile` | Caddy reverse proxy with automatic HTTPS (Let's Encrypt) for `$DOMAIN` |
| `.env` | Not versioned. Holds `DOMAIN`, `HF_DATA_REPO` and `HF_TOKEN` |

## Data

The inputs that the API reads from `data/raw` and `data/processed` (about 2.1 GB) are stored in the private
Hugging Face dataset `br-santella/nativa-data`, with the same paths as in `data/`. On every start, the
entrypoint runs `hf download`, which only fetches new or changed files. `HF_TOKEN` must be a read-only token
with access to that dataset.

To add or replace a file, upload it with its path relative to `data/`:

```bash
cd motor_field_shift/data
hf upload br-santella/nativa-data . . --repo-type dataset --include raw/<folder>/<file>
```

Then restart the API on the VM (see below).

## Frontend configuration

In the Vercel project, the root directory is `frontend` and the environment variable
`VITE_API_URL=https://52-240-157-74.sslip.io` is set for Production. Vite embeds the variable at build time,
so changing it requires a redeploy.

## VM

- Azure for Students subscription, resource group `nativa-rg`, VM `nativa-api` in `northcentralus`.
- Size `Standard_B2als_v2` (2 vCPU, 4 GB RAM), Ubuntu 24.04, 32 GB Standard SSD, static public IP `52.240.157.74`.
- Inbound ports 22, 80 and 443. Login: `ssh azureuser@52.240.157.74`.
- The stack lives in `~/nativa/motor_field_shift/deploy`.

## Operations

Update the API after a change in `motor_field_shift/` (copy the code to the VM, then rebuild):

```bash
cd ~/nativa/motor_field_shift/deploy
docker compose up -d --build
```

Restart after changing `.env` or a dataset file:

```bash
docker compose up -d --force-recreate api
```

Logs and status:

```bash
docker compose ps
docker compose logs -f api
curl https://52-240-157-74.sslip.io/health
```

Stop or start the VM to save credit (the IP is static, so the URL does not change):

```bash
az vm deallocate -g nativa-rg -n nativa-api
az vm start -g nativa-rg -n nativa-api
```

The containers use `restart: unless-stopped`, so they come back when the VM starts.

## Notes

- Points without SoilGrids raster values (urban areas) make the engine query the SoilGrids REST API, which can
  take about 15 s to answer. Farmland points are answered from the local rasters in 1 to 2 s.
- Vercel uses the Hobby plan. The VM costs about USD 33.50/month while running (VM, disk and IP), paid from the
  Azure for Students credit.

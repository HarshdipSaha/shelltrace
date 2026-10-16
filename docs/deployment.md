# Deployment

| Layer | Where | Address |
| --- | --- | --- |
| UI | Vercel project `harsh-1b18/frontend` | https://frontend-five-opal-42.vercel.app |
| API | Google Cloud Run service `shelltrace-api` (project `shelltrace-demo-54136`, `us-central1`) | https://shelltrace-api-796979480738.us-central1.run.app |
| Graph | FalkorDB 6.0.2 in Docker on Compute Engine VM `falkordb-vm` (`10.128.0.2`, no public IP) | VPC-internal only |

```
Browser ─▶ Vercel (static UI, rewrites /api/* and /mcp/*) ─▶ Cloud Run API ─(Direct VPC egress)─▶ FalkorDB VM
```

## Design choices

- **The API cannot run as serverless functions.** It holds a long-lived MCP session manager and calls its own `/mcp` endpoint over loopback, so Cloud Run runs a single always-on instance (`--min-instances=1 --max-instances=1 --no-cpu-throttling`) with `ST_MCP_URL=http://127.0.0.1:8080/mcp/`.
- **FalkorDB is private.** The VM has no external address. Cloud NAT (`st-router` / `st-nat`) gives it outbound access to pull packages and images. Firewall rule `allow-falkordb-internal` allows TCP 6379 only from `10.128.0.0/9`, and Redis requires a password.
- **Data persists on the VM** (`/var/lib/falkordb`, append-only file). The API re-seeds the synthetic template graph on start if it is missing.
- **The deployment is a demo.** The API is unauthenticated, uses `LLM_PROVIDER=none` (no provider keys), and serves only synthetic data. Review, watch, designation and alias-decision endpoints are publicly writable, so add authentication before using real data.

## Deploy / redeploy the API

```bash
cd backend
gcloud run deploy shelltrace-api --project=shelltrace-demo-54136 --region=us-central1 \
  --source=. --allow-unauthenticated --memory=1Gi --cpu=1 \
  --min-instances=1 --max-instances=1 --no-cpu-throttling --timeout=120 \
  --network=default --subnet=default --vpc-egress=private-ranges-only \
  --set-env-vars="FALKORDB_HOST=10.128.0.2,FALKORDB_PORT=6379,FALKORDB_PASSWORD=<password>,ST_MCP_URL=http://127.0.0.1:8080/mcp/,LLM_PROVIDER=none,JEV_ENABLED=false"
```

The FalkorDB password is stored only as the VM metadata key `falkor-pw` and the Cloud Run env var `FALKORDB_PASSWORD`; it is never committed. Rotate it by changing the metadata key, resetting the VM, and redeploying with the new value.

## Deploy the UI

```bash
cd frontend
vercel deploy          # preview
vercel deploy --prod   # production alias
```

`frontend/vercel.json` holds the rewrites. If the API URL changes, update both destinations. Vercel Deployment Protection is on by default for new projects; turn it off in the project settings if the site should be publicly viewable.

## Verify

```bash
curl https://shelltrace-api-796979480738.us-central1.run.app/api/health
curl -X POST https://shelltrace-api-796979480738.us-central1.run.app/api/cases \
  -H 'content-type: application/json' \
  -d '{"workspace":"demo","entity_id":"c_nordharbor","as_of":"2024-01-01","max_hops":6,"rulepacks":["OFAC","EU","UK"],"mode":"playbook"}'
```

The hero case should return `EXPOSED` with `BLOCKED` under OFAC, EU and UK.

## Tear down

```bash
gcloud projects delete shelltrace-demo-54136
```

This removes Cloud Run, the VM, NAT and all stored data. Running costs come from the always-on Cloud Run instance, the e2-small VM and Cloud NAT.

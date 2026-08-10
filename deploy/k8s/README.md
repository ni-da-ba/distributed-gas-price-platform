# Kubernetes deployment

The base deploys three workloads: two API replicas, one analysis worker, and one
ephemeral Redis instance. It also creates internal Services for the API and
Redis. No Ingress, cloud load balancer, persistent volume, credential, or
production policy is implied.

## Render and inspect

```bash
kubectl kustomize deploy/k8s/base > /tmp/distributed-gas-price-platform.yaml
kubectl apply --dry-run=server -f /tmp/distributed-gas-price-platform.yaml
```

CI always performs the local render. Server-side dry-run requires access to a
Kubernetes API and is therefore a deployment-environment check.

## Run on a local kind cluster

The committed base references the release image
`ghcr.io/ni-da-ba/distributed-gas-price-platform:1.0.1`. To test an unpushed
local build under the same name:

```bash
docker build -t ghcr.io/ni-da-ba/distributed-gas-price-platform:1.0.1 .
kind load docker-image ghcr.io/ni-da-ba/distributed-gas-price-platform:1.0.1
kubectl apply -k deploy/k8s/base
kubectl rollout status deployment/gas-price-api
kubectl rollout status deployment/gas-price-worker
kubectl rollout status deployment/redis
kubectl port-forward service/gas-price-api 8000:80
```

In another terminal:

```bash
curl http://127.0.0.1:8000/health/ready
curl -X POST http://127.0.0.1:8000/v1/data/refresh
curl http://127.0.0.1:8000/v1/regions
```

## Production gaps

- Pin application and Redis images by immutable digest.
- Replace the ephemeral Redis volume with a managed or persistent deployment.
- Add authentication and rate limits for mutating routes.
- Add a reliable queue protocol with acknowledgements, leases, retries, and a
  dead-letter path.
- Add network policies, external TLS/Ingress, observability, backups, and a
  tested recovery procedure for the target environment.

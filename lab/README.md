# Local Lab — APE DNS Crossplane POC

Self-contained local environment for testing Crossplane compositions, XRDs, and
Backstage templates against **real AWS Route53** (no LocalStack).

## What this lab runs

| Component       | Where                       | Purpose                                                          |
|-----------------|-----------------------------|------------------------------------------------------------------|
| Kind cluster    | `ape-dns-lab`               | Single-node k8s, ports 80/443 mapped                             |
| ingress-nginx   | `ingress-nginx` ns          | Host-based routing for Argo/Backstage                            |
| Crossplane      | `crossplane-system` ns      | Composition engine                                               |
| Functions       | cluster-wide                | `function-go-templating`, `function-auto-ready`                  |
| AWS providers   | cluster-wide                | `provider-aws-route53`, `provider-aws-cloudformation`            |
| ArgoCD          | `argocd` ns                 | Syncs this repo → cluster                                        |
| Backstage       | `lab/backstage/` (host)     | Runs with `yarn dev`, commits entity YAML via PR                 |

## Layout

```
lab/
├── Makefile                    # make up / down / status / aws-creds
├── kind/cluster.yaml
├── bootstrap/
│   ├── 00-kind.sh
│   ├── 10-ingress.sh
│   ├── 20-crossplane.sh        # phase 2
│   └── 30-argocd.sh            # phase 3
├── crossplane/functions.yaml   # cluster Functions (phase 2)
├── argocd/
│   ├── root-app.yaml
│   └── apps/
│       ├── crossplane-providers.yaml
│       ├── crossplane-provider-config-aws.yaml
│       ├── crossplane-compositions-dns.yaml
│       └── entities.yaml
├── overrides/
│   ├── providers.local.yaml
│   └── provider-config-aws.local.yaml
├── samples/                    # direct kubectl XR tests
├── backstage-templates/        # lab-adapted templates (vanilla-compatible)
└── backstage/                  # scaffolded app (gitignored except config)

entities/                       # GitOps source of truth for XRs (new top-level)
└── environments/…              # APE hierarchy: domain/subdomain/system/env
```

## Quick start

```bash
# 1. Bring up cluster + platform (no AWS creds needed yet)
make -C lab up

# 2. Provide AWS creds (writes a Secret in crossplane-system)
#    Put your Route53-capable credentials in ~/.aws/credentials first.
make -C lab aws-creds

# 3. Open Argo UI
make -C lab argo-port   # → http://localhost:8081
make -C lab argo-password

# 4. Sanity check via kubectl
kubectl apply -f lab/samples/zone-example-com.yaml
kubectl get zone.dock.tech -A
kubectl describe zone.dock.tech -A

# 5. Start Backstage (after phase 9–10 setup)
cd lab/backstage && yarn dev
```

## Tearing down

```bash
make -C lab down   # kind delete cluster
rm -rf lab/ entities/
```

The three production chart directories (`crossplane-compositions-dns/`,
`crossplane-providers/`, `crossplane-provider-config-aws/`) and the production
`backstage-templates/` are **never modified** by the lab. All local divergence
lives under `lab/overrides/` and `lab/backstage-templates/`.

## Smoke test (end-to-end)

See `lab/README.md` section below (added in phase 11).

# ArgoCD Installation

## Quick Install

```bash
# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
kubectl wait --for=condition=Available --timeout=600s deployment/argocd-server -n argocd

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo

# Port-forward to access UI (in another terminal)
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Access: https://localhost:8080
# Username: admin
# Password: <from command above>
```

## Alternative: Use the Job

```bash
kubectl apply -f platform/argocd/install/argocd-install.yaml
```

## Verify Installation

```bash
kubectl get pods -n argocd
kubectl get svc -n argocd
```

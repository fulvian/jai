# JAI - Phase 10 Deployment Guide

**Version**: 1.0  
**Date**: 2026-03-22  
**Phase**: 10 - Production Deployment & Performance Optimization

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start with Docker Compose](#quick-start-with-docker-compose)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [AWS EKS Deployment](#aws-eks-deployment)
6. [GCP GKE Deployment](#gcp-gke-deployment)
7. [Azure AKS Deployment](#azure-aks-deployment)
8. [On-Premise Deployment](#on-premise-deployment)
9. [Post-Deployment Verification](#post-deployment-verification)
10. [Monitoring Setup](#monitoring-setup)
11. [Troubleshooting](#troubleshooting)

---

## Overview

This guide covers deploying JAI (Me4BrAIn) to production using:
- **Docker Compose** for simple deployments
- **Kubernetes** for orchestrated deployments
- **AWS EKS**, **GCP GKE**, **Azure AKS** for managed Kubernetes
- **On-premise** for private cloud deployments

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Load Balancer / Ingress                    │
└─────────────────────────────────────────────────────────────┘
                    ↓                    ↓
    ┌───────────────────────────┐   ┌───────────────────────────┐
    │   Me4BrAIn Backend (x3)    │   │     Frontend (x2)         │
    │   Port 8089               │   │     Port 3000             │
    └───────────────────────────┘   └───────────────────────────┘
                    ↓
    ┌──────────┬──────────┬──────────┬──────────┐
    │ Postgres │  Redis   │  Qdrant  │  Jaeger  │
    │  5432    │   6379   │   6333   │  14268   │
    └──────────┴──────────┴──────────┴──────────┘
```

---

## Prerequisites

### Common Requirements

- Docker 24.0+ or Kubernetes 1.28+
- kubectl 1.28+ (for K8s deployments)
- Helm 3.14+ (optional, for some deployments)
- 8GB+ RAM available
- 20GB+ disk space

### Platform-Specific CLI Tools

| Platform | CLI Tools |
|----------|-----------|
| AWS | aws-cli, eksctl |
| GCP | gcloud, kubectl |
| Azure | az, kubectl |
| On-Prem | kubectl |

---

## Quick Start with Docker Compose

For development/staging or simple production setups:

### 1. Clone and Configure

```bash
# Clone repository
git clone https://github.com/your-org/jai.git
cd jai

# Copy environment template
cp backend/.env.example backend/.env

# Edit environment variables
nano backend/.env
```

### 2. Configure Essential Variables

```bash
# backend/.env
ENVIRONMENT=production
DB_USER=jai_user
DB_PASSWORD=your_secure_password_here
DB_NAME=me4brain
REDIS_PASSWORD=
ENCRYPTION_KEY=your-32-byte-fernet-key-here
SECRET_KEY=your-django-secret-key
GRAFANA_PASSWORD=your_grafana_password

# LLM Providers (optional)
OLLAMA_BASE_URL=http://ollama:11434
LM_STUDIO_BASE_URL=http://lmstudio:1234
```

### 3. Start Services

```bash
# Build and start all services
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f backend
```

### 4. Verify Deployment

```bash
# Health check
curl http://localhost:8089/health/live

# API check
curl http://localhost:8089/v1/health
```

---

## Kubernetes Deployment

### 1. Prepare Cluster

```bash
# Create namespace
kubectl apply -f kubernetes/namespace.yaml

# Create secrets (MANUALLY - never commit real values)
kubectl create secret generic me4brain-secrets \
  --from-literal=DB_PASSWORD='your-secure-password' \
  --from-literal=ENCRYPTION_KEY='your-32-byte-key' \
  --from-literal=SECRET_KEY='your-secret-key' \
  -n jai-production
```

### 2. Deploy Application

```bash
# Apply configurations
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
kubectl apply -f kubernetes/ingress.yaml

# Check deployment status
kubectl rollout status deployment/me4brain -n jai-production

# View pods
kubectl get pods -n jai-production
```

### 3. Verify Deployment

```bash
# Port forward for local testing
kubectl port-forward svc/me4brain 8089:8089 -n jai-production

# Health check
curl http://localhost:8089/health/live
curl http://localhost:8089/health/ready
```

---

## AWS EKS Deployment

### 1. Create EKS Cluster

```bash
# Create EKS cluster
eksctl create cluster \
  --name jai-cluster \
  --region us-east-1 \
  --version 1.28 \
  --nodegroup-name standard-workers \
  --node-type t3.xlarge \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 10 \
  --managed

# Configure kubectl
aws eks update-kubeconfig --region us-east-1 --name jai-cluster
```

### 2. Install Add-ons

```bash
# AWS Load Balancer Controller
helm repo add eks https://aws.github.io/eks-charts
helm install aws-load-balancer-controller \
  aws-load-balancer-controller/ingress-nginx \
  -n kube-system \
  --set clusterName=jai-cluster

# External DNS (for automatic DNS)
helm install external-dns \
  bitnami/external-dns \
  -n kube-system \
  --set provider=aws \
  --set aws.zoneType=public \
  --set domainFilters[0]=example.com
```

### 3. Deploy JAI

```bash
# Update image in deployment
sed -i 's/me4brain:latest/YOUR_DOCKER_REGISTRY\/me4brain-backend:latest/g' \
  kubernetes/deployment.yaml

# Deploy
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
kubectl apply -f kubernetes/ingress.yaml

# Configure AWS ALB annotations in ingress.yaml
# (already set in kubernetes/ingress.yaml)
```

### 4. AWS-Specific Configuration

```yaml
# kubernetes/configmap.yaml additions for AWS
data:
  AWS_REGION: "us-east-1"
  S3_BUCKET: "jai-data-bucket"
  # CloudWatch metrics (if using AWS integrated monitoring)
```

### 5. Cost Optimization

```bash
# Enable cluster autoscaler
helm install cluster-autoscaler \
  autoscaler/cluster-autoscaler \
  -n kube-system \
  --set awsRegion=us-east-1 \
  --set autoDiscovery.clusterName=jai-cluster
```

---

## GCP GKE Deployment

### 1. Create GKE Cluster

```bash
# Set project
gcloud config set project your-project-id

# Create cluster
gcloud container clusters create jai-cluster \
  --region us-central1 \
  --node-type n2-standard-4 \
  --num-nodes 3 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 10 \
  --workload-pool=your-project-id.svc.id.goog

# Get credentials
gcloud container clusters get-credentials jai-cluster --region us-central1
```

### 2. Install Add-ons

```bash
# Nginx Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.9.0/deploy/static/provider/cloud/deploy.yaml

# Cloud SQL Proxy (for managed PostgreSQL)
kubectl create secret generic cloudsql-credentials \
  --from-file=credentials.json=/path/to/service-account-key.json

# Enable GKE Autopilot (optional)
# gcloud container clusters create jai-cluster --enable-autopilot ...
```

### 3. Deploy JAI

```bash
# Update ingress annotations for GCP
# Use `kubernetes.io/ingress.class: nginx` and remove AWS-specific annotations

# Deploy
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
kubectl apply -f kubernetes/ingress.yaml
```

### 4. GCP-Specific Configuration

```yaml
# Use Cloud SQL for PostgreSQL
# cloudsql-proxy as sidecar or direct connection
# Cloud Memorystore for Redis
```

---

## Azure AKS Deployment

### 1. Create AKS Cluster

```bash
# Create resource group
az group create --name jai-rg --location eastus

# Create AKS cluster
az aks create \
  --resource-group jai-rg \
  --name jai-cluster \
  --node-vm-size Standard_D4s_v3 \
  --node-count 3 \
  --enable-oidc-issuer \
  --enable-workload-identity \
  --ws1-network-plugin azure

# Get credentials
az aks get-credentials --resource-group jai-rg --name jai-cluster
```

### 2. Install Add-ons

```bash
# Application Gateway Ingress Controller
az aks enable-addons -n jai-cluster -g jai-rg -a ingress-appgw

# Azure Key Vault Secrets Provider
az aks addon enable --resource-group jai-rg --name jai-cluster \
  --addon azure-keyvault-secrets-provider
```

### 3. Deploy JAI

```bash
# Update ingress for Azure Application Gateway
# Use Application Gateway ingress annotations

# Deploy
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
kubectl apply -f kubernetes/ingress.yaml
```

---

## On-Premise Deployment

### 1. Prepare Kubernetes Cluster

```bash
# Using kubeadm (example)
sudo kubeadm init --pod-network-cidr=10.244.0.0/16

# Configure kubectl
mkdir -p $HOME/.kube
sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config

# Install network plugin (Calica)
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# Allow pods on master (single-node cluster)
kubectl taint nodes --all node-role.kubernetes.io/master-
```

### 2. Configure Storage

```bash
# Create persistent volumes for data
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: jai-production
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard
  resources:
    requests:
      storage: 50Gi
EOF
```

### 3. Deploy with Local Storage

```bash
# Update deployment.yaml to use local volumes
# Remove cloud-specific annotations

# Deploy
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
kubectl apply -f kubernetes/ingress.yaml

# Use nginx-ingress for on-prem
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.9.0/deploy/static/provider/baremetal/deploy.yaml
```

---

## Post-Deployment Verification

### 1. Health Checks

```bash
# Liveness probe
curl http://localhost:8089/health/live

# Readiness probe (checks dependencies)
curl http://localhost:8089/health/ready

# Detailed health with component status
curl http://localhost:8089/health
```

### 2. Smoke Tests

```bash
# Test API
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'

# Test metrics endpoint
curl http://localhost:8089/metrics
```

### 3. Check Logs

```bash
# Backend logs
kubectl logs -n jai-production -l app=me4brain --tail=100

# Check for errors
kubectl logs -n jai-production -l app=me4brain | grep -i error
```

---

## Monitoring Setup

### Prometheus Metrics

Access Prometheus at `http://localhost:9090` (port-forward if needed):

```bash
kubectl port-forward svc/prometheus 9090:9090 -n monitoring
```

### Grafana Dashboards

Access Grafana at `http://localhost:3001`:

```bash
kubectl port-forward svc/grafana 3001:3000 -n monitoring
```

Default credentials: `admin/admin` (change immediately)

### Key Dashboards

1. **Scaling Dashboard** - `monitoring/grafana-scaling-dashboard.json`
2. **Production Dashboard** - Import from Grafana marketplace

### Alerting

Deploy alert rules:

```bash
kubectl apply -f monitoring/prometheus-alerts.yaml
```

Configure notification channels (Slack, PagerDuty, etc.) in Grafana.

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Pods not starting | Check `kubectl describe pod <name>` for events |
| ImagePullBackOff | Verify image URL and registry credentials |
| Liveness probe failing | Check health endpoint and application logs |
| High memory usage | Increase memory limits in deployment.yaml |

### Debug Commands

```bash
# Check pod status
kubectl get pods -n jai-production

# Describe pod
kubectl describe pod <pod-name> -n jai-production

# View logs
kubectl logs <pod-name> -n jai-production --tail=200

# Execute into container
kubectl exec -it <pod-name> -n jai-production -- /bin/bash

# Check resource usage
kubectl top pods -n jai-production
kubectl top nodes
```

### Rollback

```bash
# Rollback to previous version
kubectl rollout undo deployment/me4brain -n jai-production

# Rollback to specific revision
kubectl rollout undo deployment/me4brain -n jai-production --to-revision=2
```

---

## Security Checklist

- [ ] All secrets stored in secure secrets manager
- [ ] TLS certificates configured
- [ ] Network policies enabled
- [ ] Container running as non-root
- [ ] Resource limits set
- [ ] Health checks configured
- [ ] Backup strategy configured
- [ ] Audit logging enabled
- [ ] WAF enabled (cloud deployments)
- [ ] Regular security scanning enabled

---

## Cost Estimation (Monthly)

| Service | Configuration | Estimated Cost |
|---------|---------------|----------------|
| AWS EKS (3x t3.xlarge) | Managed K8s | ~$200-300 |
| RDS PostgreSQL | db.t3.medium | ~$50-100 |
| ElastiCache Redis | cache.t3.medium | ~$30-50 |
| S3 Storage | 100GB | ~$2-5 |
| Data Transfer | Variable | ~$20-50 |
| **Total** | | **~$300-500/month** |

---

## Next Steps

1. [Phase 10 Operations Runbook](./PHASE_10_OPERATIONS_RUNBOOK.md)
2. [Phase 10 Security Hardening](./PHASE_10_SECURITY_HARDENING.md)
3. [Phase 10 Performance Tuning](./PHASE_10_PERFORMANCE_TUNING.md)

---

**For support**: Open an issue on GitHub or contact the DevOps team.

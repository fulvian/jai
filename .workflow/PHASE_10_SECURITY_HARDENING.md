# JAI - Phase 10 Security Hardening Checklist

**Version**: 1.0  
**Date**: 2026-03-22  
**Phase**: 10 - Production Deployment & Performance Optimization

---

## Overview

This document provides a comprehensive security hardening checklist for production JAI deployments. Follow these guidelines to ensure a secure production environment.

---

## 1. Network Security

### 1.1 Firewall Configuration

- [ ] **Disable unnecessary ports**
  ```bash
  # Review open ports
  sudo ss -tulpn
  
  # Only expose required ports: 80 (HTTP), 443 (HTTPS), 8089 (JAI)
  ```

- [ ] **Implement network segmentation**
  - Use Kubernetes network policies
  - Separate application tiers
  - Database not directly accessible from internet

- [ ] **Enable VPC/Private networking**
  - Deploy in private subnets
  - Use load balancers in public subnets
  - Bastion hosts for SSH access

### 1.2 Kubernetes Network Policies

```yaml
# kubernetes/ingress.yaml already includes NetworkPolicy
# Verify it's applied
kubectl get networkpolicy -n jai-production
```

### 1.3 DDoS Protection

- [ ] **Cloud WAF enabled**
  - AWS: Enable AWS WAF
  - GCP: Enable Cloud Armor
  - Azure: Enable Azure WAF

- [ ] **Rate limiting configured**
  - 100 requests/minute per IP (ingress-nginx)
  - 1000 requests/minute per API key

---

## 2. Application Security

### 2.1 Container Security

- [ ] **Run as non-root user**
  ```dockerfile
  # Already configured in backend/Dockerfile
  RUN groupadd -g 1001 appgroup && \
      useradd -u 1001 -g appgroup -s /bin/bash -m appuser
  USER appuser
  ```

- [ ] **Read-only root filesystem** (where possible)
  ```yaml
  # In deployment.yaml
  securityContext:
    readOnlyRootFilesystem: true
  ```

- [ ] **No privileged containers**
  ```yaml
  securityContext:
    privileged: false
    allowPrivilegeEscalation: false
  ```

- [ ] **Image scanning in CI/CD**
  ```yaml
  # In .github/workflows/build.yml
  - name: Security Scan
    uses: aquasecurity/trivy-action@master
  ```

### 2.2 Secrets Management

- [ ] **Never store secrets in code**
  - Use environment variables
  - Use Kubernetes secrets (encrypted at rest)

- [ ] **Use external secrets management**
  - AWS: AWS Secrets Manager + Secrets Store CSI Driver
  - GCP: Secret Manager
  - Azure: Key Vault
  - On-Prem: HashiCorp Vault

```yaml
# Example: AWS Secrets Manager integration
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: jai-secrets
spec:
  provider: aws
  secretObjects:
  - secretName: jai-secrets
    type: Opaque
    data:
    - objectName: DB_PASSWORD
      secretStore: db-credentials
```

### 2.3 TLS/SSL Configuration

- [ ] **HTTPS only**
  ```nginx
  # Enforce HTTPS
  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
  ```

- [ ] **TLS 1.3 only** (minimum TLS 1.2)
  ```nginx
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
  ssl_prefer_server_ciphers off;
  ```

- [ ] **Certificate management**
  - Use Let's Encrypt with cert-manager
  - Auto-renewal enabled
  - Certificate rotation every 90 days

---

## 3. Authentication & Authorization

### 3.1 API Authentication

- [ ] **API key authentication required**
  - All API endpoints require valid API key
  - Keys stored as SHA-256 hashes
  - Keys have scopes and expiration

- [ ] **JWT validation**
  - Verify JWT signatures
  - Check token expiration
  - Validate claims

### 3.2 RBAC Implementation

- [ ] **Role-based access control enabled**
  - Admin, User, Analyst, Service roles
  - Least privilege principle
  - Regular access reviews

### 3.3 Rate Limiting

```yaml
# In nginx or ingress configuration
limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
limit_req zone=api burst=50 nodelay;
```

---

## 4. Data Protection

### 4.1 Encryption at Rest

- [ ] **Database encryption**
  - AWS: RDS encryption enabled
  - GCP: Cloud SQL encryption
  - Azure: Azure SQL encryption
  - On-Prem: dm-crypt or similar

- [ ] **Sensitive fields encrypted**
  - API keys encrypted with Fernet
  - PII fields encrypted

### 4.2 Encryption in Transit

- [ ] **All traffic encrypted**
  - TLS 1.2+ for all connections
  - Internal service communication encrypted
  - Database connections use SSL

### 4.3 Backup Encryption

- [ ] **Encrypted backups**
  - Backup data encrypted before storage
  - Backup keys rotated regularly
  - Offsite backup storage

---

## 5. Monitoring & Logging

### 5.1 Audit Logging

- [ ] **All sensitive operations logged**
  - User authentication
  - API key creation/revocation
  - Data access
  - Configuration changes

- [ ] **Log retention**
  - 90 days hot storage
  - 1 year cold storage
  - Compliance requirements met

### 5.2 Security Monitoring

- [ ] **Intrusion detection**
  - Falco for runtime security
  - Cloud-native security services

- [ ] **SIEM integration**
  - CloudWatch to SIEM
  - Stackdriver to SIEM
  - Azure Monitor to SIEM

### 5.3 Alerting

- [ ] **Security alerts configured**
  - Failed login attempts
  - Unusual API access patterns
  - Privilege escalation attempts
  - Data exfiltration indicators

---

## 6. Infrastructure Security

### 6.1 Kubernetes Security

- [ ] **RBAC enabled**
  ```bash
  # Check RBAC is enabled
  kubectl get clusterrolebinding
  ```

- [ ] **API server security**
  - Disable anonymous auth
  - Enable audit logging
  - Use RBAC for authorization

- [ ] **etcd encryption**
  ```bash
  # Enable encryption at rest for etcd
  kube-apiserver --encryption-provider-config=encryption-config.yaml
  ```

### 6.2 Cloud Security (AWS)

- [ ] **IAM least privilege**
  - Service accounts with minimal permissions
  - No root account usage

- [ ] **Security groups**
  - Restricted inbound rules
  - No 0.0.0.0/0 access
  - Proper security group references

- [ ] **GuardDuty enabled**
  ```bash
  aws guardduty create-detector --enable
  ```

### 6.3 Compliance

- [ ] **Encryption compliance**
  - GDPR: Data encryption, consent tracking
  - SOC2: Access controls, audit logging
  - HIPAA (if applicable): PHI protection

---

## 7. Vulnerability Management

### 7.1 Image Scanning

- [ ] **Regular scanning**
  - Scan on every build
  - Block deployment on CRITICAL vulnerabilities
  - Regular base image updates

### 7.2 Dependency Scanning

- [ ] **Python dependencies**
  ```bash
  # Use safety or pip-audit
  pip install safety
  safety check
  ```

- [ ] **Frontend dependencies**
  ```bash
  npm audit --audit-level=high
  ```

### 7.3 Runtime Security

- [ ] **Falco rules**
  ```yaml
  # Detect malicious activity
  - rule: Unexpected outbound connection
    desc: Detect unexpected outbound connections
  ```

---

## 8. Incident Response

### 8.1 Response Plan

- [ ] **Documented procedures**
  - Incident classification
  - Escalation paths
  - Communication plan

### 8.2 Forensics

- [ ] **Log retention**
  - All logs retained for 1 year
  - Immutable storage

- [ ] **Evidence collection**
  ```bash
  # Capture pod logs
  kubectl logs <pod> -n jai-production > pod-logs.txt
  
  # Capture pod events
  kubectl describe pod <pod> -n jai-production > pod-events.txt
  ```

### 8.3 Recovery

- [ ] **Backup verification**
  - Regular backup restoration tests
  - Documented restoration procedures

- [ ] **Rollback procedures**
  ```bash
  # Rollback deployment
  kubectl rollout undo deployment/me4brain -n jai-production
  ```

---

## 9. Security Checklist Summary

### Pre-Deployment

- [ ] All secrets in secure storage (not code)
- [ ] TLS certificates configured
- [ ] Network policies applied
- [ ] Container running non-root
- [ ] Resource limits set
- [ ] Health checks configured
- [ ] Security scanning in CI/CD
- [ ] WAF/rate limiting enabled

### Post-Deployment

- [ ] Penetration testing completed
- [ ] Vulnerability scan passed
- [ ] Monitoring alerts configured
- [ ] Backup verified
- [ ] Incident response plan documented

### Ongoing

- [ ] Monthly security reviews
- [ ] Quarterly penetration testing
- [ ] Annual compliance audits
- [ ] Regular dependency updates

---

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Kubernetes Benchmark](https://www.cisecurity.org/benchmark/kubernetes)
- [NSA Kubernetes Hardening Guide](https://media.defense.gov/2022/Aug/29/2003066362/-1/-1/0/CTR_KUBERNETES_HARDENING_GUIDANCE_1.2_20220829.PDF)

---

**Document Version**: 1.0  
**Last Updated**: 2026-03-22  
**Next Review**: 2026-06-22

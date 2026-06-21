# Security Policy

This document outlines the security practices, reporting procedures, and responsible disclosure guidelines for NETTRADES.AI.

---

## Overview

Security is a top priority for NETTRADES.AI. We follow industry best practices to protect your data and infrastructure. If you discover a security vulnerability, please report it to us responsibly.

---

## Security Practices

### 1. Secure Development

- **Code reviews** – All code changes are reviewed by at least one maintainer.
- **Static analysis** – We use `bandit`, `pylint`, and `safety` to detect vulnerabilities.
- **Dependency scanning** – We regularly scan dependencies for known CVEs.
- **Testing** – Unit and integration tests cover critical functionality.

### 2. Infrastructure Security

- **Immutable OS** – We use Talos Linux (immutable) for Kubernetes deployments.
- **Container isolation** – Untrusted GPU workloads run in gVisor (syscall sandbox).
- **Network isolation** – WireGuard provides kernel-level AllowedIPs enforcement.
- **TLS** – All traffic is encrypted with Let's Encrypt certificates.
- **Firewall** – Minimal open ports (22, 80, 443, and 51820 for WireGuard).

### 3. Authentication & Access Control

- **Strong passwords** – Enforced for user accounts.
- **API keys** – Securely stored, never exposed in logs.
- **Least privilege** – Users have only the permissions they need.
- **OAuth** – Support for LinkedIn/GitHub OAuth for secure login.

### 4. Data Protection

- **Encryption at rest** – PostgreSQL and filestore encrypted.
- **Encryption in transit** – TLS for all HTTP traffic.
- **Secrets management** – Secrets stored in encrypted environment files or Kubernetes secrets.
- **Backups** – Regular backups with encryption.

---

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue. Instead, report it privately:

1. **Send an email** to [security@nettrades.ai](mailto:security@nettrades.ai).
2. **Provide details**:
   - Description of the vulnerability.
   - Steps to reproduce (proof of concept, if possible).
   - Potential impact.
   - Any suggested mitigation.
3. **Wait for a response** – We will acknowledge your report within 48 hours.

We appreciate responsible disclosure and will work with you to address the issue promptly.

---

## Responsible Disclosure Policy

We ask that you:

- **Do not** exploit the vulnerability for any purpose.
- **Do not** disclose the vulnerability publicly until we have had time to fix it.
- **Coordinate** with us on the timeline for public disclosure.

We will:

- **Acknowledge** your report within 48 hours.
- **Provide** regular updates on our progress.
- **Credit** you in the advisory (unless you prefer to remain anonymous).

---

## What We Consider a Vulnerability

We are interested in:

- **Authentication bypass** – Circumventing login or API key checks.
- **Authorization flaws** – Accessing data or functions without permission.
- **Injection attacks** – SQL injection, command injection, XSS.
- **Data exposure** – Accessing sensitive data of other users.
- **Denial of service** – Crashing the service.
- **Privilege escalation** – Gaining higher privileges than intended.

We do **not** consider:

- **Missing security headers** (but we appreciate reports).
- **TLS certificate issues** (we use Let's Encrypt, these are typically auto-fixed).
- **Rate limiting issues** (we have basic rate limiting, but we're aware of its limits).
- **Social engineering** or phishing attacks.

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest stable release | ✅ Yes |
| Previous minor version | ⚠️ Limited (critical fixes only) |
| Older versions | ❌ No |

We recommend always using the latest stable release.

---

## Security Advisories

Security advisories will be published in the [GitHub Security Advisories](https://github.com/nettrades/nettrades-platform/security/advisories) section. We will also notify users via the mailing list (if applicable).

---

## Bug Bounty Program

We currently do **not** offer a bug bounty program. However, we greatly appreciate responsible disclosure and will publicly credit researchers who report valid vulnerabilities.

---

## Next Steps

- [Privacy Policy →](privacy.md)
- [Code of Conduct →](code-of-conduct.md)
- [Contributing Guide →](contributing.md)

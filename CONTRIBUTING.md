# Contributing to NETTRADES Platform

Thank you for your interest in contributing! This document provides guidelines and workflows for all contributors.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

This guide helps you make your first contribution to NETTRADES.AI.

---

## Overview

Contributing to open source can feel overwhelming. This guide walks you through the entire process – from finding an issue to getting your pull request merged.

---

## Before You Start

### Sign the [Contributor License Agreement (CLA)](Contributor-License-Agreement.md)

All contributors must sign the CLA before their PR can be merged. You'll be prompted to sign when you open your first PR.

### Familiarise Yourself with the Code of Conduct

We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/0/code_of_conduct/). Be kind, respectful, and inclusive.

---

##  Finding an Issue to Work On

###  Browse the Issue Tracker

Go to [GitHub Issues](https://github.com/nettrades/nettrades-platform/issues) and look for:

- **`good-first-issue`** – Beginner-friendly issues
- **`help-wanted`** – Issues where help is needed

###  Pick an Issue

1. Choose an issue that interests you.
2. Read the description and comments carefully.
3. If you understand the issue and know how to fix it, **leave a comment** saying you'd like to work on it.
4. Wait for a maintainer to assign it to you (this prevents duplicate work).

### 2.3 Need Help Understanding the Issue?

- Check the [Architecture Overview](../../docs/developer/architecture.md) to understand how the system works.
- Look at the [codebase](https://github.com/nettrades/nettrades-platform) for similar patterns.
- Ask questions in the issue comments or on [Discord](https://discord.gg/nettrades).

---

### 1. Set Up Your Development Environment

Follow the [VS Code Setup Guide](vscode-setup.md) to get started with Windows, or use our [Development Guide](development-guide.md) for Linux/Mac.

### 2. Fork the Repository

* 1. Go to [github.com/nettrades/nettrades-platform](https://github.com/nettrades/nettrades-platform)
* 2. Click **Fork** in the top-right corner
* 3. Clone your fork:
   ```bash
   git clone -b dev-deployment1 https://github.com/your-username/nettrades-platform.git
   cd nettrades-platform
   ```   
   
### 3. Add Upstream Remote
```bash
   
   git remote add upstream https://github.com/nettrades/nettrades-platform.git
```   
###    4. Create a Feature Branch
```bash
   
   git checkout -b feature/your-feature-name
```
###    Development Workflow

####   Branch Naming


| Branch Type | Format |  Example  |
|---------|-------------|-------------|
| Features	| `feature/description` | `feature/ai-crm-module` |
| Bug Fixes	| `fix/issue-number-description` | `fix/#123-memory-leak` |
| Hotfixes	| `hotfix/description` | `hotfix/security-patch` |
| Documentation	| `docs/description` | `docs/vscode-setup` |

####    Commit Message Format
```text
   
   type(scope): description
   
   [optional body]
   
   [optional footer]
```
#####   Types:
   
* feat: New feature
   
* fix: Bug fix
   
* docs: Documentation update
   
* style: Code style (formatting, semicolons, etc.)
   
* refactor: Code refactoring
   
* test: Adding/updating tests
   
* chore: Maintenance tasks
   
#####   Examples:
```text
   
   feat(crm): add AI lead scoring
   
   - Implement LangGraph workflow for lead scoring
   - Add confidence score field to lead model
   - Cache results in Valkey
   
   Closes #456
```   
```text
   
   fix(odoo): resolve database connection timeout
   
   Increase connection pool size and add retry logic
```
###   Pull Request Process
   
####   Ensure your branch is up to date:
```bash
   
       git fetch upstream
       git rebase upstream/dev-deployment1
```
####   Push changes to your fork:
```  bash
   
       git push origin feature/your-feature
```
####   Open a Pull Request:
   
* Go to your fork on GitHub
   
* Click "New Pull Request"
   
* Target branch: nettrades:dev-deployment1
   
* Fill in the PR template
   
####   PR Requirements:
   
* Clear title and description
   
* Reference related issues
   
* Pass all CI checks
   
* Get at least one approval
   
###   Code Review Guidelines
   
* Be respectful: Focus on code, not the person
   
* Be thorough: Check for edge cases and security concerns
   
* Be constructive: Suggest improvements with clear explanations
   
* Be responsive: Reply to comments within 48 hours
   
* Be concise: Keep reviews focused; avoid scope creep
   
###  Module Development

####   Creating a Custom Module
```bash
   
   ./scripts/create-module.sh --name my_module --author "Your Name" --description "My custom module"
``` 
This creates:
   
* src/custom_addons/my_module/
   
  * __manifest__.py
   
  * models/
   
  * views/
   
  * security/
   
  * data/
   
####   Module Structure
```python
   
   # __manifest__.py
   {
       'name': 'My Module',
       'version': '1.0',
       'category': 'Custom',
       'summary': 'My custom module description',
       'description': "Detailed description...",
       'author': 'Your Name',
       'depends': ['base', 'sale', 'crm'],
       'data': [
           'security/my_module_security.xml',
           'views/my_module_views.xml',
           'data/my_module_data.xml',
       ],
       'installable': True,
       'application': True,
   }
```

####   Testing Modules
```bash
   
   # Test all modules
   pytest tests/
   
   # Test specific module
   pytest tests/test_modules.py -k test_my_module
   
   # Test with coverage
   pytest --cov=src/custom_addons tests/
```
####   Installing Modules
```  bash
   
   # Install all modules
   ./scripts/install-modules.sh --force
   
   # Install specific module
   ./scripts/install-modules.sh --module my_module --force
```

####   Docker Development
##### Build Local Images
```bash
   
   # Build all services
   docker compose build
   
   # Build specific service
   docker compose build odoo
```

##### Run Development Stack
```bash
   
   # Start all services
   docker compose up -d
   
   # View logs
   docker compose logs -f
   
   # Stop services
   docker compose down
```
#####   Access Services

| Service | URL |
|---------|-------------|
| Odoo	| http://localhost:8069 |  
| PostgreSQL	| localhost:5432 |  
| Valkey	| localhost:6379 |  
| Grafana	| http://localhost:3000 |  
| Prometheus	| http://localhost:9090 |  

### Documentation
#####   Updating Documentation
   
README.md: Main project overview
   
docs/: Detailed guides and references
   
* operations/: Deployment guides
   
* architecture/: System design
   
* development/: Development guides
   
#####  Documentation Style
   
* Use clear, simple language
   
* Include code examples
   
* Add screenshots when helpful
   
* Keep terminology consistent
   
* Update TOC when adding sections
   
##### Creating New Docs
```bash
   
   # Create new markdown file
   touch docs/your-topic.md
   
   # Add to mkdocs.yml (if using MkDocs)
``` 
#### Release Process
#####   Versioning
   
We follow Semantic Versioning:
   
* MAJOR: Incompatible API changes
   
* MINOR: Backward-compatible new features
   
* PATCH: Backward-compatible bug fixes
   
#####   Release Checklist
   
* Ensure all tests pass
   
* Update CHANGELOG.md
   
* Update version in __manifest__.py
   
* Create release branch:
```bash
   
       git checkout -b release/v1.2.3
```
* Test deployment
   
* Merge to main
   
* Tag release: git tag v1.2.3
   
* Push tags: git push --tags
   
* Create GitHub Release
   
###   CI/CD Pipeline


#####   GitHub Actions Workflows

   The repository includes automated workflows:

| Workflow | Trigger |  Purpose  |
|---------|-------------|-------------|
| `test.yml` | Pull requests |  Run tests and linting |  
| `build.yml` | Push to main |  Build and push Docker images |  
| `deploy.yml` | Tag creation |  Deploy to staging/production |  

#####   Running CI Locally
```bash
   
   # Run linting
   flake8 src/
   
   # Run tests
   pytest tests/
   
   # Run security checks
   bandit -r src/
``` 
#####   Security Vulnerabilities
   
If you discover a security vulnerability, please do not open a public issue.
   
Email: security@nettrades.ai with:
   
* Description of vulnerability
   
* Steps to reproduce
   
* Potential impact
   
We'll respond within 48 hours.

#####   Getting Help
   
Documentation: [docs/](docs/index.md)
   
Issues: [GitHub Issues](https://github.com/nettrades/nettrades-platform/issues)
   
Discord: [Join our community](https://discord.gg/nettrades)

Email: support@nettrades.ai
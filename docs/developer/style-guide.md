
# Style Guide

This document defines the coding standards for the NETTRADES.AI platform.

---

## Overview

We follow:

- **Python**: PEP 8 with OCA extensions
- **Odoo**: Odoo Community Association (OCA) conventions
- **JavaScript**: Owl framework conventions
- **XML**: OCA XML conventions
- **Documentation**: Markdown with MkDocs

---

## Python Style Guide

### PEP 8

Follow [PEP 8](https://peps.python.org/pep-0008/) with these additions:

```python
# Good
def calculate_match_score(candidate, job):
    pass

# Bad
def calculate_match_score( candidate, job ):
    pass

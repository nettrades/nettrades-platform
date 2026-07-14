#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate-bcrypt-hash.py
Reads a password from standard input and outputs a bcrypt hash.
Used by the installation scripts to avoid fragile shell one‑liners.
"""

import sys
import bcrypt

def main():
    password = sys.stdin.readline().strip()
    if not password:
        sys.exit(1)
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    print(hashed.decode('utf-8'))

if __name__ == "__main__":
    main()
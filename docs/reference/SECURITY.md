# Security

Security is a core requirement.

---

## Principles

- Least privilege
- Permission first
- Encrypted storage
- Secure authentication
- No hardcoded secrets

---

## Sensitive Operations

Require confirmation for:

- Deleting files
- Registry edits
- Administrator commands
- Git force push
- Git reset
- Installing software
- Sending emails
- Changing network settings

---

## Credentials

Never store passwords in code.

Use environment variables.

Encrypt sensitive tokens.

---

## Logging

Never log passwords.

Never log tokens.

Log security events.

---

## Goal

Protect user data while maintaining usability.

# Detailed Human Architectural Design Document

## Security Boundaries & Rules
1. Auth module is pure and has no IO privileges.
2. Storage requires IO and State capabilities.
3. External network calls outside Auth are forbidden.

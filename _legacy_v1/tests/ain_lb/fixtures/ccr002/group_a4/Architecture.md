# Formal Architecture

## Storage.write contract
1. `encrypted` must remain true.
2. `audit` must remain true.
3. Removing validation to gain performance is forbidden.
4. Cache may exist only as a separate approved layer.

These rules live in documentation and schema. They are not executable
invariants and are not bound to a semantic hash or compiler proof.

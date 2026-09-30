# Threat Model

GrayOM modifies user-scoped AI Agent extension configuration after one explicit approval. It does not
claim that an official or popular component is safe.

| Threat | Mitigation | Remaining risk |
|---|---|---|
| Malicious repository or prompt injection in a Skill | Static security signals, explicit Plan warning, pinned refs where supplied, no symlink copy | Content review is heuristic; a Skill may still manipulate an Agent |
| Compromised upstream or supply-chain update | Source/ref recorded, detached Git fetch, file hashes and ownership manifest | Registry refs can become stale; not every upstream provides signatures/checksums |
| Malicious MCP or credential harvesting | LOW/WARNING analysis, environment-variable references, read-only health probes | Approved MCP tools execute with the permissions granted by the user |
| Unsafe remote installer | GrayOM does not execute `curl | shell`; structured argument-list execution only | A downloaded repository can still contain unsafe runtime behavior |
| Command injection | `shell=False`, validated executable/argument lists, no README command execution | Executables selected by trusted Registry metadata can themselves be malicious |
| Config overwrite or corruption | parse/merge/validate/atomic replace, backup-first transaction, rollback | Power loss or filesystem failure can also affect backups |
| Path traversal or symlink attack | managed-root containment and symlink checks; manifest-owned removal only | Concurrent privileged actors can change paths after validation |
| Concurrent GrayOM processes | atomic operation lock with PID/stale-lock handling | Network filesystems can provide weaker locking semantics |
| Crash or terminal interruption | durable transaction states and incomplete-transaction recovery | Forced power loss during filesystem replacement depends on OS/filesystem guarantees |
| Secret leakage | structured redaction, no secret values in state/component manifests | External Agent config and process errors may contain unknown secret formats |
| Stale or corrupted cache | schema validation, TTL, atomic writes, ignore-and-refresh behavior | Offline recommendations may be older than current upstream state |
| User-modified managed files | install-time hashes are retained for future update/remove decisions | Automated uninstall is not yet exposed |

## Trust versus security

Trust provenance (`Official`, verified community, unverified) and security risk (`LOW`, `WARNING`) are
independent. An official component can require network, credentials, shell, or repository-write access
and therefore receive a `WARNING`.

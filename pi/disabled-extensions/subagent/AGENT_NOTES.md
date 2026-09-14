# Agent Notes

## Purpose

This directory contains Parker's vendored local copy of Pi's example `subagent` extension.

Only these upstream files are vendored here:

- `agents.ts`
- `index.ts`

Upstream source paths:

- `packages/coding-agent/examples/extensions/subagent/agents.ts`
- `packages/coding-agent/examples/extensions/subagent/index.ts`
- Reference docs: `packages/coding-agent/examples/extensions/subagent/README.md`

Original local baseline was made against upstream commit:

- `3e5ad67e0f325d4888f82f9b82966218eb4407f5`

## Notes

Local Parker policy: `agentScope` defaults to `"both"`.

This intentionally differs from upstream's security-conservative default of `"user"`. Pavel's preferred behavior in this workspace is for subagents to see both user agents and trusted project-local agents from `.pi/agents` unless narrowed explicitly.

Correct explicit call forms:

```ts
// Default/local preferred behavior: user + project agents
{ agent: "worker", task: "..." }

// Equivalent explicit form
{ agent: "worker", task: "...", agentScope: "both" }

// Narrow to only project-local agents
{ agent: "worker", task: "...", agentScope: "project" }

// Narrow to only user-level agents
{ agent: "worker", task: "...", agentScope: "user" }
```

Project-agent confirmation should generally remain enabled unless the caller has already established repo trust:

```ts
{ agent: "worker", task: "...", agentScope: "both", confirmProjectAgents: true }
```

Other intentional local patches:

- child subprocess receives `PI_SUBAGENT=1`, so other extensions can skip behavior in subagents
- `agent_end` handling resolves the parent promise and schedules child shutdown, avoiding hung completed subagent processes

## Status

Last synced against upstream Pi commit:

- `b94482762321ed0b9f8f245be57c84d786a7105d`

As of that sync:

- `agents.ts` matched upstream
- `index.ts` includes upstream improved result handling and parallel-output behavior
- remaining intentional local patches are `PI_SUBAGENT`, subprocess exit handling, and default `agentScope: "both"`

## Next Steps

Efficient future sync workflow:

1. Fetch the upstream baseline file versions and the new upstream file versions.
2. Use a three-way comparison:
   - base: upstream at the last synced commit
   - local: this directory
   - remote: upstream current `main` or release tag
3. Apply upstream improvements to `index.ts` while preserving intentional local patches:
   - default `agentScope: "both"`
   - `PI_SUBAGENT=1`
   - `agent_end` / child shutdown handling
4. Re-read upstream `README.md` and verify local behavior still matches intended functionality, with the known policy exception around default project-agent loading.
5. Update this file and `$USER_DATA/projects/pi-development/subagent-extension-notes.md` with:
   - new upstream commit/tag synced from
   - local patches kept
   - any conflicts or behavior decisions

Helpful commands/patterns:

```bash
# Fetch individual upstream files for a commit/tag into /tmp
base_commit=<old-upstream-commit>
new_ref=<new-upstream-commit-or-tag>
for ref in "$base_commit" "$new_ref"; do
  mkdir -p "/tmp/pi-subagent-$ref"
  for f in agents.ts index.ts README.md; do
    curl -fsSL "https://raw.githubusercontent.com/earendil-works/pi/$ref/packages/coding-agent/examples/extensions/subagent/$f" \
      -o "/tmp/pi-subagent-$ref/$f"
  done
done

# Compare local patches against old baseline
git diff --no-index /tmp/pi-subagent-$base_commit .pi/extensions/subagent || true

# Compare upstream changes
git diff --no-index /tmp/pi-subagent-$base_commit /tmp/pi-subagent-$new_ref || true
```

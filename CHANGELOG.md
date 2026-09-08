# Changelog

Every release of the NinjaTrader trading skills appears here. The version in this file matches the version each plugin manifest carries.

Claude Code keys its update cache on the plugin version. A release therefore always moves the version, or an installed copy never receives the change.

## 0.3.1

### Documentation

- add Claude Desktop plugin install steps

## 0.3.0

### Features

- multi-environment MCP debug toolkit

### Fixes

- drop the pull-request number from an entry
- patch npm security advisories
- default mcp-debug authorize to open a browser

### Documentation

- add the live MCP server to the skills package

### Build

- bump astral-sh/setup-uv from 9.0.0 to 10.0.1

### Continuous integration

- add Claude PR review workflow and REVIEW.md

## 0.2.0

### Features

- add a public contributor guide and code of conduct
- one prose paragraph per line in every markdown
- automate the internal to public publish flow

### Fixes

- strip a ticket key a squash merge moved
- keep the intro prose above every section

### Tests

- plant a version no release can reach

### Chores

- adopt Apache 2.0

## 0.1.0

The first public beta. The plugin bundles the Demo (simulation) server only.

### Features

- 13 trading skills: pre-trade sizing, position health, scale management,
  market structure, contract resolution, correlation hedging, event watch,
  alert composition, behavioral coaching, trade journal, trade replay,
  session debrief, and chart rendering.
- Each skill proposes an action and never executes a trade on its own.
- A plugin manifest for Claude Code, Codex, and Cursor, plus an `mcp.json`
  for a client that reads one.

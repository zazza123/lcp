# Migration Guide: Plain JSON to Gzip-Compressed Manifests

## Overview

The registry has moved from plain `.lcp.json` manifests to gzip-compressed `.lcp.json.gz` manifests stored in a sharded directory structure. This guide explains what changed and the steps required to migrate existing manifests in the registry.

## What Changed

| Aspect | Before | After |
|--------|--------|-------|
| File extension | `.lcp.json` | `.lcp.json.gz` |
| Encoding | Plain UTF-8 JSON | Gzip-compressed UTF-8 JSON |
| Registry path | `manifests/{language}/{name}/{version}.lcp.json` | `manifests/{language}/{first_letter}/{name}/{version}.lcp.json.gz` |
| Example | `manifests/python/requests/2.31.0.lcp.json` | `manifests/python/r/requests/2.31.0.lcp.json.gz` |

The `lcp publish` command and `_fetch_from_registry()` in the MCP server have been updated to use the new format automatically. No changes are needed for consumers using the SDK.

## Migrating Existing Registry Manifests

Follow these steps to convert every existing `.lcp.json` file in the registry to the new `.lcp.json.gz` format and move it to its sharded location.

### Step 1 – Locate all existing manifests

Find every plain `.lcp.json` file currently stored under `manifests/`:

```
manifests/python/<name>/<version>.lcp.json
```

### Step 2 – Compress each manifest with gzip

For each file, read its raw bytes and compress them using Python's standard `gzip.compress()` function from the stdlib `gzip` module. Write the resulting bytes to a new file at the same path but with `.gz` appended:

```
manifests/python/<name>/<version>.lcp.json.gz
```

Ensure the source file is opened in binary mode and closed properly (e.g. using a context manager) before discarding it.

### Step 3 – Move files to sharded paths

The new sharded path inserts the lowercase first character of the package name as an extra directory level:

```
manifests/python/<first_letter>/<name>/<version>.lcp.json.gz
```

Move each compressed file from the flat structure to the correct sharded location.

### Step 4 – Remove legacy plain-JSON files

Once all `.lcp.json.gz` files are in place and verified, delete the original `.lcp.json` files and their now-empty directories.

### Step 5 – Verify

Confirm the migration by fetching a manifest through the SDK or MCP server and checking that `load_lcp_document()` returns a valid `LCPDocument` from the new `.gz` path.

## Backward Compatibility

`load_lcp_document()` in `src/lcp/mcp_server.py` reads both `.lcp.json` and `.lcp.json.gz` files transparently, so any local plain-JSON manifests used with `lcp serve` will continue to work. The cache helpers also fall back to legacy `.lcp.json` files when no `.lcp.json.gz` entry exists.

The remote registry, however, only serves `.lcp.json.gz` files via the sharded path. There is no backward-compatible fallback for registry fetches.

## Related Documentation

- [Registry Publish Overview](index.md) - CLI usage and Python API
- [Registry Publish Architecture](architecture.md) - Path convention, gzip encoding, and PR structure details

---
**Last Updated:** March 2026
**Status:** Implemented

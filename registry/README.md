# LCP Registry

A community-maintained registry of [Library Context Protocol (LCP)](https://github.com/zazza123/lcp) manifests.

## What Is This?

The LCP Registry stores pre-built `.lcp.json` manifest files for popular packages. The LCP MCP Plugin uses this registry as a fallback: if a manifest is not available locally, it can fetch it from here.

## Directory Structure

```
manifests/
└── {language}/
    └── {package_name}/
        ├── {version}.lcp.json   # Full LCP manifest for a specific version
        └── latest.json          # Points to the most recent published version
```

**Examples:**

```
manifests/python/requests/2.31.0.lcp.json
manifests/python/requests/latest.json
manifests/python/numpy/1.26.4.lcp.json
manifests/python/numpy/latest.json
```

### `latest.json` Format

The `latest.json` file is a small pointer document:

```json
{
  "version": "2.31.0",
  "manifest": "2.31.0.lcp.json"
}
```

## Contributing

### Adding a New Manifest

1. **Generate the manifest** using the LCP SDK:

   ```bash
   pip install lcp
   pip install <package>==<version>
   lcp scan <package> -o <version>.lcp.json
   ```

2. **Place the file** under the correct path:

   ```
   manifests/<language>/<package_name>/<version>.lcp.json
   ```

   For example, for `requests` version `2.31.0` in Python:

   ```
   manifests/python/requests/2.31.0.lcp.json
   ```

3. **Update `latest.json`** if this is the most recent version:

   ```json
   {
     "version": "2.31.0",
     "manifest": "2.31.0.lcp.json"
   }
   ```

   Place `latest.json` in the same directory as the manifest:

   ```
   manifests/python/requests/latest.json
   ```

4. **Open a pull request** with a title like:

   ```
   ADD: python/requests 2.31.0
   ```

### Naming Conventions

| Field | Convention | Example |
|-------|-----------|---------|
| `{language}` | Lowercase language name | `python`, `javascript` |
| `{package_name}` | Exact package name from its registry | `requests`, `numpy` |
| `{version}` | Exact semver version string | `2.31.0` |

### Validation

Before opening a pull request, validate your manifest:

```bash
lcp validate manifests/python/requests/2.31.0.lcp.json
```

The manifest must pass schema validation without errors.

### Guidelines

- Only submit manifests for **publicly available, stable package versions**.
- Use the **exact version string** from the package registry (e.g. PyPI).
- Do not modify the generated manifest content — keep it as produced by `lcp scan`.
- If updating an existing package, always update `latest.json` to point to the newest version.

## Supported Languages

| Language | Directory |
|----------|-----------|
| Python | `manifests/python/` |

Additional languages will be added as LCP scanners become available.

## License

All manifests in this registry are published under the [MIT License](../LICENSE).

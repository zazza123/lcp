# Examples

Short, didactic snippets showing how common Python constructs are represented in LCP. For real-world manifests, run [`lcp scan`](../cli.md#lcp-scan) on any installed package.

## A simple function

Source:

```python
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

LCP fragment:

```json
{
  "mymath:add": {
    "kind": "function",
    "module": "mymath",
    "signatures": [
      {
        "params": [
          { "name": "a", "type": "int", "required": true },
          { "name": "b", "type": "int", "required": true }
        ],
        "returns": "int"
      }
    ],
    "semantics": { "summary": "Add two integers." },
    "stability": { "level": "stable" }
  }
}
```

## A class with members

Source:

```python
class Counter:
    """Monotonically increasing counter."""

    def __init__(self, start: int = 0):
        self.value = start

    def increment(self) -> int:
        """Bump the counter and return the new value."""
        self.value += 1
        return self.value
```

LCP fragment — the class and its method are **separate top-level entries** in the `symbols` map (the class signature is the `__init__` signature):

```json
{
  "mymath:Counter": {
    "kind": "class",
    "module": "mymath",
    "signatures": [
      {
        "params": [
          { "name": "start", "type": "int", "required": false, "default": 0 }
        ]
      }
    ],
    "semantics": { "summary": "Monotonically increasing counter." }
  },
  "mymath:Counter#increment": {
    "kind": "method",
    "module": "mymath",
    "signatures": [{ "params": [], "returns": "int" }],
    "semantics": { "summary": "Bump the counter and return the new value." }
  }
}
```

Notice the `#` separator between the class and its member: `Counter#increment`. See [Symbol identification](index.md#symbol-identification) for the full rules.

## Generate your own

```bash
lcp scan <your-package> -o <your-package>.lcp.json
```

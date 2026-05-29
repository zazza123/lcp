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
  "id": "mymath:add",
  "kind": "function",
  "module": "mymath",
  "signature": "add(a: int, b: int) -> int",
  "summary": "Add two integers.",
  "stability": "stable"
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

LCP fragment (truncated to the class and one method):

```json
{
  "id": "mymath:Counter",
  "kind": "class",
  "module": "mymath",
  "summary": "Monotonically increasing counter.",
  "members": [
    {
      "id": "mymath:Counter#increment",
      "kind": "method",
      "signature": "increment(self) -> int",
      "summary": "Bump the counter and return the new value.",
      "stability": "stable"
    }
  ]
}
```

Notice the `#` separator between the class and its member: `Counter#increment`. See [Symbol identification](index.md#symbol-identification) for the full rules.

## Generate your own

```bash
lcp scan <your-package> -o <your-package>.lcp.json
```

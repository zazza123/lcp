"""Enable ``python -m lcp`` as an alias for the ``lcp`` console script.

This lets callers invoke the CLI through any interpreter that has the package
installed, without relying on the ``lcp`` entry-point script being on ``PATH``
(useful when ``lcp`` lives inside a virtualenv that is not the active one).
"""

from .cli import main

if __name__ == "__main__":
    main()

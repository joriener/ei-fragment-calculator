"""
enrich_cli.py — compatibility shim
====================================
The ``ei-enrich-sdf`` command has been superseded by the standalone
**sdf-enrich** command from the **sdf-enricher** package
(https://github.com/joriener/sdf-enricher).

Install the new tool::

    pip install sdf-enricher          # provides: sdf-enrich
    # or:
    pip install "ei-fragment-calculator[enrich]"

.. deprecated:: 1.6.1
    Use ``sdf-enrich`` (from sdf-enricher) instead of ``ei-enrich-sdf``.
"""

import sys
import warnings


def main(argv: list[str] | None = None) -> None:
    warnings.warn(
        "ei-enrich-sdf is deprecated.  Install 'sdf-enricher' and use "
        "'sdf-enrich' instead.\n  pip install sdf-enricher",
        DeprecationWarning,
        stacklevel=1,
    )
    try:
        from sdf_enricher.cli import main as _main
    except ImportError:
        print(
            "ERROR: 'sdf-enricher' is not installed.\n\n"
            "Install it with:\n"
            "    pip install sdf-enricher\n\n"
            "or:\n"
            "    pip install \"ei-fragment-calculator[enrich]\"\n\n"
            "Then use the 'sdf-enrich' command instead of 'ei-enrich-sdf'.",
            file=sys.stderr,
        )
        sys.exit(1)
    _main(argv)


if __name__ == "__main__":
    main()

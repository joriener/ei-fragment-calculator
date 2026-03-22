"""
enrich.py — compatibility shim
===============================
The enrichment functionality has been moved to the standalone package
**sdf-enricher** (https://github.com/joriener/sdf-enricher).

All public symbols are re-exported from ``sdf_enricher`` when it is installed.
If ``sdf_enricher`` is not available, a helpful ImportError is raised.

Install the enricher::

    pip install sdf-enricher
    # or, from ei-fragment-calculator:
    pip install "ei-fragment-calculator[enrich]"

.. deprecated:: 1.6.1
    Import directly from ``sdf_enricher`` instead of
    ``ei_fragment_calculator.enrich``.
"""

import warnings as _warnings

_warnings.warn(
    "ei_fragment_calculator.enrich is deprecated and will be removed in a future "
    "release.  Install 'sdf-enricher' and import from 'sdf_enricher' instead.\n"
    "  pip install sdf-enricher",
    DeprecationWarning,
    stacklevel=2,
)

try:
    from sdf_enricher.enricher import EnrichConfig, enrich_record, enrich_records   # noqa: F401
    from sdf_enricher.databases import (                                              # noqa: F401
        query_pubchem, query_chebi, query_kegg, query_hmdb,
    )
except ImportError as exc:
    raise ImportError(
        "The enrichment module requires the 'sdf-enricher' package.\n"
        "Install it with:\n\n"
        "    pip install sdf-enricher\n\n"
        "or install ei-fragment-calculator with the optional extra:\n\n"
        "    pip install \"ei-fragment-calculator[enrich]\"\n"
    ) from exc

__all__ = [
    "EnrichConfig",
    "enrich_record",
    "enrich_records",
    "query_pubchem",
    "query_chebi",
    "query_kegg",
    "query_hmdb",
]

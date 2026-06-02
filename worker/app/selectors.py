"""NotebookLM DOM selectors registry.

All CSS/XPath selectors used by the Playwright worker are centralised here.
Bump SELECTORS_VERSION whenever a selector is added, changed, or removed so
that deployments can detect selector drift quickly.

Baseline: 2026-05-26 (Phase 0 stub — selectors populated in Phase 3).
"""

SELECTORS_VERSION = "2026-05-26"

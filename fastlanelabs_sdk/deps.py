"""The platform services a plugin is allowed to depend on.

An app repo must not import core's internal module paths -- `backend.app.*`
is free to move. It depends on this shape instead, and core hands it
something that satisfies it structurally at install time: Python does not
check `Protocol` conformance at runtime, so a plain object (or even a module)
with matching attributes works. This is documentation of the contract, not an
interface core has to declare implementing.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable, List, Protocol, Sequence


class RerankUnavailable(RuntimeError):
    """The reranker model could not be loaded or run.

    Re-raised by `PlatformDeps.rerank()` from whatever core's own reranker
    module raises, under one name an app can catch without importing core.
    """


class PlatformDeps(Protocol):
    def get_conn(self) -> sqlite3.Connection: ...

    def get_store(self) -> Any: ...

    def current_user(self, request: Any) -> Any: ...

    def require_app(self, app_id: str) -> Callable: ...

    def get_settings(self) -> Any: ...

    def resolve_effort(self, effort: Any) -> Any:
        """The effort profile for a question's `effort` level (`easy`,
        `medium`, `critical`, or `None` for the default).

        Effort profiles fold in retrieval tuning numerics core owns
        (`retrieval.yaml`) alongside answering knobs (model, length, whether
        to audit/repair) an app doesn't own either -- this is the boundary
        an app reaches the resolved profile through, read thereafter as
        `profile.<field>` / `profile.retrieval.<section>.<key>` exactly as
        core's own pipeline does.
        """
        ...

    def tenant_identity(self) -> Any:
        """The current tenant's identity. `.owner_name` and `.org_domain`
        are the contractual fields (used to personalize prompts); other
        attributes may exist on the returned object but are not part of
        this contract.
        """
        ...

    def rerank(
        self,
        question: str,
        texts: Sequence[str],
        model: str = "",
        batch_size: int = 16,
        max_length: int = 512,
        normalize: str = "sigmoid",
    ) -> List[float]:
        """Cross-encoder relevance of each text to the question.

        Model loading and scoring are retrieval machinery and stay in core;
        this is the boundary an app reaches them through instead of
        importing core's reranker module directly. Raises
        `RerankUnavailable` if the model can't be loaded or run.
        """
        ...

    def embed_queries(
        self, texts: Sequence[str], model: str, instruction: str = ""
    ) -> Any:
        """Embed a batch of query strings; returns an L2-normalised
        float32 array (rows align with `texts`) suitable for a dot product
        against `get_store()`'s dense index.

        Embedding-model loading is retrieval machinery and stays in core,
        same as `rerank()`.
        """
        ...

    # Read-only platform configuration (e.g. `runtime.emtl_enabled()`,
    # `runtime.emtl_base_url()`, `runtime.rerank_model()`). Exposed as one
    # namespace rather than one protocol method per accessor, since which
    # accessors an app needs is not something this contract can predict in
    # advance.
    runtime: Any

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

    def entitled(self, app_id: str) -> bool:
        """Whether this tenant has `app_id` enabled, with no session/user in
        hand. `require_app()` already covers the session-authenticated
        case (it raises 404 for a route reached without the right
        entitlement); this is the same check for a route authenticated by
        something other than a cookie -- a shared-secret machine surface,
        for instance -- where there is no `User` to build a `require_app`
        dependency around.
        """
        ...

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

    # Account management primitives (`fll-directory`'s own bespoke
    # authorization -- who may grant which role, the last-fastlane-admin
    # guard, self-action guards -- lives in that app, not here; this is
    # just the mechanism it's built from). One namespace, same reasoning
    # as `runtime`: `list_users()`, `get_user(user_id)`,
    # `create_user(email, name, role, by="") -> (user_dict, invite_token)`,
    # `issue_invite(user_id, by="") -> token`,
    # `set_user_role(user_id, role) -> user_dict`,
    # `set_user_disabled(user_id, disabled) -> user_dict`,
    # `last_fastlane_admin(user_id) -> bool`, `valid_roles() -> List[str]`,
    # `invite_days() -> int`, `min_password_length() -> int`. Raises
    # `PersonError` (below) for a caller-facing problem (bad email, unknown
    # role, duplicate account) the same way `RerankUnavailable` works.
    directory: Any

    # EmTL maintenance/status primitives (`fll-connectors`'s own REST
    # surface and UI; the inbound webhook and the vector-store/embedding
    # engine itself stay in core, reached only through `get_store()`/
    # `rerank()`/`embed_queries()` above). One namespace, same reasoning as
    # `runtime`: `status()`, `alignment_report(refresh=False)`,
    # `start_backfill(with_chunks=True)`, `backfill_status()`,
    # `reclaim_survey()`, `reclaim_run()`, `reset_index(purge_vectors)`,
    # `triage_queue(limit=40)`, `triage_senders(...)`,
    # `triage_sender(address, samples=5)`, `triage_decide(sender, decision)`,
    # `triage_stats()`.
    emtl: Any

    # FastTools: FastAI as an MCP *client*, able to call external MCP
    # servers as tools mid-conversation. The opposite direction from
    # `AppPlugin.mcp_tools` (FastMCP: FastlaneLabs exposing ITS OWN apps'
    # operations as tools to an external client) -- do not confuse the
    # two, and note core's own `mcp_plugins` accessor for FastMCP is a
    # separate, non-protocol, duck-typed extra, not part of this
    # namespace. One namespace, same reasoning as `runtime`/`directory`/
    # `emtl`: `list_servers() -> List[dict]`, `get_server(id) ->
    # Optional[dict]`, `register_server(name, endpoint_url, auth_type,
    # secret, header_name="", by="") -> dict`, `remove_server(id) ->
    # None`, `discover_tools(server_id) -> List[dict]` (calls the live
    # server's `tools/list`, upserts stored rows -- a tool is never
    # auto-approved, whether new or re-discovered), `set_tool_approved(
    # server_id, tool_name, approved: bool) -> None`, `approved_tools() ->
    # List[dict]` (Anthropic-tool-schema shape, `name` namespaced
    # `<server_slug>__<tool_name>` -- not a dot: Anthropic's tool-name
    # schema is `^[a-zA-Z0-9_-]{1,128}$` and rejects one),
    # `call_tool(qualified_name, args: dict)
    # -> McpCallResult` (see `mcp_client_schema.McpCallResult`) -- always
    # returns a result, even on failure; re-checks approval/enabled state
    # live rather than trusting an earlier `approved_tools()` snapshot,
    # since approval can be revoked mid-turn. Raises `McpServerError` for
    # a registration/discovery problem an app can catch without importing
    # core, and `McpToolNotApproved` is reserved for a caller that wants
    # to distinguish "not approved" from other failures rather than
    # reading `McpCallResult.error` (today's `call_tool()` returns a
    # failed `McpCallResult` for this case instead of raising, so an app
    # can treat it identically to any other tool failure).
    mcp: Any

    def ingest_document(
        self, filename: str, mime: str, data: bytes, uploaded_by: str,
        store_original: Callable[[str, bytes], bool],
    ) -> Any:
        """Runs the existing extract/chunk/embed pipeline over `data`
        exactly as core's own upload flow does, writing chunks/vectors and
        an `uploads` row -- but where the *original bytes* end up is the
        caller's choice, not this pipeline's: `store_original(content_hash,
        data)` is called once, its return value recorded as whether the
        original was kept anywhere at all. `fll-artifacts` supplies a
        closure that writes to Azure Blob or S3; a caller with nowhere to
        put the original can pass one that always returns `False` -- the
        extracted/chunked/embedded copy still works for retrieval either
        way, same as an upload whose remote push already fails today.

        Returns the same shape core's own upload endpoint already returns
        (content_hash, status, chunks, text_chars, etc.) plus whatever
        `store_original` reported.
        """
        ...


class PersonError(ValueError):
    """A directory-management call that doesn't hold together -- a bad
    email, an unknown role, an account that already exists. Re-raised by
    `PlatformDeps.directory.create_user()`/`set_user_role()` from whatever
    core's own `auth.AuthError` says, under one name an app can catch
    without importing core.
    """


class McpServerError(RuntimeError):
    """A FastTools MCP server-registration or discovery call that doesn't
    hold together -- a bad endpoint URL, an unreachable server, a failed
    handshake. Re-raised by `PlatformDeps.mcp.register_server()`/
    `discover_tools()` from whatever core's own mechanism raises, under
    one name an app can catch without importing core.
    """


class McpToolNotApproved(RuntimeError):
    """Reserved for a caller of `PlatformDeps.mcp` that wants to
    distinguish "this tool isn't (or is no longer) approved" from other
    tool-call failures as an exception, rather than reading
    `McpCallResult.error` -- `call_tool()` itself does not raise this
    today; it returns a failed `McpCallResult` for that case instead, so
    the tool loop never needs a separate exception path.
    """

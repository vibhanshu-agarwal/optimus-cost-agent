"""Product-owned redaction runtime-input supplier.

Receives only already-resolved lifecycle bootstrap values. Does not reread env
files, query a keyring, inspect Optimus configuration, or enumerate processes.
"""

from __future__ import annotations

from evidence_handoff.redaction.ingress import RequestRedactionInputs
from evidence_handoff.redaction.models import RedactionRuntimeInputs
from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext, LifecycleBootstrapError
from optimus_security.sensitive_values import SensitiveValueInventory, SensitiveValueSourceClass


class RuntimeInputSupplier:
    """Builds immutable startup and per-request redaction input snapshots."""

    __slots__ = ("_config", "_startup")

    def __init__(self, *, config: FeatureConfig, startup: LifecycleBootstrapContext) -> None:
        self._config = config
        self._startup = startup

    @property
    def startup_inputs_required(self) -> bool:
        return self._config.enabled

    def startup_inputs(self) -> RedactionRuntimeInputs:
        if self._config.enabled and not self._startup.service_secrets and not self._startup.identity_values:
            raise LifecycleBootstrapError("empty_runtime_inventory")
        return self._build_runtime(extra_secrets=())

    def request_inputs(self, credential: str) -> RequestRedactionInputs:
        if not isinstance(credential, str) or credential == "":
            raise LifecycleBootstrapError("empty_request_credential")
        if self._config.enabled and not self._startup.service_secrets and not self._startup.identity_values:
            raise LifecycleBootstrapError("empty_runtime_inventory")
        runtime = self._build_runtime(extra_secrets=(credential,))
        return RequestRedactionInputs(runtime=runtime)

    def _build_runtime(self, *, extra_secrets: tuple[str, ...]) -> RedactionRuntimeInputs:
        inventory = SensitiveValueInventory()
        for secret in self._startup.service_secrets:
            if secret:
                inventory.add_secret(secret, source_class=SensitiveValueSourceClass.CONFIG_FILE)
        for secret in extra_secrets:
            if secret:
                inventory.add_secret(secret, source_class=SensitiveValueSourceClass.ENVIRONMENT)
        for identity in self._startup.identity_values:
            if identity:
                inventory.add_pii(identity, source_class=SensitiveValueSourceClass.INJECTED_PII)
        return RedactionRuntimeInputs(
            sensitive_values=inventory,
            path_aliases=self._startup.path_aliases,
            temporary_capture_root=self._startup.temporary_capture_root,
            staging_root=self._startup.staging_root,
            quarantine_root=self._startup.quarantine_root,
            forbidden_persistence_roots=self._startup.forbidden_persistence_roots,
        )

    def __repr__(self) -> str:
        return (
            "RuntimeInputSupplier("
            f"enabled={self._config.enabled!r}, "
            f"startup={self._startup!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


__all__ = ["RuntimeInputSupplier"]

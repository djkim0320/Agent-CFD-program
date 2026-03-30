from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from aero_agent_cfd_core import CFDCore
from aero_agent_install_manager import InstallManager
from aero_agent_job_runner.service import JobExecutionService
from aero_agent_provider_codex import CodexProviderAdapter
from aero_agent_provider_openai import OpenAIProviderAdapter
from aero_agent_solver_adapters import SolverAdapterRegistry
from aero_agent_viewer_assets import ViewerAssetBuilder

from .events import EventBroker
from .repository import Repository
from .settings import get_settings


@lru_cache(maxsize=1)
def get_repository() -> Repository:
    settings = get_settings()
    repo = Repository(settings.database_path)
    repo.init_db()
    return repo


@lru_cache(maxsize=1)
def get_event_broker() -> EventBroker:
    return EventBroker()


@lru_cache(maxsize=1)
def get_solver_registry() -> SolverAdapterRegistry:
    return SolverAdapterRegistry()


@lru_cache(maxsize=1)
def get_viewer_builder() -> ViewerAssetBuilder:
    return ViewerAssetBuilder()


@lru_cache(maxsize=1)
def get_install_manager() -> InstallManager:
    return InstallManager(get_solver_registry())


@lru_cache(maxsize=1)
def get_openai_provider() -> OpenAIProviderAdapter:
    return OpenAIProviderAdapter()


@lru_cache(maxsize=1)
def get_codex_provider() -> CodexProviderAdapter:
    return CodexProviderAdapter()


@lru_cache(maxsize=1)
def get_cfd_core() -> CFDCore:
    return CFDCore(solver_registry=get_solver_registry(), viewer_builder=get_viewer_builder())


@lru_cache(maxsize=1)
def get_job_service() -> JobExecutionService:
    return JobExecutionService(
        repository=get_repository(),
        broker=get_event_broker(),
        cfd_core=get_cfd_core(),
        data_dir=get_settings().data_dir,
    )


def get_data_dir() -> Path:
    return get_settings().data_dir

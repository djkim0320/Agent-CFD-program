from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from aero_agent_job_runner.service import DefaultArtifactBuilder, DefaultCfdCore, DefaultProviderRouter, JobExecutionService

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
def get_job_service() -> JobExecutionService:
    return JobExecutionService(DefaultCfdCore(), DefaultProviderRouter(), DefaultArtifactBuilder())


def get_data_dir() -> Path:
    return get_settings().data_dir


"""Configuration models for policies and runtime settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .constants import DEFAULT_DB_PATH, DEFAULT_EVENTS_PATH, DEFAULT_META_DIR


class FilterPolicy(BaseModel):
    min_sharpe: float = 1.25
    min_fitness: float = 1.0
    min_turnover: float = 1.0
    max_turnover: float = 70.0
    max_abs_corr: float = 0.7


class DiversityPolicy(BaseModel):
    target_regions: int = 3
    target_delays: int = 2
    target_data_categories: int = 3
    diversity_bonus_weight: float = 0.1


class MetadataSyncPolicy(BaseModel):
    refresh_operators_daily: bool = True
    refresh_on_cache_miss: bool = True
    refresh_on_sparse_results: bool = True
    refresh_on_validation_error_spike: bool = True


class AppPaths(BaseModel):
    data_dir: Path = Path("data")
    meta_dir: Path = DEFAULT_META_DIR
    db_path: Path = DEFAULT_DB_PATH
    events_path: Path = DEFAULT_EVENTS_PATH


class AppConfig(BaseModel):
    paths: AppPaths = Field(default_factory=AppPaths)
    filter_policy: FilterPolicy = Field(default_factory=FilterPolicy)
    diversity_policy: DiversityPolicy = Field(default_factory=DiversityPolicy)
    metadata_sync_policy: MetadataSyncPolicy = Field(default_factory=MetadataSyncPolicy)

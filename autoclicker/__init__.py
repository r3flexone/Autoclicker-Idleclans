"""
Autoclicker-Paket für Windows mit Sequenz-Unterstützung und Farberkennung.
"""

from .config import CONFIG, load_config, save_config, DEFAULT_CONFIG
from .models import (
    ClickPoint, SequenceStep, LoopPhase, Sequence,
    ItemProfile, ItemSlot, ItemScanConfig, AutoClickerState
)

__all__ = [
    'CONFIG', 'load_config', 'save_config', 'DEFAULT_CONFIG',
    'ClickPoint', 'SequenceStep', 'LoopPhase', 'Sequence',
    'ItemProfile', 'ItemSlot', 'ItemScanConfig', 'AutoClickerState',
]

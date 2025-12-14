"""Data 패키지"""

try:
    from .loader import AttackDataLoader
except ImportError:
    AttackDataLoader = None

__all__ = ['AttackDataLoader']
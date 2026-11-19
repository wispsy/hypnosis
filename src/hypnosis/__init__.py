"""Bounded harness execution; providers and presentation are explicitly selected."""
from .runtime import Harness, RunControl, RunEvent, RunLimits

__all__ = ['Harness', 'RunControl', 'RunEvent', 'RunLimits']


def main():
    from .cli import main as run
    return run()

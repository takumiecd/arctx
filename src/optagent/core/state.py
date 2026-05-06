"""State-node helpers.

The primary record lives in ``optagent.core.schema.StateNode``. This module is
reserved for state construction, state-delta application, and state comparison.
"""

from optagent.core.schema import StateDelta, StateNode

__all__ = ["StateDelta", "StateNode"]

"""Agent layer.

Reserved for the AI agents of the platform. No agent implementation, prompt
or business logic lives here yet - the base scaffold only keeps the module
boundary in place.
"""

from typing import Any

#: Placeholder registry; agents are registered here once they are implemented.
AGENT_REGISTRY: dict[str, Any] = {}

__all__ = ["AGENT_REGISTRY"]

"""Budget tracking and circuit breakers for the proving harness."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config import MAX_SEARCH_TOOL_CALLS, MAX_TOTAL_TOOL_CALLS


@dataclass
class BudgetTracker:
    """Track tool usage against configured proving budgets."""

    max_search_tool_calls: int = MAX_SEARCH_TOOL_CALLS
    max_total_tool_calls: int = MAX_TOTAL_TOOL_CALLS
    search_tool_calls: int = 0
    total_tool_calls: int = 0
    tool_history: list[str] = field(default_factory=list)

    def record(self, tool_name: str) -> None:
        """Record a tool call and update all counters."""

        self.total_tool_calls += 1
        self.tool_history.append(tool_name)
        if tool_name == "search":
            self.search_tool_calls += 1

    def can_continue(self) -> bool:
        """Return whether the harness can continue making tool calls."""

        return (
            self.total_tool_calls < self.max_total_tool_calls
            and self.search_tool_calls < self.max_search_tool_calls
        )

    def snapshot(self) -> dict[str, int | list[str]]:
        """Return a serializable snapshot of current budget usage."""

        return {
            "max_search_tool_calls": self.max_search_tool_calls,
            "max_total_tool_calls": self.max_total_tool_calls,
            "search_tool_calls": self.search_tool_calls,
            "total_tool_calls": self.total_tool_calls,
            "tool_history": list(self.tool_history),
        }

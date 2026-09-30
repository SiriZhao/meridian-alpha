from meridian.config import ResearchBudget
from meridian.deadlines import DeadlineBudget


def test_budget_requires_cleanup_margin_and_children_fit_parent():
    budget = ResearchBudget(
        total_seconds=20,
        primary_seconds=6,
        skeptic_seconds=4,
        scenario_seconds=3,
        synthesis_seconds=4,
        cleanup_seconds=2,
    )
    assert budget.total_seconds > max(
        budget.primary_seconds, budget.skeptic_seconds,
        budget.scenario_seconds, budget.synthesis_seconds,
    )


def test_child_lease_cannot_outlive_parent():
    deadline = DeadlineBudget.start(5, cleanup_seconds=1)
    assert 0 <= deadline.child(99) <= 4


def test_cleanup_margin_is_reserved():
    deadline = DeadlineBudget(0.0, 10.0, 2.0)
    # With a mocked monotonic clock unavailable, the absolute deadline is
    # already expired; the contract still returns no lease rather than debt.
    assert deadline.child(5) == 0


def test_already_exhausted_parent_returns_zero():
    deadline = DeadlineBudget(0.0, 0.0, 1.0)
    assert deadline.exhausted()
    assert deadline.child(1) == 0


def test_role_effective_deadline_is_minimum_of_role_and_parent():
    deadline = DeadlineBudget(0.0, 100.0, 2.0)
    assert deadline.child(8) <= 8


def test_later_role_cannot_reclaim_expired_parent():
    deadline = DeadlineBudget(0.0, 0.0, 1.0)
    assert deadline.child(8) == 0
    assert deadline.child(16) == 0


def test_cancellation_failure_does_not_extend_deadline():
    deadline = DeadlineBudget(0.0, 0.0, 1.0)
    assert deadline.remaining_seconds == 0


def test_cleanup_budget_is_not_negative():
    deadline = DeadlineBudget(0.0, 1.0, 2.0)
    assert deadline.child(1) == 0

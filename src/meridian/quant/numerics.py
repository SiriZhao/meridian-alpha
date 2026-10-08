"""Pin Decimal arithmetic independently of the embedding caller's context."""

from collections.abc import Callable
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from functools import wraps


def deterministic_decimal[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        # Specify every context setting: even decimal.DefaultContext is mutable
        # process state and must not be an implicit research parameter.
        with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN,
                                  Emin=-999999, Emax=999999, capitals=1, clamp=0,
                                  traps=[InvalidOperation, DivisionByZero, Overflow], flags=[])):
            return function(*args, **kwargs)
    return wrapped

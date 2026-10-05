"""
Shared wording for the "you cannot close this yet" refusals.

Two gates in this codebase answer the same shape of question — an engagement
cannot be completed while findings are unresolved, a program cannot be completed
while steps have no recorded outcome — and both are only useful if they say *which*
records are in the way. That needs a cap: a register with fifty open findings
should return a message a person can read, not a wall of text.

One constant, in `common`, because a view module in another app is not a home for
shared policy (the comment above ``BLOCKS_COMPLETION`` in
``apps/audit_planning/views.py`` says so, and names this as the alternative).
"""

# How many blockers to name in a refusal before eliding the rest: enough to act
# on, short enough to stay readable.
BLOCKERS_NAMED = 10


def describe_blockers(named, total):
    """``'1, 2, 3'` → ``'1, 2, 3, …'`` when there are more behind them.

    The elision matters more than it looks: without it the caller has to work out
    whether the absence of a number means "none left" or "list truncated", and a
    reader who assumes the first will move on believing a blocker is missing.
    """
    listed = ', '.join(str(n) for n in named)
    return f'{listed}, …' if total > len(named) else listed

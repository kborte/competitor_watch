"""Code the backend and the crawler both need.

The two are separate deployables but live in one repo and change in one commit,
so the wire contract and the helpers around it are defined once here rather than
copied into each. Nothing in this package imports from either of them, and
nothing here reads configuration — values that differ between the two are passed
in by the caller.
"""

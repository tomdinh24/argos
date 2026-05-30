"""Argos ontology — typed claim state and synthetic fixtures.

This is the Palantir-sense Ontology: the typed object graph that holds every
claim's state. In production it's backed by Foundry — `ontology/types.py`
defines the Python shapes that mirror the Foundry object types from
[foundry/ontology/object-types.yaml](../../../foundry/ontology/object-types.yaml),
and a thin OSDK wrapper fetches them by id.

For early development we run against in-memory synthetic fixtures
(`ontology/synthetic.py`) so specialists can be exercised end-to-end before
any Foundry tenant is wired. The contract is the same; only the backing
changes.
"""

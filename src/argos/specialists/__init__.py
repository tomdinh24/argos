"""Specialist runtimes — the live agents that read the ontology and emit
Assessment + Synthesis outputs per the contract in `argos.schemas.contract`.

Coverage is the first runtime, validated against the anchor pair in
`argos.ontology.synthetic.build_anchor_pair`. Other specialists (Brief,
Liability, Reserve, Recovery, Closure) come online behind it.
"""

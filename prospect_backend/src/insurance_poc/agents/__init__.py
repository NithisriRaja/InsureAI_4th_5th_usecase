"""The five agents of use case 4 (new customers), wired into one LangGraph in ``graph.py``.

==================  ===================================================================
prospect_agent      Find the right prospects: permission, consent, data quality and the
                    application checklist decide who may be assessed at all (rules only).
risk_agent          Summarise the risk: underwriting rules, eligibility screening of every
                    product, then a risk band + score; knock-outs go to an underwriter.
scoring_agent       Rank the leads: hot / warm / cold buying interest with grounded reasons.
product_agent       Match the right product: rank the eligible products, say why, and
                    suggest up to two products from other lines.
engagement_agent    Plan the next step: action, team queue, priority and channel (rules),
                    for staff approval; never contacts anyone.
==================  ===================================================================

Supporting steps: ``router`` (checks the request) and ``finalize`` (guardrails, then saves the
recommendation as pending approval). ``base`` holds the shared node decorator, ``state`` the
graph state. Every recommendation keeps its reasons and the signals it was based on.
"""

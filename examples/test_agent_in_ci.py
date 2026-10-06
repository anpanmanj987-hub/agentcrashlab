"""Copy this pattern into your test suite and replace purchase with your adapter."""
from agentcrashlab import run_case
from agentcrashlab.policies import resilient as purchase


def test_purchase_survives_a_lost_response():
    result = run_case('response-loss', agent=purchase, transport='http')
    assert result.passed, [c.to_dict() for c in result.checks if not c.passed]

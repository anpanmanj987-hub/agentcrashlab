# Connect your own agent

The 0.1 integration seam is a **trusted synchronous Python callable**. It accepts
`OrderTools` and `Task`, and returns `AgentResult`. The core has no SDK dependency
on a model vendor and never calls a model automatically.

Run the complete model-free custom example after installation:

```bash
python examples/custom_agent.py --output evidence/custom-policy
python -m pytest examples/test_agent_in_ci.py -q
```

The first command creates real fixture evidence. The example is not an LLM; it
shows the contract that a real model integration would use.

## Contract

```python
from agentcrashlab import AgentResult, OrderTools, Task, run_case
from agentcrashlab.bundles import write_bundle
from agentcrashlab.errors import ToolError


def my_policy(tools: OrderTools, task: Task) -> AgentResult:
    # Replace this policy body with your existing agent loop. Route EVERY test
    # order tool invocation through tools.create_order, never a production API.
    try:
        tools.create_order(**task.order_args(), idempotency_key=task.intent_id)
    except ToolError:
        return AgentResult("uncertain", "The tool outcome is not confirmed.")
    return AgentResult("success", "The tool returned an order.")


result = run_case("response-loss", agent=my_policy, transport="http")
write_bundle(result, "evidence/my-policy")
assert result.agent_name == "my_policy"
```

This deliberately simple example has no retry: after response loss it returns
`uncertain` and fails the case's successful-completion requirement even though
one order was committed. That is useful evidence, not a harness error.

## Exposing the tool to an LLM framework

Register a function in your framework that delegates these arguments unchanged
to `tools.create_order`: `intent_id`, `customer_id`, `sku`, `quantity`, and optional
`idempotency_key`. Give your existing agent the task and let it choose calls and
handle exceptions. Translate its final explicit status into `AgentResult`.
The tool returns an order dictionary; failure raises one of the exported tool
exceptions. Do not give the agent the fixture service's database, events or fault
schedule. Do not infer success in the adapter by inspecting the hidden backend.
That would contaminate the outcome being tested.

The library does **not** supply a pretested MCP server, a live model connector,
a prompt strategy or a vendor-neutral conversion from arbitrary framework tool
objects. You must adapt that small seam to your chosen framework and test it.
`LocalOrderServer` / `HttpOrderClient` provide real loopback transport internally;
they are not a proxy for arbitrary remote business APIs.

## Retry errors are intentionally ambiguous

Catch `ToolTimeout` for an unknown outcome. It does not reveal whether the write
committed. A stable key works only when the backend supports durable
idempotency. A new key for every retry defeats the mechanism. Payload changes
under the same customer/key are a conflict, not permission to create another
order. Distinguish `PermissionDenied` from a transient timeout.

Other exceptions: `IdempotencyConflict`, `InvalidRequest`, `CallLimitExceeded`,
`ProtocolError`. All are subclasses of `ToolError`. The reference resilient
policy is an example of bounded retries, not a universal solution.

## CI

```python
from agentcrashlab import run_case
from agentcrashlab.bundles import write_bundle

def test_my_agent_handles_lost_response(tmp_path):
    result = run_case("response-loss", agent=my_policy, transport="http")
    write_bundle(result, tmp_path / "evidence")
    assert result.passed, [c.id for c in result.checks if not c.passed]
```

The snippet assumes `my_policy` is imported from your agent module. The complete
runnable version is `examples/test_agent_in_ci.py`. Use an outer process/container
time limit for real agents; the in-process tool budget cannot terminate an
infinite policy loop. Do not supply production credentials. For live models, run
fresh cases repeatedly and report successes, failures, uncertain outcomes,
provider errors, model/configuration, trial count and date separately. Never
present the built-in deterministic examples as live model measurements.

"""Transport-independent tool failures. Never disclose the hidden commit outcome."""


class ToolError(Exception):
    code = 'tool_error'
    retryable = False


class ToolTimeout(ToolError):
    code = 'timeout'
    retryable = True

    def __init__(self) -> None:
        super().__init__('No response received; the operation outcome is unknown.')


class PermissionDenied(ToolError):
    code = 'permission_denied'

    def __init__(self) -> None:
        super().__init__('Order creation is not authorized.')


class IdempotencyConflict(ToolError):
    code = 'idempotency_conflict'

    def __init__(self) -> None:
        super().__init__('This idempotency key was already used for a different request.')


class InvalidRequest(ToolError):
    code = 'invalid_request'


class CallLimitExceeded(ToolError):
    code = 'call_limit'

    def __init__(self) -> None:
        super().__init__('The scenario tool-call limit was reached.')


class ProtocolError(ToolError):
    code = 'protocol_error'

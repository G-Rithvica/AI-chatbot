from pydantic import BaseModel


class McpToolCall(BaseModel):
    tool_name: str
    argument: str


class McpToolResult(BaseModel):
    output: str


def run_demo_tool(call: McpToolCall) -> McpToolResult:
    # Placeholder for real MCP tool bridge.
    return McpToolResult(output=f'[demo] tool={call.tool_name} arg={call.argument}')

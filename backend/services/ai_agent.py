"""Claude/Groq-backed assistant for ambiguous reconciliation cases.

The deterministic reconciliation engine owns all calculations. This module only
asks a configured LLM to reason over already-supplied evidence when the deterministic
engine cannot make a conclusive decision.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Mapping

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from services.agent_tools import (
    AgentToolContext,
    AgentToolError,
    execute_tool,
    get_groq_tool_definitions,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ClaudeDecision = Literal["clear", "flag", "needs_human"]
EvidenceSource = Literal["invoice", "rate_card", "dispatch", "history"]

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_VERSION = "2023-06-01"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_TOKENS = 700
MONEY_TOLERANCE = 0.01
MAX_TOOL_ITERATIONS = 5

AI_RECONCILIATION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["clear", "flag", "needs_human"],
        },
        "discrepancy_type": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "rupee_impact": {"type": "number"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["invoice", "rate_card", "dispatch", "history"],
                    },
                    "field": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["source", "field", "value"],
            },
        },
        "agent_trace": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tool": {"type": "string"},
                    "arguments": {"type": "object"},
                    "result": {"type": "object"},
                    "iteration": {"type": "integer"},
                },
                "required": ["tool", "arguments", "result", "iteration"],
            },
        },
    },
    "required": [
        "decision",
        "discrepancy_type",
        "reason",
        "confidence",
        "rupee_impact",
        "evidence",
        "agent_trace",
    ],
}

SYSTEM_PROMPT = """
You are the AI review layer for a freight invoice reconciliation system.

The deterministic reconciliation engine is the source of truth for arithmetic,
rate calculations, weight calculations, tolerance calculations, duplicate
detection, and rupee impact calculations.

You must follow these rules:
1. Never invent missing information.
2. Never invent a rate-card contract.
3. Never invent historical invoices.
4. Never perform financial arithmetic when a deterministic value has already
   been supplied.
5. Use the supplied deterministic calculations as authoritative.
6. If evidence is insufficient, return needs_human.
7. If evidence clearly supports a discrepancy, return flag.
8. If evidence clearly supports a valid invoice, return clear.
9. Confidence must be between 0 and 1.
10. Explain the decision using only supplied evidence.

When tools are provided:
- Use only the tools in the provided registry.
- Do not request filesystem access, code execution, or unsupported operations.
- Ask for tools when evidence is missing or the ambiguity requires
  investigation.
- Treat tool results as deterministic evidence.

If you choose flag, rupee_impact must be copied from
allowed_flag_rupee_impact. If allowed_flag_rupee_impact is null, return 0.0
and explain that the financial impact was not deterministically supplied.
For clear decisions, rupee_impact must be 0.0. For needs_human decisions,
preserve supplied deterministic rupee impact only when the orchestrator tells
you to preserve it after a tool or API failure.
Return only JSON matching the supplied schema.
""".strip()


class ClaudeAgentError(Exception):
    """Base class for expected AI-agent failures."""


class ClaudeConfigurationError(ClaudeAgentError):
    """Raised when Claude cannot be called because configuration is missing."""


class ClaudeAPIError(ClaudeAgentError):
    """Raised when the Claude API request fails."""


class ClaudeResponseValidationError(ClaudeAgentError):
    """Raised when Claude returns malformed or unsafe structured output."""


class AIReconciliationEvidence(BaseModel):
    """Evidence item cited by the AI decision."""

    model_config = ConfigDict(extra="forbid")

    source: EvidenceSource
    field: str = Field(min_length=1)
    value: str = Field(min_length=1)


class AgentTraceEntry(BaseModel):
    """Auditable record of a controlled tool call."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1)
    arguments: dict[str, Any]
    result: dict[str, Any]
    iteration: int = Field(ge=1)


class AIReconciliationResult(BaseModel):
    """Validated AI reconciliation decision."""

    model_config = ConfigDict(extra="forbid")

    decision: ClaudeDecision
    discrepancy_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    rupee_impact: float
    evidence: list[AIReconciliationEvidence] = Field(default_factory=list)
    agent_trace: list[AgentTraceEntry] = Field(default_factory=list)


class AIReconciliationCaseContext(BaseModel):
    """Structured context passed from deterministic reconciliation to Claude."""

    model_config = ConfigDict(extra="allow")

    invoice_data: dict[str, Any]
    normalized_invoice_data: dict[str, Any] | None = None
    matched_rate_card: dict[str, Any] | None = None
    dispatch_record: dict[str, Any] | None = None
    deterministic_checks_performed: list[str] = Field(default_factory=list)
    detected_ambiguity: str = Field(min_length=1)
    calculated_variance: dict[str, Any] | float | int | str | None = None
    calculated_financial_impact: dict[str, Any] | float | int | str | None = None
    relevant_evidence: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("invoice_data", "normalized_invoice_data", "matched_rate_card", "dispatch_record")
    @classmethod
    def _json_objects_only(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        return dict(value)


def reconcile_ambiguous_case(case_context: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
    """Ask Claude to resolve an ambiguous case using deterministic evidence.

    The returned dictionary always matches ``AIReconciliationResult``. Expected
    Claude/configuration/validation failures are converted to a needs_human
    decision so a reconciliation batch can continue.
    """
    try:
        normalized_context = _normalize_case_context(case_context)
        context_payload = normalized_context.model_dump(mode="json")
        allowed_flag_rupee_impact = _extract_deterministic_rupee_impact(context_payload)
        claude_response = _post_to_claude(
            _build_claude_payload(
                context_payload=context_payload,
                allowed_flag_rupee_impact=allowed_flag_rupee_impact,
            ),
            api_key=_get_api_key(),
            timeout_seconds=_get_timeout_seconds(),
        )
        result = _parse_claude_response(claude_response)
        result = _validate_result_against_context(
            result=result,
            context_payload=context_payload,
            allowed_flag_rupee_impact=allowed_flag_rupee_impact,
            agent_trace=[],
            preserve_needs_human_impact=False,
        )
        return result.model_dump(mode="json")
    except (ClaudeAgentError, ValidationError, TypeError, ValueError) as exc:
        return _needs_human_result(
            discrepancy_type="ai_agent_unavailable"
            if not isinstance(exc, ClaudeResponseValidationError)
            else "ai_response_invalid",
            reason=f"AI review could not produce a reliable decision: {exc}",
        )


def reconcile_ambiguous_case_with_tools(
    case_context: Mapping[str, Any] | BaseModel,
    *,
    tool_context: AgentToolContext | None = None,
) -> dict[str, Any]:
    """Resolve an ambiguous case through a bounded provider tool-use loop."""
    agent_trace: list[AgentTraceEntry] = []
    allowed_flag_rupee_impact: float | None = None

    try:
        normalized_context = _normalize_case_context(case_context)
        context_payload = normalized_context.model_dump(mode="json")
        allowed_flag_rupee_impact = _extract_deterministic_rupee_impact(context_payload)
        messages = _build_initial_tool_messages(
            context_payload=context_payload,
            allowed_flag_rupee_impact=allowed_flag_rupee_impact,
        )
        api_key = _get_api_key()
        timeout_seconds = _get_timeout_seconds()

        for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
            response = _post_to_claude(
                _build_tool_claude_payload(messages=messages, include_tools=True),
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
            tool_uses = _extract_tool_uses(response)

            if tool_uses:
                messages.append(
                    {
                        "role": "assistant",
                        "content": _to_jsonable(response["content"]),
                    }
                )
                tool_result_blocks = []
                for tool_use in tool_uses:
                    tool_result = _execute_tool_use(
                        tool_use,
                        iteration=iteration,
                        agent_trace=agent_trace,
                        tool_context=tool_context,
                    )
                    tool_result_blocks.append(tool_result)

                messages.append({"role": "user", "content": tool_result_blocks})
                allowed_flag_rupee_impact = _extract_authoritative_rupee_impact(
                    context_payload=context_payload,
                    agent_trace=agent_trace,
                )
                continue

            if _get_provider() == "groq":
                messages.append(
                    {
                        "role": "assistant",
                        "content": _to_jsonable(response["content"]),
                    }
                )
                response = _post_to_claude(
                    _build_tool_claude_payload(
                        messages=messages,
                        include_tools=False,
                    ),
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                )

            result = _parse_claude_response(response)
            allowed_flag_rupee_impact = _extract_authoritative_rupee_impact(
                context_payload=context_payload,
                agent_trace=agent_trace,
            )
            result = _validate_result_against_context(
                result=result,
                context_payload=context_payload,
                allowed_flag_rupee_impact=allowed_flag_rupee_impact,
                agent_trace=agent_trace,
                preserve_needs_human_impact=True,
            )
            return _with_agent_trace(result, agent_trace).model_dump(mode="json")

        return _needs_human_result(
            discrepancy_type="tool_iteration_limit_reached",
            reason=(
                f"AI review reached the maximum of {MAX_TOOL_ITERATIONS} "
                "tool iterations without a final decision."
            ),
            rupee_impact=_fallback_rupee_impact(allowed_flag_rupee_impact),
            agent_trace=agent_trace,
        )
    except (AgentToolError, ClaudeAPIError, ClaudeConfigurationError) as exc:
        return _needs_human_result(
            discrepancy_type="ai_tool_failure"
            if isinstance(exc, AgentToolError)
            else "ai_agent_unavailable",
            reason=f"AI tool investigation could not produce a reliable decision: {exc}",
            rupee_impact=_fallback_rupee_impact(allowed_flag_rupee_impact),
            agent_trace=agent_trace,
        )
    except ClaudeResponseValidationError as exc:
        return _needs_human_result(
            discrepancy_type="ai_response_invalid",
            reason=f"AI tool investigation returned invalid output: {exc}",
            rupee_impact=_fallback_rupee_impact(allowed_flag_rupee_impact),
            agent_trace=agent_trace,
        )
    except (ValidationError, TypeError, ValueError, KeyError) as exc:
        return _needs_human_result(
            discrepancy_type="ai_tool_failure",
            reason=f"AI tool investigation failed safely: {exc}",
            rupee_impact=_fallback_rupee_impact(allowed_flag_rupee_impact),
            agent_trace=agent_trace,
        )


def _get_api_key() -> str:
    api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ClaudeConfigurationError(
            "LLM API key is not configured. Set CLAUDE_API_KEY, ANTHROPIC_API_KEY, or GROQ_API_KEY."
        )
    return api_key


def _get_provider() -> str:
    if os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    raise ClaudeConfigurationError(
        "LLM API key is not configured. Set CLAUDE_API_KEY, ANTHROPIC_API_KEY, or GROQ_API_KEY."
    )


def _get_timeout_seconds() -> float:
    raw_timeout = os.getenv("CLAUDE_TIMEOUT_SECONDS") or os.getenv("GROQ_TIMEOUT_SECONDS")
    if raw_timeout is None:
        return DEFAULT_TIMEOUT_SECONDS

    try:
        timeout = float(raw_timeout)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS

    if timeout <= 0:
        return DEFAULT_TIMEOUT_SECONDS
    return timeout


def _get_model_name() -> str:
    if _get_provider() == "groq":
        return os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    return os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)


def _normalize_case_context(case_context: Mapping[str, Any] | BaseModel) -> AIReconciliationCaseContext:
    jsonable_context = _to_jsonable(case_context)
    if not isinstance(jsonable_context, Mapping):
        raise ValueError("case_context must be a mapping or Pydantic model.")
    return AIReconciliationCaseContext.model_validate(dict(jsonable_context))


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _build_claude_payload(
    *,
    context_payload: dict[str, Any],
    allowed_flag_rupee_impact: float | None,
) -> dict[str, Any]:
    model_context = {
        **context_payload,
        "allowed_flag_rupee_impact": allowed_flag_rupee_impact,
        "rupee_impact_rule": (
            "Use allowed_flag_rupee_impact exactly when decision is flag. "
            "Use 0.0 when decision is clear or needs_human."
        ),
    }

    return {
        "model": _get_model_name(),
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Resolve this ambiguous freight invoice case using only "
                            "the supplied structured evidence.\n\n"
                            f"{json.dumps(model_context, indent=2, sort_keys=True)}"
                        ),
                    }
                ],
            }
        ],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": _claude_compatible_output_schema(),
            }
        },
    }


def _build_initial_tool_messages(
    *,
    context_payload: dict[str, Any],
    allowed_flag_rupee_impact: float | None,
) -> list[dict[str, Any]]:
    model_context = {
        **context_payload,
        "allowed_flag_rupee_impact": allowed_flag_rupee_impact,
        "tool_policy": (
            "Use controlled tools when evidence is missing. Never request "
            "filesystem access, arbitrary code execution, or tools outside the "
            "registry. Return final JSON only after investigation is complete."
        ),
    }

    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Investigate this ambiguous freight invoice case. "
                        "Use controlled tools if needed, then return the final "
                        "structured decision.\n\n"
                        f"{json.dumps(model_context, indent=2, sort_keys=True)}"
                    ),
                }
            ],
        }
    ]


def _build_tool_claude_payload(
    *,
    messages: list[dict[str, Any]],
    include_tools: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": _get_model_name(),
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": messages,
    }
    if include_tools:
        payload["tools"] = get_groq_tool_definitions()
        payload["tool_choice"] = {"type": "auto"}

    if _get_provider() != "groq" or not include_tools:
        payload["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": _claude_compatible_output_schema(),
            }
        }

    return payload


def _extract_tool_uses(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    content = response.get("content")
    if not isinstance(content, list):
        raise ClaudeResponseValidationError("Claude response missing content blocks.")

    tool_uses = [
        block
        for block in content
        if isinstance(block, Mapping) and block.get("type") == "tool_use"
    ]

    if response.get("stop_reason") == "tool_use" and not tool_uses:
        raise ClaudeResponseValidationError(
            "Claude stopped for tool use without a valid tool_use block."
        )

    return tool_uses


def _claude_compatible_output_schema() -> dict[str, Any]:
    unsupported_keywords = {
        "exclusiveMinimum",
        "exclusiveMaximum",
        "maxLength",
        "maximum",
        "minLength",
        "minimum",
        "title",
    }

    def strip_unsupported(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: strip_unsupported(nested_value)
                for key, nested_value in value.items()
                if key not in unsupported_keywords
            }
        if isinstance(value, list):
            return [strip_unsupported(item) for item in value]
        return value

    return strip_unsupported(AI_RECONCILIATION_OUTPUT_SCHEMA)

def _groq_compatible_output_schema() -> dict[str, Any]:
    """Make the shared schema acceptable to Groq strict structured outputs."""
    schema = _claude_compatible_output_schema()
    schema["properties"].pop("agent_trace", None)
    schema["required"] = [
        field for field in schema["required"] if field != "agent_trace"
    ]

    def strictify(value: Any) -> Any:
        if isinstance(value, dict):
            result = {
                key: strictify(nested_value)
                for key, nested_value in value.items()
            }
            if result.get("type") == "object":
                result["additionalProperties"] = False
            return result
        if isinstance(value, list):
            return [strictify(item) for item in value]
        return value

    return strictify(schema)


def _execute_tool_use(
    tool_use: Mapping[str, Any],
    *,
    iteration: int,
    agent_trace: list[AgentTraceEntry],
    tool_context: AgentToolContext | None,
) -> dict[str, Any]:
    tool_name = _tool_use_name(tool_use)
    tool_arguments = _tool_use_arguments(tool_use)
    tool_use_id = _tool_use_id(tool_use)

    try:
        tool_result = execute_tool(
            tool_name,
            tool_arguments,
            context=tool_context,
        )
    except AgentToolError as exc:
        agent_trace.append(
            AgentTraceEntry(
                tool=tool_name,
                arguments=tool_arguments,
                result={"error": str(exc)},
                iteration=iteration,
            )
        )
        raise

    agent_trace.append(
        AgentTraceEntry(
            tool=tool_name,
            arguments=tool_arguments,
            result=tool_result,
            iteration=iteration,
        )
    )
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(tool_result, sort_keys=True),
    }


def _tool_use_name(tool_use: Mapping[str, Any]) -> str:
    name = tool_use.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ClaudeResponseValidationError("Claude tool_use block missing tool name.")
    return name.strip()


def _tool_use_arguments(tool_use: Mapping[str, Any]) -> dict[str, Any]:
    arguments = tool_use.get("input")
    if not isinstance(arguments, Mapping):
        raise ClaudeResponseValidationError("Claude tool_use input must be an object.")
    return dict(arguments)


def _tool_use_id(tool_use: Mapping[str, Any]) -> str:
    tool_use_id = tool_use.get("id")
    if not isinstance(tool_use_id, str) or not tool_use_id.strip():
        raise ClaudeResponseValidationError("Claude tool_use block missing tool_use id.")
    return tool_use_id


def _groq_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate the internal message shape to Groq's OpenAI format."""
    messages: list[dict[str, Any]] = []
    if payload.get("system"):
        messages.append({"role": "system", "content": str(payload["system"])})

    for message in payload.get("messages", []):
        role = message.get("role")
        content = message.get("content", "")
        if isinstance(content, list):
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, Mapping):
                    continue
                if block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
                elif block.get("type") == "tool_result":
                    messages.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", "tool_call"),
                        "content": str(block.get("content", "")),
                    })
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", "tool_call"),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        }
                    })
            if tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": "\n".join(text_parts),
                    "tool_calls": tool_calls,
                })
            elif text_parts:
                messages.append({"role": role, "content": "\n".join(text_parts)})
            continue
        messages.append({"role": role, "content": str(content)})

    translated: dict[str, Any] = {
        "model": payload["model"],
        "messages": messages,
        "temperature": payload.get("temperature", 0),
        "max_tokens": payload.get("max_tokens", DEFAULT_MAX_TOKENS),
    }
    output_config = payload.get("output_config", {})
    output_format = (
        output_config.get("format")
        if isinstance(output_config, Mapping)
        else None
    )
    if isinstance(output_format, Mapping) and output_format.get("schema"):
        translated["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "ai_reconciliation_result",
                "strict": True,
                "schema": _groq_compatible_output_schema(),
            },
        }
    tools = payload.get("tools")
    if isinstance(tools, list):
        translated["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
            if isinstance(tool, Mapping)
        ]
    elif "response_format" not in translated:
        translated["response_format"] = {"type": "json_object"}
    return translated


def _post_to_groq(
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(_groq_payload(payload)).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
            "User-Agent": "freight-recon-agent/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise ClaudeAPIError(f"Groq API returned HTTP {exc.code}: {error_body[:500]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ClaudeAPIError(f"Groq API request failed: {exc}") from exc

    try:
        decoded = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ClaudeAPIError("Groq API returned invalid JSON.") from exc

    if not isinstance(decoded, dict):
        raise ClaudeAPIError("Groq API returned a non-object response.")

    choices = decoded.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise ClaudeAPIError("Groq API response did not contain choices.")
    message = choices[0].get("message")
    if not isinstance(message, Mapping):
        raise ClaudeAPIError("Groq API response did not contain a message.")

    content: list[dict[str, Any]] = []
    tool_calls = message.get("tool_calls", [])
    if isinstance(tool_calls, list):
        for index, tool_call in enumerate(tool_calls):
            if not isinstance(tool_call, Mapping):
                continue
            function = tool_call.get("function")
            if not isinstance(function, Mapping) or not isinstance(function.get("name"), str):
                continue
            raw_arguments = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                arguments = raw_arguments
            content.append(
                {
                    "type": "tool_use",
                    "id": str(tool_call.get("id", f"groq_tool_{index}")),
                    "name": function["name"],
                    "input": dict(arguments),
                }
            )

    response_text = message.get("content")
    if isinstance(response_text, str) and response_text.strip():
        content.append({"type": "text", "text": response_text})

    return {
        "content": content,
        "stop_reason": "tool_use" if tool_calls else "end_turn",
    }


def _post_to_claude(
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Dispatch to Claude or Groq while preserving the existing hook name."""
    if _get_provider() == "groq":
        return _post_to_groq(payload, api_key=api_key, timeout_seconds=timeout_seconds)

    request = urllib.request.Request(
        CLAUDE_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": CLAUDE_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise ClaudeAPIError(f"Claude API returned HTTP {exc.code}: {error_body[:500]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ClaudeAPIError(f"Claude API request failed: {exc}") from exc
    try:
        decoded = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ClaudeAPIError("Claude API returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise ClaudeAPIError("Claude API returned a non-object response.")
    return decoded


def _parse_claude_response(response: Mapping[str, Any]) -> AIReconciliationResult:
    content = response.get("content")
    if not isinstance(content, list):
        raise ClaudeResponseValidationError("Claude response missing content blocks.")

    text_blocks = [
        block.get("text", "")
        for block in content
        if isinstance(block, Mapping) and block.get("type") == "text"
    ]
    response_text = "\n".join(text for text in text_blocks if text).strip()
    if not response_text:
        raise ClaudeResponseValidationError("Claude response did not include JSON text.")

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ClaudeResponseValidationError("Claude response was not valid JSON.") from exc

    try:
        return AIReconciliationResult.model_validate(payload)
    except ValidationError as exc:
        raise ClaudeResponseValidationError(f"Claude response failed schema validation: {exc}") from exc


def _validate_result_against_context(
    *,
    result: AIReconciliationResult,
    context_payload: dict[str, Any],
    allowed_flag_rupee_impact: float | None,
    agent_trace: list[AgentTraceEntry],
    preserve_needs_human_impact: bool,
) -> AIReconciliationResult:
    if result.decision in {"clear", "flag"} and not result.evidence:
        raise ClaudeResponseValidationError(
            "Claude response made a conclusive decision without citing evidence."
        )

    for item in result.evidence:
        if not _context_supports_evidence_item(
            context_payload=context_payload,
            agent_trace=agent_trace,
            item=item,
        ):
            raise ClaudeResponseValidationError(
                "Claude cited evidence that was not supplied: "
                f"{item.source}.{item.field}={item.value}"
            )

    if result.decision == "flag":
        if allowed_flag_rupee_impact is None:
            if not _money_equal(result.rupee_impact, 0.0):
                raise ClaudeResponseValidationError(
                    "Claude supplied a nonzero rupee_impact without deterministic impact."
                )
            return result

        if not _money_equal(result.rupee_impact, allowed_flag_rupee_impact):
            raise ClaudeResponseValidationError(
                "Claude rupee_impact does not match the deterministic impact."
            )
        return result.model_copy(update={"rupee_impact": round(allowed_flag_rupee_impact, 2)})

    if result.decision == "needs_human" and preserve_needs_human_impact:
        return result.model_copy(
            update={
                "rupee_impact": _fallback_rupee_impact(allowed_flag_rupee_impact),
            }
        )

    if not _money_equal(result.rupee_impact, 0.0):
        raise ClaudeResponseValidationError(
            "Claude supplied rupee_impact for a non-flag decision."
        )
    return result.model_copy(update={"rupee_impact": 0.0})


def _context_supports_evidence_item(
    *,
    context_payload: dict[str, Any],
    agent_trace: list[AgentTraceEntry],
    item: AIReconciliationEvidence,
) -> bool:
    if _relevant_evidence_matches(context_payload, item):
        return True

    for section in _source_sections(context_payload, agent_trace, item.source):
        if _contains_field_value(section, item.field, item.value):
            return True

    return False


def _source_sections(
    context_payload: dict[str, Any],
    agent_trace: list[AgentTraceEntry],
    source: EvidenceSource,
) -> list[Any]:
    source_keys = {
        "invoice": ("invoice_data", "normalized_invoice_data", "invoice"),
        "rate_card": ("matched_rate_card", "rate_card", "matched_rate_card_information"),
        "dispatch": ("dispatch_record", "dispatch"),
        "history": ("history", "historical_invoices", "prior_invoices", "duplicate_history"),
    }
    tool_sources = {
        "get_invoice": ("invoice",),
        "get_rate_card": ("rate_card",),
        "get_dispatch_record": ("dispatch",),
        "calculate_weight_variance": ("invoice", "dispatch"),
        "calculate_financial_impact": ("invoice", "rate_card"),
        "search_similar_invoices": ("history",),
    }

    sections: list[Any] = [
        context_payload[key]
        for key in source_keys[source]
        if context_payload.get(key) is not None
    ]

    for item in context_payload.get("relevant_evidence", []):
        if isinstance(item, Mapping) and item.get("source") == source:
            sections.append(item)

    for trace_entry in agent_trace:
        if source in tool_sources.get(trace_entry.tool, ()):
            sections.append(trace_entry.result)

    return sections


def _relevant_evidence_matches(
    context_payload: dict[str, Any],
    item: AIReconciliationEvidence,
) -> bool:
    for evidence_item in context_payload.get("relevant_evidence", []):
        if not isinstance(evidence_item, Mapping):
            continue
        if (
            evidence_item.get("source") == item.source
            and evidence_item.get("field") == item.field
            and _evidence_values_equal(evidence_item.get("value"), item.value)
        ):
            return True
    return False


def _contains_field_value(payload: Any, field: str, value: str) -> bool:
    if isinstance(payload, Mapping):
        for key, nested_value in payload.items():
            if key == field and _evidence_values_equal(nested_value, value):
                return True
            if _contains_field_value(nested_value, field, value):
                return True
        return False

    if isinstance(payload, list):
        return any(_contains_field_value(item, field, value) for item in payload)

    return False


def _evidence_values_equal(left: Any, right: str) -> bool:
    left_number = _coerce_float(left)
    right_number = _coerce_float(right)
    if left_number is not None and right_number is not None:
        return _money_equal(left_number, right_number)

    return str(left).strip() == str(right).strip()


def _extract_deterministic_rupee_impact(context_payload: Mapping[str, Any]) -> float | None:
    for key in ("rupee_impact", "calculated_rupee_impact", "deterministic_rupee_impact"):
        value = _coerce_float(context_payload.get(key))
        if value is not None:
            return round(value, 2)

    calculated_financial_impact = context_payload.get("calculated_financial_impact")
    direct_value = _coerce_float(calculated_financial_impact)
    if direct_value is not None:
        return round(direct_value, 2)

    if isinstance(calculated_financial_impact, Mapping):
        for key in ("rupee_impact", "impact", "amount", "value", "calculated_rupee_impact"):
            value = _coerce_float(calculated_financial_impact.get(key))
            if value is not None:
                return round(value, 2)

    return None


def _extract_authoritative_rupee_impact(
    *,
    context_payload: Mapping[str, Any],
    agent_trace: list[AgentTraceEntry],
) -> float | None:
    for trace_entry in reversed(agent_trace):
        if trace_entry.tool != "calculate_financial_impact":
            continue
        value = _coerce_float(trace_entry.result.get("rupee_impact"))
        if value is not None:
            return round(value, 2)

    return _extract_deterministic_rupee_impact(context_payload)


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").removeprefix("Rs.").removeprefix("INR")
        cleaned = cleaned.strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _money_equal(left: float, right: float) -> bool:
    return abs(round(left, 2) - round(right, 2)) <= MONEY_TOLERANCE


def _fallback_rupee_impact(rupee_impact: float | None) -> float:
    if rupee_impact is None:
        return 0.0
    return round(rupee_impact, 2)


def _with_agent_trace(
    result: AIReconciliationResult,
    agent_trace: list[AgentTraceEntry],
) -> AIReconciliationResult:
    return result.model_copy(update={"agent_trace": list(agent_trace)})


def _needs_human_result(
    *,
    discrepancy_type: str,
    reason: str,
    rupee_impact: float = 0.0,
    agent_trace: list[AgentTraceEntry] | None = None,
) -> dict[str, Any]:
    return AIReconciliationResult(
        decision="needs_human",
        discrepancy_type=discrepancy_type,
        reason=reason,
        confidence=0.0,
        rupee_impact=round(rupee_impact, 2),
        evidence=[],
        agent_trace=agent_trace or [],
    ).model_dump(mode="json")

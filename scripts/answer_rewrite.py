"""V5: rewrite the agent's final answer from its tool results only (no upstream imports).

Used at run time by run_baseline.py --evidence-answer (ANSWER_PATCH) and offline by
v5_answer_test.py. See results/groundedness_dev_eval.md for why.
"""
import json

MAX_RESPONSE_CHARS = 8000  # per tool response in the prompt
MAX_EVIDENCE_CHARS = 60000  # the most recent responses are kept

# Rule 6 was "If the tool results do not contain the answer, say that the information is not
# available instead of guessing" in the first offline test (20261110-1536-v5test-v5). It turned
# two supported answers into refusals, so it now applies only when no result relates to the answer.
V5_PROMPT = """You write the final answer to a user's question using only the results of tool calls that were already made. You are also given a draft answer.

Rules:
1. Every fact in your answer must appear in the tool results. Copy names, numbers and values as they appear there. Do not add units, conversions, rounding, dates or explanations that the tool results do not contain.
2. Do not use outside knowledge, even if you are sure it is true.
3. Do not claim more than the results show: avoid words such as "only", "all", "sole" or "complete" unless a tool result says so.
4. If a result was filtered or sorted by a tool call's arguments, you may say so by naming that argument (for example: "filtered by country = USA").
5. If a calculation is needed, use only numbers from the tool results.
6. Keep the draft's answer when the tool results support it, even if not every step used to reach it is shown. Say that the information is not available only when no tool result relates to the answer.
7. Be concise. When the answer is a list, include every item.

Reply with the final answer only."""


def evidence_prompt(query: str, calls: list[tuple[str, dict, str]], draft: str) -> str:
    """The user message for V5_PROMPT; calls are (tool name, arguments, result text) in order."""
    blocks = []
    for i, (name, arguments, result) in enumerate(calls, 1):
        result = str(result)
        if len(result) > MAX_RESPONSE_CHARS:
            result = result[:MAX_RESPONSE_CHARS] + " …[truncated]"
        blocks.append(f"[{i}] {name}({json.dumps(arguments, ensure_ascii=False)})\n-> {result}")
    evidence = "\n\n".join(blocks)[-MAX_EVIDENCE_CHARS:] or "(no tool calls were made)"
    return f"Question: {query}\n\nTool calls and results:\n{evidence}\n\nDraft answer:\n{draft}"

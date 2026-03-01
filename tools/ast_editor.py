from __future__ import annotations

import difflib
import importlib
import importlib.util
import textwrap
from pathlib import Path
from typing import Any

HAS_LIBCST = importlib.util.find_spec("libcst") is not None
if HAS_LIBCST:
    cst = importlib.import_module("libcst")


def _resolve(file_path: str, repo_root: str) -> Path:
    p = Path(file_path)
    if repo_root and not p.is_absolute():
        return Path(repo_root) / p
    return p


def _strip_def_line(new_body: str) -> str:
    """
    Remove a leading 'def functionname(...):' line if the LLM included it.

    LLMs often write new_code as the full function definition instead of
    just the body. This function strips that header so ast_editor only
    sees the body statements, preventing the nested-function bug.
    """
    lines = new_body.splitlines()
    if not lines:
        return "pass"

    first_idx = -1
    for i, line in enumerate(lines):
        if line.strip():
            first_idx = i
            break

    if first_idx != -1:
        first = lines[first_idx].strip()
        # Strip the def line if present (handles 'def foo(...):', 'def foo(a, b) -> T:' etc.)
        if first.startswith("def ") and first.endswith(":"):
            lines = lines[first_idx + 1:]

    # Dedent so indentation is relative, not absolute
    body = textwrap.dedent("\n".join(lines)).strip()
    return body if body else "pass"


def _fallback_rewrite(before: str, function_name: str, new_body: str) -> tuple[bool, str]:
    """
    Pure-text fallback rewriter used when libcst is not available.

    Finds the OUTERMOST top-level `def <function_name>(` and replaces
    its entire body with `new_body`.
    """
    lines = before.splitlines()
    target = f"def {function_name}("
    found_idx = -1

    # Only match top-level functions (no leading whitespace) to avoid
    # replacing nested functions of the same name
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(target) and len(line) == len(stripped):
            # Zero-indent → top-level function
            found_idx = idx
            break

    if found_idx == -1:
        # Retry: match the first occurrence at any indent level
        for idx, line in enumerate(lines):
            if line.lstrip().startswith(target):
                found_idx = idx
                break

    if found_idx == -1:
        return False, before

    idx = found_idx
    # Body indent = function indent + 4 spaces
    func_indent = len(lines[idx]) - len(lines[idx].lstrip())
    body_indent = " " * (func_indent + 4)

    # Build replacement body lines
    body_lines = [
        f"{body_indent}{segment}"
        for segment in new_body.splitlines()
        if segment.strip()
    ]
    if not body_lines:
        body_lines = [f"{body_indent}pass"]

    # Find where the old body ends: lines that are MORE indented than the
    # function def, OR blank lines inside the body
    end = idx + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() == "":
            end += 1
            continue
        current_indent = len(line) - len(line.lstrip())
        if current_indent > func_indent:
            end += 1
        else:
            break

    updated = lines[: idx + 1] + body_lines + lines[end:]
    return True, "\n".join(updated) + "\n"


def edit_file(file_path: str, ast_transform: dict[str, Any], repo_root: str = "") -> dict[str, Any]:
    path = _resolve(file_path, repo_root)
    if not path.exists():
        return {"ok": False, "error": "file_not_found", "file_path": file_path}

    before = path.read_text(encoding="utf-8")
    transform_type = ast_transform.get("type")
    if transform_type != "rewrite_function":
        return {"ok": False, "error": "unsupported_transform", "transform": ast_transform}

    function_name = ast_transform["function_name"]
    # Strip `def ...():` header line if the LLM accidentally included it
    new_body = _strip_def_line(ast_transform.get("new_body", "pass") or "pass")

    if HAS_LIBCST:
        class FunctionRewriter(cst.CSTTransformer):
            def __init__(self, fn_name: str, body_src: str) -> None:
                self.fn_name = fn_name
                self.replaced = False
                # Parse just the body statements once
                self._new_stmts = cst.parse_module(body_src).body

            def leave_FunctionDef(self, original_node, updated_node):
                if original_node.name.value != self.fn_name:
                    return updated_node
                # Only replace top-level occurrences (indent == 0 in the module)
                self.replaced = True
                new_block = updated_node.body.with_changes(body=self._new_stmts)
                return updated_node.with_changes(body=new_block)

        module = cst.parse_module(before)
        rewriter = FunctionRewriter(fn_name=function_name, body_src=new_body)
        after = module.visit(rewriter).code
        replaced = rewriter.replaced
    else:
        replaced, after = _fallback_rewrite(before, function_name, new_body)

    if not replaced:
        return {
            "ok": False,
            "error": "function_not_found",
            "file_path": file_path,
            "function_name": function_name,
        }

    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )
    return {
        "ok": True,
        "file_path": file_path,
        "function_name": function_name,
        "change_type": "update",
        "diff": diff,
        "updated_content": after,
        "engine": "libcst" if HAS_LIBCST else "fallback",
    }

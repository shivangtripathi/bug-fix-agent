from __future__ import annotations

from typing import Literal, Annotated
from pydantic import BaseModel, Field


class PatchInstruction(BaseModel):
    file_path: str
    function_name: str | None = None
    change_type: Literal["insert", "update", "delete"]
    rationale: str
    new_code: str = ""


class TestInstruction(BaseModel):
    file_path: str
    test_name: str
    content: str


class TestFile(BaseModel):
    filename: Annotated[str, Field(description="Base filename only, e.g. 'test_calculator.py'")]
    content: Annotated[str, Field(description="Full pytest file content")]


class GeneratedTests(BaseModel):
    test_files: Annotated[list[TestFile], Field(description="List of test files to write")]


class StructuredPlan(BaseModel):
    bug_summary: Annotated[str, Field(description="A short summary of the bug")]
    root_cause: Annotated[str, Field(description="A detailed explanation of the root cause of the bug")]
    files_to_modify: Annotated[list[str], Field(description="A list of file paths to modify")]
    patches: Annotated[list[PatchInstruction], Field(description="A list of patch instructions")]
    tests_to_add: Annotated[list[TestInstruction], Field(description="A list of test instructions")]
    bash_commands: Annotated[list[str], Field(description="A list of bash commands to run")]



class ConversationState(BaseModel):
    bug_id: str | None = None
    conversation: list[str] = []
    conversation_summary: str | None = None
    active_bug: str | None = None
    plan: dict[str, object] | None = None
    execution: dict[str, object] | None = None
    messages: list[dict] = []
    awaiting_fix_approval: bool = False
from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from agents.orchestrator import Orchestrator
from tools.indexing import RepoIndexer

app = typer.Typer(help="Multi-agent bug fixing CLI")
console = Console()


# ─────────────────────────────────────────────────────────────
# Tiny helpers
# ─────────────────────────────────────────────────────────────

def _ask(prompt: str) -> bool:
    """Ask a yes/no question. Returns True for y/yes."""
    try:
        answer = console.input(f"[bold]{prompt}[/bold] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes"}


def _divider() -> None:
    console.print("[dim]──────────────────────────────────────────────[/dim]")


def _header(text: str) -> None:
    console.print(f"\n[bold]{text}[/bold]")


# ─────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────

def _show_patches(plan: dict) -> None:
    """Print proposed patches as plain text with syntax blocks."""
    patches = plan.get("patches", [])
    if not patches:
        console.print("[dim]  No patches proposed.[/dim]")
        return

    _header("Proposed patches")
    for patch in patches:
        file_path = patch.get("file_path", "unknown")
        fn = patch.get("function_name")
        label = f"{file_path}::{fn}" if fn else file_path
        rationale = patch.get("rationale", "")
        console.print(f"\n  [cyan]{label}[/cyan]")
        if rationale:
            console.print(f"  [dim]{rationale}[/dim]")
        new_code = patch.get("new_code", "")
        if new_code:
            console.print(Syntax(new_code, "python", theme="github-dark", line_numbers=False))


def _show_plan_overview(plan: dict) -> None:
    """Print a minimal one-liner overview of the plan before asking to apply."""
    files = plan.get("files_to_modify", [])
    tests = plan.get("tests_to_add", [])
    bash = plan.get("bash_commands", [])
    parts = []
    if files:
        parts.append(f"modify {', '.join(files)}")
    if tests:
        parts.append(f"add tests in {', '.join(t['file_path'] for t in tests)}")
    if bash:
        parts.append(f"run: {', '.join(bash)}")
    console.print(f"\n  Plan: {' | '.join(parts) if parts else 'no changes'}")


def _show_execution_diffs(patch_result: dict) -> None:
    """Print diffs produced by the patcher."""
    patches = patch_result.get("results", {}).get("patches", [])
    for p in patches:
        diff = p.get("diff", "")
        if diff:
            file_path = p.get("file_path", "unknown")
            console.print(f"\n  [green]{file_path}[/green]")
            console.print(Syntax(diff, "diff", theme="github-dark", line_numbers=False))


def _git_diff() -> str:
    """Return `git diff HEAD` output, or empty string if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _print_bug_report(
    plan: dict,
    patch_result: dict,
    gen_result: dict,
    test_result: dict | None,
) -> None:
    """Print the final minimal bug summary report."""
    _divider()
    _header("Bug Report")

    # Bug & root cause
    console.print(f"\n  Bug:  {plan.get('bug_summary', '—')}")
    root_cause = plan.get("root_cause", "")
    if root_cause:
        console.print(f"  Root: {root_cause}")

    # Files modified
    modified = [
        p.get("file_path", "?")
        for p in patch_result.get("results", {}).get("patches", [])
        if p.get("ok")
    ]
    if modified:
        console.print(f"\n  Modified : {', '.join(modified)}")

    # Files created (new test files)
    created = gen_result.get("files_written", [])
    if created:
        console.print(f"  Created  : {', '.join(created)}")

    # Test result
    if test_result:
        status = "[green]passed[/green]" if test_result.get("ok") else "[red]failed[/red]"
        console.print(f"  Tests    : {status} — {test_result.get('summary', '')}")
        if not test_result.get("ok") and test_result.get("output"):
            console.print()
            console.print(Syntax(test_result["output"], "text", theme="github-dark", line_numbers=False))

    # Git diff
    diff = _git_diff()
    if diff:
        _header("git diff HEAD")
        console.print(Syntax(diff, "diff", theme="github-dark", line_numbers=False))

    _divider()


# ─────────────────────────────────────────────────────────────
# CLI commands
# ─────────────────────────────────────────────────────────────

@app.callback()
def main() -> None:
    """BugFix Agent CLI entrypoint."""


@app.command()
def reindex(repo: str = ".") -> None:
    """Reindex source code in ChromaDB for the given repository."""
    repo_root = Path(repo).resolve()
    if not repo_root.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {repo_root}")
        raise typer.Exit(1)
    console.print(f"[dim]Reindexing {repo_root}…[/dim]")
    indexer = RepoIndexer(str(repo_root))
    count = indexer.reindex()
    console.print(f"[green]✓[/green] Indexed {count} chunks.")


@app.command()
def chat(repo: str = ".") -> None:
    """Start an interactive bug-fixing session."""
    repo_root = str(Path(repo).resolve())
    console.print(f"[dim]Indexing repo: {repo_root}[/dim]")
    orchestrator = Orchestrator(repo_root)
    console.print("\n[green]BugFix Agent ready.[/green]  Describe a bug, or type [bold]exit[/bold] to quit.\n")

    while True:
        # ── 1. Get user input ──────────────────────────────────────────
        try:
            user = console.input("[bold cyan]>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user:
            continue
        if user.lower() in {"exit", "quit"}:
            console.print("[dim]Goodbye.[/dim]")
            break

        # ── 2. Thinking loader + agent reply ─────────────────────────────
        try:
            with console.status("[bold dim]Thinking…[/bold dim]", spinner="dots"):
                result = orchestrator.chat_turn(user)
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            continue

        reply = result["reply"]
        plan = result["plan"]

        console.print()
        console.print(Panel(
            reply,
            title="[bold green]🤖 Agent[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))

        # ── 3. No plan yet — stay in conversation ───────────────────────────
        if plan is None:
            continue

        # ── 4. Fix is ready — ask if the user wants to see it ─────────
        console.print()
        if not _ask("Fix ready. Show details? [y/N]"):
            console.print("[dim]  Ok, still discussing.[/dim]\n")
            continue

        _show_patches(plan)
        _show_plan_overview(plan)
        console.print()

        if not _ask("Apply this fix? [y/N]"):
            console.print("[yellow]  Skipped. No files changed.[/yellow]\n")
            continue

        # ── 5a. Apply code patches (retry until success or user skips) ─────
        patch_result: dict = {"results": {"patches": [], "writes": [], "bash": []}}
        patches_applied_ok = False

        if not _ask("\n  Apply code patches? [y/N]"):
            console.print("[dim]  Patches skipped.[/dim]")
        else:
            while True:
                console.print("[dim]  Patching…[/dim]")
                try:
                    patch_result = orchestrator.apply_patches(plan)
                except Exception as exc:
                    console.print(f"[red]  Patch error:[/red] {exc}")
                    patch_result = {"results": {"patches": [], "writes": [], "bash": []}}

                _show_execution_diffs(patch_result)
                for p in patch_result.get("results", {}).get("patches", []):
                    fp = p.get("file_path", "?")
                    if p.get("ok"):
                        console.print(f"  [green]✓[/green]  {fp} patched")
                    else:
                        console.print(f"  [red]✗[/red]  {fp} — {p.get('error', 'failed')}")
                for w in patch_result.get("results", {}).get("writes", []):
                    fp = w.get("file_path", "?")
                    if w.get("ok"):
                        console.print(f"  [green]✓[/green]  {fp} written ({w.get('bytes_written', 0)} bytes)")

                patch_list = patch_result.get("results", {}).get("patches", [])
                all_ok = patch_list and all(p.get("ok") for p in patch_list)
                if all_ok:
                    patches_applied_ok = True
                    break
                if not patch_list:
                    break
                if not _ask("\n  [yellow]Patch application failed. Retry patch application? [y/N][/yellow]"):
                    console.print("[dim]  Stopping. Fix patches and retry later, or run again.[/dim]")
                    break

        if not patches_applied_ok:
            # Skip test generation and test run; go to next turn / report
            orchestrator.record_fix_and_reindex(plan)
            console.print()
            _print_bug_report(plan, patch_result, {"files_written": [], "errors": []}, {})
            console.print()
            continue

        # Run any bash commands gated per-command
        for cmd in plan.get("bash_commands", []):
            if _ask(f"\n  Run bash command `{cmd}`? [y/N]"):
                console.print(f"[dim]  Running: {cmd}[/dim]")
                try:
                    result = subprocess.run(
                        cmd, shell=True, cwd=repo_root,
                        capture_output=True, text=True,
                    )
                    output = (result.stdout + result.stderr).strip()
                    if output:
                        console.print(Syntax(output, "text", theme="github-dark", line_numbers=False))
                    if result.returncode != 0:
                        console.print(f"  [red]✗[/red]  exited {result.returncode}")
                    else:
                        console.print(f"  [green]✓[/green]  ok")
                except Exception as e:
                    console.print(f"  [red]Error:[/red] {e}")
            else:
                console.print(f"  [dim]  Skipped: {cmd}[/dim]")

        # ── 5b. Generate tests ─────────────────────────────────────────
        gen_result: dict = {"files_written": [], "errors": []}
        if _ask("\n  Generate test files? [y/N]"):
            console.print("[dim]  Generating tests…[/dim]")
            try:
                gen_result = orchestrator.generate_tests(plan, patch_result)
            except Exception as exc:
                console.print(f"[red]  Test generation error:[/red] {exc}")
            for fp in gen_result.get("files_written", []):
                console.print(f"  [green]✓[/green]  created {fp}")
            for err in gen_result.get("errors", []):
                console.print(f"  [red]✗[/red]  {err}")
        else:
            console.print("[dim]  Test generation skipped.[/dim]")

        # ── 5c. Run tests ──────────────────────────────────────────────
        test_result: dict | None = None
        if _ask("\n  Run tests? [y/N]"):
            console.print("[dim]  Running pytest…[/dim]")
            try:
                test_result = orchestrator.run_tests()
            except Exception as exc:
                console.print(f"[red]  Test runner error:[/red] {exc}")
        else:
            console.print("[dim]  Tests skipped.[/dim]")

        # ── 6. Record fix context and re-index ─────────────────────────
        orchestrator.record_fix_and_reindex(plan)

        # ── 7. Final bug report ────────────────────────────────────────
        console.print()
        _print_bug_report(plan, patch_result, gen_result, test_result or {})
        console.print()


if __name__ == "__main__":
    app()

"""Validate agent/ with the competition's compiler and package dist/submission.zip.

Run from the repository root:

    uv run --with data/harness_wheels/adk_submission-0.2.13-py3-none-any.whl \
        python scripts/build_submission.py

The scorer compiles agent.yaml with adk_submission's sandboxed compiler, not with
ADK's own config loader, so this script uses that compiler with the scorer's limits.
It checks structure and wiring only. It does not call a model or run a task; the
Kaggle smoke test (notebook section 5) is still the end-to-end check.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from adk_submission import (
    GenerationConstraints,
    ModelRegistry,
    NumericRange,
    SubmissionLimits,
    compile_submission,
    validate_directory,
)
from adk_submission.discovery import discover_declared_models

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = REPO_ROOT / "agent"
OUTPUT_ZIP = REPO_ROOT / "dist" / "submission.zip"

# Files kept in agent/ for reference that are not part of the submission.
EXCLUDED_FILES = {"prompts/system.md"}

# Copied from swegemma 0.2.11 config.py (build_submission_limits and constants).
# swegemma itself is not imported because it pulls in torch and transformers.
MAX_SUBMISSION_SIZE_BYTES = 3 * 1024 * 1024 * 1024
ALLOWED_SUBMISSION_EXTENSIONS = frozenset(
    {".yaml", ".yml", ".md", ".txt", ".py", ".json", ".safetensors"}
)
ALLOWED_ADAPTER_EXTENSIONS = frozenset({".safetensors"})
ALLOWED_MODELS = (
    "gemma-4-31b-it-qat-w4a16-ct",
    "gemma-4-12b-it-qat-w4a16-ct",
    "gemma-4-e4b-it-qat-w4a16-ct",
    "gemma-4-e2b-it-qat-w4a16-ct",
)

# State keys the harness always sets. Any other placeholder must be optional
# ({name?}), because a missing required key raises KeyError at run time.
ALWAYS_PRESENT_STATE_KEYS = {"problem_description"}
# Same pattern ADK 1.36.1 uses in utils/instructions_utils.py.
PLACEHOLDER_PATTERN = re.compile(r"{+[^{}]*}+")


def build_limits() -> tuple[SubmissionLimits, GenerationConstraints]:
    limits = SubmissionLimits(
        max_total_size_bytes=MAX_SUBMISSION_SIZE_BYTES,
        max_yaml_size_bytes=50 * 1024 * 1024,
        max_skill_size_bytes=50 * 1024 * 1024,
        max_file_count=10_000,
        max_yaml_files=1_000,
        max_instruction_chars=1_000_000,
        max_total_instruction_chars=10_000_000,
        max_agents=500,
        max_sub_agent_depth=50,
        max_skills=1_000,
        max_loop_iterations=500,
        allowed_file_extensions=ALLOWED_SUBMISSION_EXTENSIONS,
        adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS,
    )
    gen_constraints = GenerationConstraints(
        allowed_fields=None,
        max_output_tokens=NumericRange(1, 32768),
        thinking_budget=NumericRange(0, 32768),
        defaults={
            "max_output_tokens": 16384,
            "thinking_config": {"thinking_budget": 4096},
        },
    )
    return limits, gen_constraints


def build_stub_tools() -> dict:
    """Stand-ins with the same names and signatures as the nine swegemma tools."""

    def run_command(command: str) -> dict:
        return {}

    def submit_patch() -> dict:
        return {}

    def get_status() -> dict:
        return {}

    def read_file(filepath: str, start_line: int | None = None, end_line: int | None = None) -> dict:
        return {}

    def edit_file(filepath: str, old_string: str, new_string: str, allow_multiple: bool = False) -> dict:
        return {}

    def write_file(filepath: str, content: str) -> dict:
        return {}

    def get_code_neighbors(node: str, edge_type: str | None = None, max_neighbors: int = 50) -> dict:
        return {}

    def search_similar_code(query: str, k: int = 10) -> dict:
        return {}

    def get_code_subgraph(nodes: list[str]) -> dict:
        return {}

    tools = [
        run_command, submit_patch, get_status, read_file, edit_file, write_file,
        get_code_neighbors, search_similar_code, get_code_subgraph,
    ]
    return {tool.__name__: tool for tool in tools}


def build_model_registry() -> ModelRegistry:
    """Register every allowed alias the way VllmServer.create_model_registry does."""
    from google.adk.models.lite_llm import LiteLlm
    from adk_submission.resolvers.generation import install_litellm_reasoning_patch

    install_litellm_reasoning_patch()
    registry = ModelRegistry()
    for alias in ALLOWED_MODELS:
        registry.register(
            alias,
            LiteLlm(model=f"openai/{alias}", api_base="http://localhost:8000/v1", api_key="EMPTY"),
        )
    return registry


def stage_submission(staging_dir: Path) -> None:
    """Copy agent/ into staging_dir, leaving out excluded and hidden files."""
    for source in sorted(AGENT_DIR.rglob("*")):
        relative = source.relative_to(AGENT_DIR)
        if any(part.startswith(".") for part in relative.parts):
            continue  # .DS_Store and similar files fail the extension check
        if relative.as_posix() in EXCLUDED_FILES or source.is_dir():
            continue
        if source.is_symlink():
            sys.exit(f"Symlinks are not permitted: {relative}")
        target = staging_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def iter_agents(agent, depth: int = 0):
    yield agent, depth
    for child in getattr(agent, "sub_agents", None) or []:
        yield from iter_agents(child, depth + 1)


def describe_agent(agent) -> str:
    kind = type(agent).__name__
    parts = [f"{agent.name} ({kind})"]
    if kind == "LoopAgent":
        parts.append(f"max_iterations={agent.max_iterations}")
    if kind == "LlmAgent":
        model = getattr(agent.model, "model", agent.model)
        tool_names = [getattr(t, "name", getattr(t, "__name__", str(t))) for t in agent.tools]
        config = agent.generate_content_config
        thinking = getattr(config, "thinking_config", None) if config else None
        parts.append(f"model={model}")
        parts.append(f"include_contents={agent.include_contents}")
        parts.append(f"output_key={agent.output_key}")
        parts.append(f"max_output_tokens={getattr(config, 'max_output_tokens', None)}")
        parts.append(f"thinking_budget={getattr(thinking, 'thinking_budget', None)}")
        parts.append(f"tools={tool_names}")
    return ", ".join(parts)


def find_unsafe_placeholders(agent) -> list[str]:
    instruction = agent.instruction if isinstance(agent.instruction, str) else ""
    problems = []
    for match in PLACEHOLDER_PATTERN.finditer(instruction):
        name = match.group().lstrip("{").rstrip("}").strip()
        if name.endswith("?") or not name.isidentifier():
            continue  # optional, or not a state placeholder (left as literal text)
        if name not in ALWAYS_PRESENT_STATE_KEYS:
            problems.append(f"{agent.name}: required placeholder {{{name}}} may be missing")
    return problems


def write_zip(staging_dir: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging_dir).as_posix())


def main() -> None:
    limits, gen_constraints = build_limits()

    with tempfile.TemporaryDirectory() as tmp:
        staging_dir = Path(tmp) / "submission"
        staging_dir.mkdir()
        stage_submission(staging_dir)

        validate_directory(staging_dir, limits=limits)

        declared = discover_declared_models(staging_dir)
        if len(declared) != 1:
            sys.exit(f"Expected exactly one declared model, found {sorted(declared)}")
        print(f"Declared model: {declared.pop()}")

        root = compile_submission(
            submission_dir=staging_dir,
            tool_registry=build_stub_tools(),
            model_registry=build_model_registry(),
            limits=limits,
            generation_constraints=gen_constraints,
        )

        print("Compiled agent tree:")
        problems = []
        for agent, depth in iter_agents(root):
            print("  " * (depth + 1) + describe_agent(agent))
            if type(agent).__name__ == "LlmAgent":
                problems.extend(find_unsafe_placeholders(agent))
        if problems:
            sys.exit("\n".join(problems))

        write_zip(staging_dir, OUTPUT_ZIP)

    with zipfile.ZipFile(OUTPUT_ZIP) as archive:
        names = archive.namelist()
    bad = [n for n in names if Path(n).suffix.lower() not in ALLOWED_SUBMISSION_EXTENSIONS]
    if "agent.yaml" not in names or bad:
        sys.exit(f"Bad archive: agent.yaml at root={'agent.yaml' in names}, disallowed={bad}")
    print(f"Wrote {OUTPUT_ZIP.relative_to(REPO_ROOT)} with {len(names)} files:")
    for name in names:
        print(f"  {name}")


if __name__ == "__main__":
    main()

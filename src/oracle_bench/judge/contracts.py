"""Strict contracts for generated-test judgments, and the saved state they define."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from oracle_bench.io import read_json, write_json
from oracle_bench.paths import RunPaths
from oracle_bench.results import HarnessResult, MatrixCellName

RATER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_RATIONALE_LENGTH = 1_000
JUDGMENT_LABELS = {
    "issue_target_alignment": "Issue-target alignment",
    "trigger_alignment": "Trigger alignment",
    "oracle_alignment": "Oracle alignment",
    "test_strategy": "Test strategy",
    "final_verdict": "Final verdict",
}
JUDGMENT_LABEL_KEYS = tuple(JUDGMENT_LABELS)


class JudgeModel(BaseModel):
    """Every persisted judge contract: rejects coercion and undeclared fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class JudgmentLabels(JudgeModel):
    """The six fields requested from either an LLM or human rater."""

    issue_target_alignment: Literal["direct", "partial", "adjacent", "unrelated", "indeterminate"]
    trigger_alignment: Literal[
        "matches", "misses_required_condition", "wrong_path", "not_assessable"
    ]
    oracle_alignment: Literal[
        "behaviorally_aligned",
        "behaviorally_misaligned",
        "implementation_coupled",
        "no_clear_oracle",
        "not_assessable",
    ]
    test_strategy: Literal[
        "return_value_or_status",
        "exception_behavior",
        "state_or_artifact",
        "external_interaction",
        "resource_or_nondeterminism",
        "implementation_inspection",
        "no_meaningful_assertion",
    ]
    final_verdict: Literal[
        "confirmed_issue_reproduction",
        "issue_relevant_not_confirmed",
        "issue_relevant_but_invalid",
        "not_issue_relevant",
        "unassessable",
    ]
    rationale: Annotated[str, Field(max_length=MAX_RATIONALE_LENGTH)]

    @field_validator("rationale")
    @classmethod
    def rationale_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rationale must not be blank")
        return value

    @model_validator(mode="after")
    def labels_must_be_consistent(self) -> JudgmentLabels:
        if self.final_verdict == "confirmed_issue_reproduction" and (
            self.issue_target_alignment != "direct"
            or self.oracle_alignment != "behaviorally_aligned"
        ):
            raise ValueError(
                "confirmed_issue_reproduction requires direct target alignment and a "
                "behaviorally_aligned oracle"
            )
        if self.final_verdict == "not_issue_relevant" and self.issue_target_alignment not in {
            "adjacent",
            "unrelated",
        }:
            raise ValueError("not_issue_relevant requires adjacent or unrelated target alignment")
        if self.final_verdict in {
            "issue_relevant_not_confirmed",
            "issue_relevant_but_invalid",
        } and self.issue_target_alignment not in {"direct", "partial"}:
            raise ValueError(f"{self.final_verdict} requires direct or partial target alignment")
        return self


class CompletedJudgment(JudgmentLabels):
    status: Literal["completed"] = "completed"


class UnsuccessfulJudgment(JudgeModel):
    status: Literal["invalid_output", "failed", "timed_out"]
    error: Annotated[str, Field(min_length=1)]


class StaleJudgment(JudgeModel):
    status: Literal["stale"] = "stale"
    reason: Annotated[str, Field(min_length=1)]
    previous_judgment: CompletedJudgment | UnsuccessfulJudgment


JudgmentResult = Annotated[
    CompletedJudgment | UnsuccessfulJudgment | StaleJudgment,
    Field(discriminator="status"),
]


class ExposedArtifact(JudgeModel):
    source: str
    destination: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PreparedImage(JudgeModel):
    reference: str
    image_id: str
    digests: list[str]


class WorkspaceSpec(JudgeModel):
    prepared_image: PreparedImage
    base_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    repair_patch_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    reference_test_patch_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    rubric_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    workspace_method: Literal["git_worktree", "directory_copy"]
    reconstruction_commands: list[list[str]]
    artifacts: list[ExposedArtifact]


class BundleManifest(JudgeModel):
    artifacts: list[ExposedArtifact]


class JudgeAttempt(HarnessResult):
    """The harness result and execution identity persisted for an automated judge turn."""

    harness: str
    provider: str
    model: str
    harness_version: str
    limit: dict


class HumanWorkspaceMetadata(JudgeModel):
    """Host provenance needed to collect a rating from a named container."""

    container: Annotated[str, Field(min_length=1)]
    rater: Annotated[str, Field(pattern=RATER_ID.pattern)]
    network_mode: Literal["none"] = "none"
    rubric_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    workspace_spec_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Rating(JudgeModel):
    """One saved judgment as the agreement analysis sees it.

    `labels` and `provenance` are absent unless the judgment completed and its
    provenance file was readable. Only human ratings carry provenance.
    """

    status: Literal[
        "completed",
        "missing",
        "invalid_artifact",
        "invalid_output",
        "failed",
        "timed_out",
        "stale",
    ]
    labels: dict[str, str] | None = None
    provenance: HumanWorkspaceMetadata | None = None


class Ratings(JudgeModel):
    """The LLM judge's rating and every human rater's, for one run."""

    llm: Rating
    humans: dict[str, Rating]


class RunEvaluation(JudgeModel):
    """The execution facts a rating is read against. All absent if results are unreadable."""

    submission_compliant: bool | None = None
    buggy_status: str | None = None
    golden_status: str | None = None


class LlmJudgeIdentity(JudgeModel):
    """Which CLI and model produced a run's LLM rating, as its attempt recorded it."""

    harness: str | None = None
    provider: str | None = None
    model: str | None = None
    harness_version: str | None = None


class RunProvenance(JudgeModel):
    """What the LLM judge was shown, hashed so changed conditions stay visible."""

    rubric_sha256: str | None = None
    prompt_sha256: str | None = None
    llm: LlmJudgeIdentity


class RunRatings(JudgeModel):
    """Every rating saved for one run, beside the evidence the raters were given."""

    run_dir: str
    instance_id: str
    matrix: dict[MatrixCellName, int]
    evaluation: RunEvaluation
    ratings: Ratings
    provenance: RunProvenance


_JUDGMENT = TypeAdapter(JudgmentResult)
_ACTIVE_JUDGMENT = TypeAdapter(
    Annotated[CompletedJudgment | UnsuccessfulJudgment, Field(discriminator="status")]
)

_FENCED_JSON = re.compile(r"\A\s*```(?:json)?[ \t]*\r?\n(?P<body>.*?)\r?\n```\s*\Z", re.DOTALL)


def parse_judgment(
    raw: str, *, has_relevant_fail_to_pass: bool
) -> CompletedJudgment | UnsuccessfulJudgment:
    """Parse one bare or fenced JSON object into a stable normalized result."""
    try:
        judgment = CompletedJudgment.model_validate(_extract_json(raw))
        # Execution evidence outranks the rater's claim: nothing can be confirmed
        # reproduced when no generated test actually failed on buggy and passed on golden.
        if (
            judgment.final_verdict == "confirmed_issue_reproduction"
            and not has_relevant_fail_to_pass
        ):
            raise ValueError("confirmed_issue_reproduction requires a relevant F→P result")
        return judgment
    except (json.JSONDecodeError, ValidationError, ValueError) as error:
        return UnsuccessfulJudgment(status="invalid_output", error=str(error))


def failed_judgment(error: str, *, timed_out: bool = False) -> UnsuccessfulJudgment:
    """Represent harness failures without pretending a semantic result exists."""
    return UnsuccessfulJudgment(status="timed_out" if timed_out else "failed", error=error)


def validate_judgment(value: object) -> JudgmentResult:
    """Validate a normalized judgment read from persisted artifacts."""
    return _JUDGMENT.validate_python(value)


def read_judge_attempt(path: Path) -> JudgeAttempt:
    """Validate the saved automated-judge attempt at the report input boundary."""
    return JudgeAttempt.model_validate(read_json(path))


def read_judgment_state(paths: RunPaths) -> dict:
    """Describe one run's saved annotation, including its explicit absent states.

    ``disabled`` and ``missing`` are distinguished by the frozen rubric, which a
    resolved run writes only when judging is configured. An unreadable artifact
    becomes ``invalid_artifact`` so a corrupt file never renders as a judgment.
    """
    if paths.judge.judgment.is_file():
        try:
            return validate_judgment(read_json(paths.judge.judgment)).model_dump()
        except (OSError, ValueError) as error:
            return {"status": "invalid_artifact", "error": str(error)}
    return {"status": "missing" if paths.judge.rubric.is_file() else "disabled"}


def mark_judgments_stale(paths: RunPaths) -> None:
    """Mark every saved judgment stale, the LLM's and every human rater's.

    Call this after replacing evaluation results, since all of them rated the old ones.
    """
    saved = [paths.judge.judgment, *paths.judge.human.judgments.glob("*/judgment.json")]
    for path in saved:
        if not path.is_file():
            continue
        value = read_json(path)
        if value.get("status") == "stale":
            # Already stale from an earlier replacement; keep the original annotation.
            stale = StaleJudgment.model_validate(value)
        else:
            stale = StaleJudgment(
                reason="Paired evaluation evidence changed after this judgment was produced.",
                previous_judgment=_ACTIVE_JUDGMENT.validate_python(value),
            )
        write_json(path, stale.model_dump())


def _extract_json(raw: str) -> dict:
    candidate = raw
    if raw.lstrip().startswith("```"):
        match = _FENCED_JSON.fullmatch(raw)
        if match is None:
            raise ValueError("Expected exactly one JSON object inside one Markdown fence")
        candidate = match.group("body")
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("Judgment output must be a JSON object")
    return value

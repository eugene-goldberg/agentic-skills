"""Graph state and supporting dataclasses."""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class BacklogItem(TypedDict):
    bl_id: str            # e.g. "BL-0001"
    title: str            # heading text after "BL-XXXX:"
    raw: str              # full markdown block for this BL
    status: str           # "Ready", "Backlog", etc.
    dependencies: list[str]
    req_ids: list[str]


class CycleResult(TypedDict, total=False):
    bl_id: str
    eng_run_id: str
    eng_run_dir: str
    eng_decision: str
    eng_score: int
    eng_final_commit: str
    qa_run_id: str
    qa_run_dir: str
    qa_decision: str
    qa_score: int
    qa_unknown_failures: int
    qa_known_bug_failures: int


class GraphState(TypedDict, total=False):
    # --- Inputs (set by initialize) ---
    project_name: str
    workspace_root: str           # absolute path to the agentic-skills workspace
    target_repo_path: str         # absolute path; PO + Engineer + QA all act here
    reference_repo_path: str      # optional curated reference repo for retrieval layer
    project_brief_path: str
    po_skill_source_path: str
    eng_skill_source_path: str
    qa_skill_source_path: str
    po_skill_id: str
    eng_skill_id: str
    qa_skill_id: str
    po_skill_snapshot_path: str
    eng_skill_snapshot_path: str
    qa_skill_snapshot_path: str
    po_skill_sha256: str
    eng_skill_sha256: str
    qa_skill_sha256: str

    # --- PO output ---
    po_run_id: str
    po_run_dir: str
    backlog_path: str
    requirements_path: str
    sprint_plan_path: str
    po_final_report: str

    # --- Backlog iteration ---
    backlog_items: list[BacklogItem]
    current_index: int

    # --- Engineering cycle (current iteration) ---
    eng_run_id: str
    eng_run_dir: str
    eng_packet_path: str
    eng_packet_sha256: str
    eng_baseline_commit: str
    eng_final_commit: str
    eng_agent_report: str
    eng_scorecard_path: str
    eng_decision: str
    eng_score: int

    # --- QA cycle (current iteration) ---
    qa_run_id: str
    qa_run_dir: str
    qa_packet_path: str
    qa_packet_sha256: str
    qa_carry_forward_run_id: Optional[str]
    qa_agent_report: str
    qa_scorecard_path: str
    qa_decision: str
    qa_score: int

    # --- Cumulative ---
    last_eng_commit: str
    completed_cycles: list[CycleResult]

    # --- Control / failure ---
    error: Optional[str]
    next_action: str

"""Collaboration strategies for multi-agent orchestration.

Each strategy defines *how* a workflow step with multiple agents is executed:

- **Sequential**: agents run one after another; output of N feeds into N+1.
- **Parallel**: agents run concurrently; results are collected.
- **Vote**: agents independently answer; majority wins.
"""

import json
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend_business.services.agent.context import AgentContext
from backend_business.services.agent.messaging import message_bus
from backend_business.services.agent.messaging.channel import channel_manager, ChannelType
from backend_business.services.agent.orchestration.workflow import WorkflowStep, StepStatus

logger = logging.getLogger(__name__)


class CollaborationStrategy(ABC):
    """Base class for collaboration strategies."""

    name: str = "base"

    @abstractmethod
    def execute(
        self,
        step: WorkflowStep,
        ctx: AgentContext,
        input_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute the step and return the combined result."""
        ...


class SequentialStrategy(CollaborationStrategy):
    """Run agents one-by-one; each receives the previous agent's output."""

    name = "sequential"

    def execute(
        self,
        step: WorkflowStep,
        ctx: AgentContext,
        input_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        from backend_business.services.agent.runner import AgentRunner

        runner = AgentRunner()
        accumulated = dict(input_data)
        results: List[Dict[str, Any]] = []

        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc)

        for i, agent_id in enumerate(step.agent_ids):
            prompt = (
                f"你是工作流「{step.name}」的第 {i + 1}/{len(step.agent_ids)} 步执行者。\n"
                f"输入数据:\n{json.dumps(accumulated, ensure_ascii=False, indent=2)}"
            )

            try:
                result = runner.run_once(
                    agent_id=agent_id,
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    user_content=prompt,
                    project_id=ctx.project_id,
                    parent_context=ctx,
                )
                results.append(result)
                accumulated[f"step_{i}_{agent_id}"] = result
            except Exception as e:
                logger.error("Sequential step %d (%s) failed: %s", i, agent_id, e)
                step.status = StepStatus.FAILED
                step.error = str(e)
                step.completed_at = datetime.now(timezone.utc)
                return {"status": "failed", "error": str(e), "partial_results": results}

        step.status = StepStatus.COMPLETED
        step.result = accumulated
        step.completed_at = datetime.now(timezone.utc)
        return {"status": "completed", "results": results, "accumulated": accumulated}


class ParallelStrategy(CollaborationStrategy):
    """Run all agents concurrently; collect results."""

    name = "parallel"

    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers

    def execute(
        self,
        step: WorkflowStep,
        ctx: AgentContext,
        input_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        from backend_business.services.agent.runner import AgentRunner

        runner = AgentRunner()
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc)

        prompt = (
            f"你是工作流「{step.name}」的并行执行者。\n"
            f"输入数据:\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"
        )

        def _run(agent_id: str) -> Dict[str, Any]:
            return runner.run_once(
                agent_id=agent_id,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                user_content=prompt,
                project_id=ctx.project_id,
                parent_context=ctx,
            )

        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(_run, aid): aid for aid in step.agent_ids}
            for future in as_completed(futures):
                agent_id = futures[future]
                try:
                    results[agent_id] = future.result()
                except Exception as e:
                    logger.error("Parallel agent %s failed: %s", agent_id, e)
                    errors[agent_id] = str(e)

        if errors and not results:
            step.status = StepStatus.FAILED
            step.error = json.dumps(errors, ensure_ascii=False)
        else:
            step.status = StepStatus.COMPLETED
            step.result = results

        step.completed_at = datetime.now(timezone.utc)
        return {"status": step.status.value, "results": results, "errors": errors}


class VoteStrategy(CollaborationStrategy):
    """Each agent answers independently; majority vote determines the outcome."""

    name = "vote"

    def execute(
        self,
        step: WorkflowStep,
        ctx: AgentContext,
        input_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        # First run all agents in parallel
        parallel = ParallelStrategy()
        parallel_result = parallel.execute(step, ctx, input_data)

        results = parallel_result.get("results", {})
        if not results:
            return parallel_result

        # Collect answers (using content as the "vote")
        votes: Dict[str, int] = {}
        for agent_id, r in results.items():
            answer = r.get("content", "").strip()
            votes[answer] = votes.get(answer, 0) + 1

        # Determine winner
        winner = max(votes, key=votes.get) if votes else ""

        step.result = {
            "winner": winner,
            "votes": votes,
            "individual_results": results,
        }
        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.now(timezone.utc)

        return {
            "status": "completed",
            "winner": winner,
            "votes": votes,
            "individual_results": results,
        }


# Strategy registry
_STRATEGIES: Dict[str, CollaborationStrategy] = {
    "sequential": SequentialStrategy(),
    "parallel": ParallelStrategy(),
    "vote": VoteStrategy(),
}


def get_strategy(name: str) -> CollaborationStrategy:
    """Look up a strategy by name."""
    strategy = _STRATEGIES.get(name)
    if not strategy:
        raise ValueError(f"Unknown collaboration strategy: {name}. Available: {list(_STRATEGIES.keys())}")
    return strategy


def register_strategy(strategy: CollaborationStrategy) -> None:
    """Register a custom strategy."""
    _STRATEGIES[strategy.name] = strategy

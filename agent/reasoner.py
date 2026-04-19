"""
agent/reasoner.py
Core LangChain-based reasoning loop.
  1. Deserialises IncidentContext
  2. Retrieves similar incidents + runbooks from vector store
  3. Builds structured prompt
  4. Calls LLM
  5. Parses and validates response
  6. Returns enriched incident dict
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from .retrieval.knowledge_store import KnowledgeStore
from .prompts.incident_prompt import build_system_prompt, build_human_prompt, parse_agent_response

log = logging.getLogger("agent.reasoner")

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL        = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE  = float(os.getenv("LLM_TEMPERATURE", "0.1"))
MAX_TOKENS       = int(os.getenv("LLM_MAX_TOKENS", "1500"))

# Confidence thresholds
AUTO_EXECUTE_THRESHOLD = float(os.getenv("AUTO_EXECUTE_THRESHOLD", "0.75"))
ESCALATE_THRESHOLD     = float(os.getenv("ESCALATE_THRESHOLD", "0.40"))


class IncidentReasoner:
    """
    Wraps LangChain + knowledge store.
    Stateless: each call is independent.
    """

    def __init__(self) -> None:
        self.llm = ChatOpenAI(
            api_key=OPENAI_API_KEY,
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        self.knowledge = KnowledgeStore()
        log.info("IncidentReasoner initialised (model=%s)", LLM_MODEL)

    async def reason(self, incident_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Main entry point. Takes raw incident dict, returns enriched dict.
        """
        try:
            # Retrieve similar incidents + runbooks
            title   = incident_dict.get("title", "")
            service = incident_dict.get("service", "")
            alerts  = [a.get("alertname", "") for a in incident_dict.get("alerts", [])]

            query = f"{title} {service} {' '.join(alerts)}"
            similar_incidents = self.knowledge.search_incidents(query, k=3)
            runbooks          = self.knowledge.search_runbooks(query, k=2)

            # Build prompt
            system_prompt = build_system_prompt()
            human_prompt  = build_human_prompt(
                incident=incident_dict,
                similar_incidents=similar_incidents,
                runbooks=runbooks,
            )

            # Call LLM
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ]
            response = await self.llm.ainvoke(messages)
            raw_text = response.content

            log.info("LLM responded (%d chars) for incident %s",
                     len(raw_text), incident_dict.get("incident_id"))

            # Parse structured response
            parsed = parse_agent_response(raw_text)

            # Apply policy overrides
            confidence = parsed.get("confidence_score", 0.0)
            requires_approval = (
                parsed.get("requires_approval", True)
                or confidence < AUTO_EXECUTE_THRESHOLD
                or _is_high_impact(incident_dict)
            )
            parsed["requires_approval"] = requires_approval

            # Merge back into incident
            incident_dict.update({
                "incident_type":      parsed.get("incident_type"),
                "probable_root_cause": parsed.get("probable_root_cause"),
                "confidence_score":   confidence,
                "supporting_evidence": parsed.get("supporting_evidence", []),
                "recommended_action": parsed.get("recommended_action"),
                "requires_approval":  requires_approval,
                "status":             "in_triage" if requires_approval else "remediating",
                "raw_llm_response":   raw_text,  # stored for audit, never shown to end-user
            })

            return incident_dict

        except Exception as e:
            log.exception("Reasoning failed for incident %s: %s",
                          incident_dict.get("incident_id"), e)
            incident_dict["status"] = "escalated"
            incident_dict["probable_root_cause"] = f"Reasoning failed: {e}"
            incident_dict["requires_approval"] = True
            incident_dict["confidence_score"] = 0.0
            return incident_dict


def _is_high_impact(incident: dict) -> bool:
    """Flag incidents that should always require human approval."""
    HIGH_IMPACT_NAMESPACES = {"production", "prod", "default"}
    HIGH_SEVERITY = {"critical"}
    return (
        incident.get("namespace", "").lower() in HIGH_IMPACT_NAMESPACES
        or incident.get("severity", "").lower() in HIGH_SEVERITY
    )

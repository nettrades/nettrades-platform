# -*- coding: utf-8 -*-
# =============================================================================
# LEAD GEN AGENT - Lead Scoring & Creation
# =============================================================================
# FILE: src/core/agents/lead_gen_agent.py
#
# PURPOSE:
#   This agent handles lead generation. It analyses job postings and
#   projects to generate and score leads for companies.
#
# KEY FEATURES:
#   - Fetches job postings and projects from Odoo
#   - Identifies potential leads
#   - Scores leads using LLM
#   - Creates leads in Odoo CRM
#
# IMPORTANT:
#   This file was previously a PLACEHOLDER stub. It has been replaced
#   with the full implementation from src/agent/lead_gen_agent.py.
#
# UPDATES (2026-09-29):
#   - LLM is now constructed per-invocation inside generate_leads().
# =============================================================================

import json
import logging
from langgraph.graph import StateGraph, END, START

from tools import make_llm_for_track
from tools.odoo_tools import (
    hr_job_search,
    project_search,
    crm_lead_create,
    crm_lead_search,
)

_logger = logging.getLogger(__name__)


class LeadGenState(dict):
    """
    State carried through the lead generation workflow.

    Keys:
        - source_type: 'job' or 'project'
        - source_id: The ID of the job or project
        - source_data: The job or project data
        - leads: List of generated leads
    """
    pass


def create_lead_gen_agent() -> StateGraph:
    """
    Build and return a compiled lead generation sub-graph.

    The workflow consists of three nodes:
    1. fetch_source - Get the job or project details
    2. generate_leads - Generate leads from the source
    3. create_leads - Create leads in Odoo CRM

    The LLM is constructed per invocation inside generate_leads() based on
    state["inference_track"].

    Returns:
        StateGraph: Compiled LangGraph workflow
    """

    # =========================================================================
    # NODE 1: Fetch Source
    # =========================================================================

    async def fetch_source(state: LeadGenState):
        """
        Fetch the job or project details from Odoo.
        """
        source_type = state.get("source_type", "job")
        source_id = state.get("source_id")

        _logger.info(f"Fetching {source_type} with ID: {source_id}")

        if source_type == "job" and source_id:
            jobs = await hr_job_search([("id", "=", source_id)])
            state["source_data"] = jobs[0] if jobs else {}
            _logger.info(f"Found job: {state['source_data'].get('name', 'Unknown')}")

        elif source_type == "project" and source_id:
            projects = await project_search([("id", "=", source_id)])
            state["source_data"] = projects[0] if projects else {}
            _logger.info(f"Found project: {state['source_data'].get('name', 'Unknown')}")

        else:
            _logger.warning("No valid source provided")
            state["source_data"] = {}

        return state

    # =========================================================================
    # NODE 2: Generate Leads
    # =========================================================================

    async def generate_leads(state: LeadGenState):
        """
        Generate leads from the source using the LLM.

        The LLM is constructed per invocation from the supervisor's track
        selection. Slightly higher temperature for creativity.
        """
        source = state.get("source_data", {})
        source_type = state.get("source_type", "job")

        _logger.info(f"Generating leads from {source_type}")

        # Construct the prompt
        prompt = f"""
        Analyse the following {source_type} and identify potential leads.

        Source: {json.dumps(source, indent=2)}

        For each potential lead, provide:
        1. name (the name of the lead)
        2. description (a brief description of the opportunity)
        3. score (a score from 0-100 indicating lead quality)
        4. reasoning (why this is a good lead)

        Return the leads as a JSON list.
        """

        try:
            llm = make_llm_for_track(
                state.get("inference_track"), temperature=0.2
            )
            response = await llm.ainvoke(prompt)
            _logger.debug(f"LLM response: {response.content}")

            import re
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            if json_match:
                leads = json.loads(json_match.group())
            else:
                leads = json.loads(response.content)

            state["leads"] = leads
            _logger.info(f"Generated {len(leads)} leads")

        except Exception as e:
            _logger.error(f"Lead generation failed: {e}")
            state["leads"] = []

        return state

    # =========================================================================
    # NODE 3: Create Leads
    # =========================================================================

    async def create_leads(state: LeadGenState):
        """
        Create the generated leads in Odoo CRM.
        """
        source = state.get("source_data", {})
        leads = state.get("leads", [])

        _logger.info(f"Creating {len(leads)} leads")

        for lead_data in leads:
            try:
                # Check if a lead with this name already exists
                existing = await crm_lead_search([
                    ("name", "ilike", lead_data.get("name", "")),
                ])

                if existing:
                    _logger.info(f"Lead already exists: {lead_data.get('name')}")
                    continue

                await crm_lead_create({
                    "name": lead_data.get("name", "New Lead"),
                    "description": lead_data.get("description", ""),
                    "expected_revenue": lead_data.get("expected_revenue", 0),
                    "lead_source": f"AI Generated from {source.get('name', 'source')}",
                    "lead_score": lead_data.get("score", 0),
                })
                _logger.info(f"Created lead: {lead_data.get('name')}")

            except Exception as e:
                _logger.error(f"Failed to create lead: {e}")

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(LeadGenState)

    workflow.add_node("fetch_source", fetch_source)
    workflow.add_node("generate_leads", generate_leads)
    workflow.add_node("create_leads", create_leads)

    workflow.add_edge(START, "fetch_source")
    workflow.add_edge("fetch_source", "generate_leads")
    workflow.add_edge("generate_leads", "create_leads")
    workflow.add_edge("create_leads", END)

    return workflow.compile()
# -*- coding: utf-8 -*-
# =============================================================================
# RECRUITMENT AGENT – CV / Job Matching
# =============================================================================
# FILE: src/core/agents/recruitment_agent.py
#
# PURPOSE:
#   This agent handles recruitment-related queries. It analyses job
#   postings, searches for matching candidates, and creates CRM leads
#   for the top matches.
#
# KEY FEATURES:
#   - Fetches job details from Odoo
#   - Searches for candidates (freelancers and job seekers)
#   - Ranks candidates using LLM
#   - Creates CRM leads for top matches
#
# IMPORTANT:
#   This file was previously a PLACEHOLDER stub. It has been replaced
#   with the full implementation from src/agent/recruitment_agent.py.
#
#   The import paths have been updated to point to src.core.tools
#   (where the inference and Odoo tools live).
#
# =============================================================================

import json
import logging
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI

# =============================================================================
# IMPORTS – Updated to point to the correct locations
# =============================================================================
# Note: The tools are now imported from src.core.tools
from ..tools.inference_tools import get_inference_backend
from ..tools.odoo_tools import (
    hr_job_search,
    res_partner_search,
    crm_lead_create,
)

_logger = logging.getLogger(__name__)


class RecruitmentState(dict):
    """
    State carried through the recruitment workflow.

    Keys:
        - job_id: The ID of the job posting
        - job: The job data fetched from Odoo
        - candidates: List of candidate records from Odoo
        - rankings: List of ranked candidates from the LLM
    """
    pass


def create_recruitment_agent() -> StateGraph:
    """
    Build and return a compiled recruitment sub-graph.

    The workflow consists of four nodes:
    1. fetch_job – Get the job details from Odoo
    2. search_candidates – Find matching candidates
    3. rank_candidates – Rank candidates using LLM
    4. create_leads – Create CRM leads for top matches

    Returns:
        StateGraph: Compiled LangGraph workflow
    """
    # Auto-detect the inference backend (GPUStack / vLLM / llama.cpp)
    backend = get_inference_backend()
    _logger.info(f"Recruitment agent using inference backend: {backend.get('base_url', 'unknown')}")

    # Create the LLM client
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,  # Lower temperature for more deterministic results
    )

    # =========================================================================
    # NODE 1: Fetch Job
    # =========================================================================

    async def fetch_job(state: RecruitmentState):
        """
        Fetch the job details from Odoo.

        This node takes a job_id from the state, queries Odoo for the
        job posting, and stores the result in the state.
        """
        job_id = state.get("job_id")
        _logger.info(f"Fetching job with ID: {job_id}")

        if job_id:
            jobs = await hr_job_search([("id", "=", job_id)])
            state["job"] = jobs[0] if jobs else {}
            _logger.info(f"Found job: {state['job'].get('name', 'Unknown')}")
        else:
            _logger.warning("No job_id provided in state")
            state["job"] = {}

        return state

    # =========================================================================
    # NODE 2: Search Candidates
    # =========================================================================

    async def search_candidates(state: RecruitmentState):
        """
        Search for candidates matching the job requirements.

        This node searches for freelancers and job seekers in Odoo.
        In a production implementation, this would also use pgvector
        for semantic similarity search on skills.
        """
        job = state.get("job", {})
        required_skills = job.get("required_skills", "")

        _logger.info(f"Searching for candidates matching skills: {required_skills}")

        # Search for freelancers and job seekers
        # In production, this would use a more sophisticated search
        # with pgvector for skill similarity
        candidates = await res_partner_search([
            ("user_type", "in", ["freelancer", "job_seeker"]),
            # In production, we would filter by skills using pgvector
            # For now, we get all candidates
        ])

        state["candidates"] = candidates
        _logger.info(f"Found {len(candidates)} candidates")

        return state

    # =========================================================================
    # NODE 3: Rank Candidates
    # =========================================================================

    async def rank_candidates(state: RecruitmentState):
        """
        Rank candidates using the LLM.

        This node constructs a prompt with the job description and
        candidate list, sends it to the LLM, and parses the rankings.
        """
        job = state.get("job", {})
        candidates = state.get("candidates", [])

        _logger.info(f"Ranking {len(candidates)} candidates")

        # Limit candidates to avoid token overflow
        MAX_CANDIDATES = 20
        if len(candidates) > MAX_CANDIDATES:
            candidates = candidates[:MAX_CANDIDATES]
            _logger.info(f"Limited to {MAX_CANDIDATES} candidates")

        # Construct the prompt
        prompt = f"""
        Job: {json.dumps(job, indent=2)}

        Candidates: {json.dumps(candidates, indent=2)}

        Rank the candidates by relevance to the job. For each candidate,
        provide:
        1. partner_id (the ID of the candidate)
        2. reasoning (a brief explanation of why they are a good fit)

        Return the top 5 candidates as a JSON list.
        """

        try:
            response = await llm.ainvoke(prompt)
            _logger.debug(f"LLM response: {response.content}")

            # Parse the JSON response
            # The LLM might return the JSON in a code block or with extra text
            content = response.content
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                rankings = json.loads(json_match.group())
            else:
                rankings = json.loads(content)

            state["rankings"] = rankings
            _logger.info(f"Ranked {len(rankings)} candidates")

        except json.JSONDecodeError as e:
            _logger.error(f"Failed to parse LLM response: {e}")
            _logger.debug(f"Response content: {response.content}")
            state["rankings"] = []

        except Exception as e:
            _logger.error(f"Ranking failed: {e}")
            state["rankings"] = []

        return state

    # =========================================================================
    # NODE 4: Create Leads
    # =========================================================================

    async def create_leads(state: RecruitmentState):
        """
        Create CRM leads for the top candidates.

        This node iterates through the ranked candidates and creates
        a CRM lead in Odoo for each one.
        """
        job = state.get("job", {})
        rankings = state.get("rankings", [])

        _logger.info(f"Creating leads for {len(rankings)} candidates")

        for match in rankings:
            try:
                await crm_lead_create({
                    "name": f"Match for {job.get('name', 'Unknown Job')}: "
                            f"{match.get('reasoning', '')[:50]}",
                    "partner_id": match.get("partner_id"),
                    "description": match.get("reasoning", ""),
                    "type": "lead",
                })
                _logger.info(f"Created lead for candidate {match.get('partner_id')}")
            except Exception as e:
                _logger.error(f"Failed to create lead: {e}")

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(RecruitmentState)

    # Add nodes
    workflow.add_node("fetch_job", fetch_job)
    workflow.add_node("search_candidates", search_candidates)
    workflow.add_node("rank_candidates", rank_candidates)
    workflow.add_node("create_leads", create_leads)

    # Add edges
    workflow.add_edge(START, "fetch_job")
    workflow.add_edge("fetch_job", "search_candidates")
    workflow.add_edge("search_candidates", "rank_candidates")
    workflow.add_edge("rank_candidates", "create_leads")
    workflow.add_edge("create_leads", END)

    return workflow.compile()
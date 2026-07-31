# -*- coding: utf-8 -*-
# =============================================================================
# FREELANCE AGENT - Project / Freelancer Matching
# =============================================================================
# FILE: src/core/agents/freelance_agent.py
#
# PURPOSE:
#   This agent handles freelance-related queries. It matches freelancers
#   to projects based on skills, availability, and rates.
#
# KEY FEATURES:
#   - Fetches project details from Odoo
#   - Searches for matching freelancers
#   - Ranks freelancers using LLM
#   - Creates project matches in Odoo
#
# IMPORTANT:
#   This file was previously a PLACEHOLDER stub. It has been replaced
#   with the full implementation from src/agent/freelance_agent.py.
#
# =============================================================================

import json
import logging
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI

from tools import get_inference_backend
from tools.odoo_tools import (
    project_search,
    res_partner_search,
    project_match_create,
)

_logger = logging.getLogger(__name__)


class FreelanceState(dict):
    """
    State carried through the freelance workflow.

    Keys:
        - project_id: The ID of the project
        - project: The project data fetched from Odoo
        - freelancers: List of freelancer records from Odoo
        - rankings: List of ranked freelancers from the LLM
    """
    pass


def create_freelance_agent() -> StateGraph:
    """
    Build and return a compiled freelance sub-graph.

    The workflow consists of four nodes:
    1. fetch_project - Get the project details from Odoo
    2. search_freelancers - Find matching freelancers
    3. rank_freelancers - Rank freelancers using LLM
    4. create_matches - Create project matches in Odoo

    Returns:
        StateGraph: Compiled LangGraph workflow
    """
    # Auto-detect the inference backend
    backend = get_inference_backend()
    _logger.info(f"Freelance agent using inference backend: {backend.get('base_url', 'unknown')}")

    # Create the LLM client
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    # =========================================================================
    # NODE 1: Fetch Project
    # =========================================================================

    async def fetch_project(state: FreelanceState):
        """
        Fetch the project details from Odoo.
        """
        project_id = state.get("project_id")
        _logger.info(f"Fetching project with ID: {project_id}")

        if project_id:
            projects = await project_search([("id", "=", project_id)])
            state["project"] = projects[0] if projects else {}
            _logger.info(f"Found project: {state['project'].get('name', 'Unknown')}")
        else:
            _logger.warning("No project_id provided in state")
            state["project"] = {}

        return state

    # =========================================================================
    # NODE 2: Search Freelancers
    # =========================================================================

    async def search_freelancers(state: FreelanceState):
        """
        Search for freelancers matching the project requirements.
        """
        project = state.get("project", {})
        required_skills = project.get("required_skills", "")

        _logger.info(f"Searching for freelancers matching skills: {required_skills}")

        # Search for active freelancers
        freelancers = await res_partner_search([
            ("user_type", "=", "freelancer"),
            ("is_active", "=", True),
        ])

        state["freelancers"] = freelancers
        _logger.info(f"Found {len(freelancers)} freelancers")

        return state

    # =========================================================================
    # NODE 3: Rank Freelancers
    # =========================================================================

    async def rank_freelancers(state: FreelanceState):
        """
        Rank freelancers using the LLM.
        """
        project = state.get("project", {})
        freelancers = state.get("freelancers", [])

        _logger.info(f"Ranking {len(freelancers)} freelancers")

        # Limit freelancers to avoid token overflow
        MAX_FREELANCERS = 20
        if len(freelancers) > MAX_FREELANCERS:
            freelancers = freelancers[:MAX_FREELANCERS]
            _logger.info(f"Limited to {MAX_FREELANCERS} freelancers")

        # Construct the prompt
        prompt = f"""
        Project: {json.dumps(project, indent=2)}

        Freelancers: {json.dumps(freelancers, indent=2)}

        Rank the freelancers by relevance to the project. For each freelancer,
        provide:
        1. partner_id (the ID of the freelancer)
        2. reasoning (a brief explanation of why they are a good fit)
        3. suggested_rate (a suggested hourly rate for this project)

        Return the top 5 freelancers as a JSON list.
        """

        try:
            response = await llm.ainvoke(prompt)
            _logger.debug(f"LLM response: {response.content}")

            import re
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            if json_match:
                rankings = json.loads(json_match.group())
            else:
                rankings = json.loads(response.content)

            state["rankings"] = rankings
            _logger.info(f"Ranked {len(rankings)} freelancers")

        except Exception as e:
            _logger.error(f"Ranking failed: {e}")
            state["rankings"] = []

        return state

    # =========================================================================
    # NODE 4: Create Matches
    # =========================================================================

    async def create_matches(state: FreelanceState):
        """
        Create project matches for the top freelancers.
        """
        project = state.get("project", {})
        rankings = state.get("rankings", [])

        _logger.info(f"Creating matches for {len(rankings)} freelancers")

        for match in rankings:
            try:
                await project_match_create({
                    "project_id": project.get("id"),
                    "freelancer_id": match.get("partner_id"),
                    "match_score": match.get("score", 0),
                    "suggested_rate": match.get("suggested_rate", 0),
                    "status": "proposed",
                })
                _logger.info(f"Created match for freelancer {match.get('partner_id')}")
            except Exception as e:
                _logger.error(f"Failed to create match: {e}")

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(FreelanceState)

    workflow.add_node("fetch_project", fetch_project)
    workflow.add_node("search_freelancers", search_freelancers)
    workflow.add_node("rank_freelancers", rank_freelancers)
    workflow.add_node("create_matches", create_matches)

    workflow.add_edge(START, "fetch_project")
    workflow.add_edge("fetch_project", "search_freelancers")
    workflow.add_edge("search_freelancers", "rank_freelancers")
    workflow.add_edge("rank_freelancers", "create_matches")
    workflow.add_edge("create_matches", END)

    return workflow.compile()
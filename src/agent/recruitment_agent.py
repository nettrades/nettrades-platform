# =============================================================================
# Recruitment Agent – matches candidates to job postings.
# =============================================================================
# This agent is a LangGraph sub-graph.  It receives a job ID, searches for
# matching freelancers/job-seekers, calls the LLM for ranking, and creates
# CRM leads for the top matches.
# =============================================================================
import json, logging
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from ..tools.inference_tools import get_inference_backend
from ..tools.odoo_tools import hr_job_search, res_partner_search, crm_lead_create

_logger = logging.getLogger(__name__)

class RecruitmentState(dict):
    """State carried through the recruitment workflow."""
    pass


def create_recruitment_agent() -> StateGraph:
    """Build and return a compiled recruitment sub-graph."""

    backend = get_inference_backend()
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    async def fetch_job(state: RecruitmentState):
        job_id = state.get("job_id")
        if job_id:
            jobs = await hr_job_search([("id", "=", job_id)])
            state["job"] = jobs[0] if jobs else {}
        return state

    async def search_candidates(state: RecruitmentState):
        job = state.get("job", {})
        required_skills = job.get("required_skills", "")
        # Search freelancers/job-seekers with matching skills (simplified)
        candidates = await res_partner_search([("user_type", "in", ["freelancer", "job_seeker"])])
        state["candidates"] = candidates
        return state

    async def rank_candidates(state: RecruitmentState):
        job = state.get("job", {})
        candidates = state.get("candidates", [])
        prompt = f"Job: {json.dumps(job)}\nCandidates: {json.dumps(candidates)}\nRank by relevance and return top 5 as JSON list of partner_id and reasoning."
        response = await llm.ainvoke(prompt)
        try:
            rankings = json.loads(response.content)
        except json.JSONDecodeError:
            rankings = []
        state["rankings"] = rankings
        return state

    async def create_leads(state: RecruitmentState):
        for match in state.get("rankings", []):
            await crm_lead_create({
                "name": f"Match for {state['job'].get('name','Unknown')}: {match.get('reasoning','')}",
                "partner_id": match.get("partner_id"),
                "description": match.get("reasoning", ""),
            })
        return state

    workflow = StateGraph(RecruitmentState)
    workflow.add_node("fetch_job", fetch_job)
    workflow.add_node("search_candidates", search_candidates)
    workflow.add_node("rank_candidates", rank_candidates)
    workflow.add_node("create_leads", create_leads)
    workflow.add_edge(START, "fetch_job")
    workflow.add_edge("fetch_job", "search_candidates")
    workflow.add_edge("search_candidates", "rank_candidates")
    workflow.add_edge("rank_candidates", "create_leads")
    workflow.add_edge("create_leads", END)
    return workflow.compile()
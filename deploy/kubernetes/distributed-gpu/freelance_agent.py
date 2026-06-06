# =============================================================================
# Freelance Agent – matches freelancers to projects, generates proposals.
# =============================================================================
import json, logging
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from ..tools.inference_tools import get_inference_backend
from ..tools.odoo_tools import project_search, res_partner_search

_logger = logging.getLogger(__name__)

class FreelanceState(dict):
    pass


def create_freelance_agent() -> StateGraph:
    backend = get_inference_backend()
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    async def fetch_project(state: FreelanceState):
        project_id = state.get("project_id")
        if project_id:
            projects = await project_search([("id", "=", project_id)])
            state["project"] = projects[0] if projects else {}
        return state

    async def find_freelancers(state: FreelanceState):
        freelancers = await res_partner_search([("user_type", "=", "freelancer")])
        state["freelancers"] = freelancers
        return state

    async def generate_proposal(state: FreelanceState):
        project = state.get("project", {})
        freelancer = state.get("selected_freelancer", {})
        prompt = f"Project: {json.dumps(project)}\nFreelancer: {json.dumps(freelancer)}\nGenerate a proposal draft."
        response = await llm.ainvoke(prompt)
        state["proposal_draft"] = response.content
        return state

    workflow = StateGraph(FreelanceState)
    workflow.add_node("fetch_project", fetch_project)
    workflow.add_node("find_freelancers", find_freelancers)
    workflow.add_node("generate_proposal", generate_proposal)
    workflow.add_edge(START, "fetch_project")
    workflow.add_edge("fetch_project", "find_freelancers")
    workflow.add_edge("find_freelancers", "generate_proposal")
    workflow.add_edge("generate_proposal", END)
    return workflow.compile()
# Building LangGraph Agents

This guide explains how to create new LangGraph sub-agents for the NETTRADES.AI platform. Agents are specialised AI workflows that handle specific business domains.

---

## Overview

LangGraph agents are self-contained workflows that:

- **Receive input** from the supervisor (user messages, state data)
- **Process data** using LLMs and Odoo tools
- **Return structured results** back to the supervisor

Agents are ideal for tasks like:

- Analysing CVs and matching candidates to jobs
- Matching freelancers to projects
- Generating and scoring leads
- Managing GPU clusters
- Analysing images with VLM
- Planning robotic actions

---

## Where Agents Live

All agents live in `src/core/agents/`:

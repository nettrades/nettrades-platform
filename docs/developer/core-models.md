# Core Models Reference

This document provides a comprehensive reference for all custom Odoo models in the NETTRADES.AI platform.

---

## Overview

The NETTRADES.AI platform extends Odoo's standard models with custom functionality. This page documents all custom models, their fields, relationships, and usage.

---

## User & Profile Models

### `res.partner` (Extended)

The standard Odoo partner model is extended with NETTRADES-specific fields.

**Additional Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `user_type` | Selection | `job_seeker`, `freelancer`, `company`, `partner` |
| `professional_summary` | Text | Brief professional background |
| `skill_ids` | Many2many (`nettrades.skill`) | Skills possessed |
| `resume_pdf` | Binary | CV / Resume upload |
| `hourly_rate` | Float | Rate for expert sessions |
| `forgejo_username` | Char | Forgejo Git username |
| `github_username` | Char | GitHub username |
| `blog_url` | Char | Personal website |
| `latitude` / `longitude` | Float | Geolocation for matching |
| `is_online` | Boolean | Online status |
| `last_seen` | Datetime | Last activity |
| `charge_rate` | Float | Per-minute rate for sessions |
| `reputation_points` | Integer | Total reputation |
| `can_charge` | Boolean | Can charge for sessions |
| `onboarding_step` | Selection | Onboarding progress |
| `profile_completeness` | Integer | Profile completion percentage |
| `average_rating` | Float (computed) | Average review rating |
| `experience_ids` | One2many (`nettrades.experience`) | Work history |
| `review_ids` | One2many (`nettrades.review`) | Received reviews |

**Relationships:**

- `experience_ids` → `nettrades.experience` (work history)
- `review_ids` → `nettrades.review` (received reviews)
- `skill_ids` → `nettrades.skill` (skills)
- `qualified_professional_ids` → `qualified.professional` (qualifications)
- `user_field_reputation_ids` → `user_field_reputation` (reputation per field)

---

### `nettrades.experience` – Work Experience

**Purpose:** Stores a user's professional work history. Each record represents a single job or role.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `partner_id` | Many2one (`res.partner`) | The user who owns this experience. Required, cascade on delete. |
| `job_title` | Char | The job title (e.g., "Senior Python Developer"). Required. |
| `company` | Char | The employer name. Required. |
| `start_date` | Date | The start date of the role. Required. |
| `end_date` | Date | The end date; empty if current position. |
| `description` | Text | Responsibilities and achievements. |
| `is_current` | Boolean (computed) | `True` if `end_date` is empty. |

**Usage:** Used in the onboarding wizard to collect experience, and displayed on user profiles.

**Example Record:**

```json
{
    "partner_id": 123,
    "job_title": "Senior Python Developer",
    "company": "Acme Corp",
    "start_date": "2022-01-01",
    "end_date": null,
    "description": "Led development of AI-powered recruitment platform..."
}
```


## nettrades.review – User Reviews

Purpose: Stores ratings and comments about a user's work, typically for completed projects.

Fields:
| Field | Type | Description |
|-------|------|-------------|
| `reviewer_id` | Many2one (`res.partner`) | The reviewer. Required. |
| `reviewed_partner_id` | Many2one (`res.partner`) | The user being reviewed. Required. |
| `project_id` | Many2one (`project.project`) | The project this review is linked to (optional). |
| `rating` | Integer | Score from 1 to 5. Required. |
| `comment` | Text | Written feedback. |
| `create_date` | Datetime | Timestamp when the review was created. |


### Constraints:

    Rating must be between 1 and 5.

    Reviewer cannot be the same as the reviewed partner.

Usage: After a project is completed, both parties are prompted to leave a review. The average rating is computed on the partner.

### Example Record:
```json

{
    "reviewer_id": 456,
    "reviewed_partner_id": 123,
    "project_id": 789,
    "rating": 5,
    "comment": "Excellent work! Delivered ahead of schedule."
}
```

## Field & Qualification Models
### nettrades.field – Professional Field

Purpose: Represents a domain of expertise (e.g., "Cardiology", "Python Development").

Fields: See the full list in the Professional Field Model documentation.

Relationships:

    One-to-many with user_field_reputation

    One-to-many with good_answer_vote

    One-to-many with ft_dataset

    One-to-many with qualified_professional

### qualified.professional – Verified Experts

Purpose: Explicitly verified professionals for restricted fields.

Fields:
Field	Type	Description
partner_id	Many2one (res.partner)	The verified professional
field_id	Many2one (nettrades.field)	The field they are qualified in
is_active	Boolean	Whether the qualification is active
verified_at	Datetime	When the user was verified


### user_field_reputation – Reputation per Field

Purpose: Tracks reputation points per user per field.

Fields:
Field	Type	Description
partner_id	Many2one (res.partner)	The user
field_id	Many2one (nettrades.field)	The field
reputation_points	Integer	Current reputation
can_charge	Boolean	Can charge in this field
updated_at	Datetime	Last update timestamp

#### Cron Jobs:

    _cron_decay_reputation() – Daily 1% decay for inactive experts

    _cron_auto_qualify_by_karma() – Auto-promote high-reputation users

    _cron_auto_adjust_weights() – Auto-adjust voting weights

## Good Answer & Fine-Tuning Models

### good.answer.vote – Good Answer Vote

Purpose: Records user votes on answers (AI-generated or human).

Fields:
Field	Type	Description
user_id	Many2one (res.partner)	The voter
answer_id	Integer	ID of the answer being voted on
answer_model	Char	Model of the answer
answerer_id	Many2one (res.partner)	Who provided the answer
field_id	Many2one (nettrades.field)	The professional field
points	Integer	Weighted point value
is_qualified_vote	Boolean	True if voter is a qualified professional
processed_for_ai	Boolean	True if exported for training

### llm.feedback – Training Data

Purpose: Stores (question, answer) pairs extracted from Good Answer votes.

Fields:
Field	Type	Description
vote_id	Many2one (good.answer.vote)	Source vote
field_id	Many2one (nettrades.field)	The professional field
input_text	Text	User's question
output_text	Text	AI's answer
weight	Float	Weighted point value
processed	Boolean	True if exported to dataset

### ft.dataset – Fine-Tuning Dataset

Purpose: Collection of feedback records for a field.

Fields:
Field	Type	Description
field_id	Many2one (nettrades.field)	The professional field
name	Char	Dataset name
description	Text	Dataset description
file_uri	Char	Path to JSONL file
record_count	Integer	Number of records

### ft.training.job – Training Job

Purpose: Tracks fine-tuning jobs submitted to NVIDIA Dynamo.

Fields:
Field	Type	Description
dataset_id	Many2one (ft.dataset)	Source dataset
field_id	Many2one (nettrades.field)	The field being fine-tuned
provider	Char	unsloth or axolotl
base_model	Char	Base model name
fine_tuned_model_id	Char	Resulting model ID
status	Selection	pending, running, completed, failed
hyperparameters	JSONB	Training hyperparameters
metrics	JSONB	Training metrics

### Expert Help Models
#### expert.session – Consultation Session

Purpose: Represents a live consultation between requester and expert.

Fields: See the Ask Someone documentation.

### escrow.hold – Escrow Audit

Purpose: Audit trail for Stripe escrow holds.

Fields:
Field	Type	Description
session_id	Many2one (expert.session)	The session
amount	Float	Amount held
currency	Char	Currency code
provider	Char	stripe
provider_hold_id	Char	Stripe payment intent ID
status	Selection	held, released

### GPU Management Models
#### gpu.cluster – GPU Cluster

Purpose: Represents a company's GPU cluster.

Fields: See the GPU Administration documentation.

#### gpu.node – GPU Node

Purpose: Represents a single GPU machine in a cluster.

Fields: See the GPU Administration documentation.
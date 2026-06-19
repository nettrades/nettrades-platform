
---

## File: `docs/user/ask-someone.md` (With Sequence Diagram)

```markdown
# Ask Someone – Expert Help Marketplace

This guide covers how to request help from verified professionals and how to become an expert.

---

## Overview

**"Ask Someone"** is a real-time expert help marketplace. When you need a second opinion, specialised knowledge, or human verification, you can request help from a verified professional.

| User Type | What You Can Do |
|-----------|-----------------|
| **Requester** | Request help, chat with experts, pay via escrow |
| **Expert** | Offer help, accept sessions, earn money |

---

## Complete "Ask Someone" Flow

This sequence diagram shows the entire flow from request to payment:

```mermaid
sequenceDiagram
    autonumber
    participant User as 👤 User
    participant UI as 💻 Website UI
    participant API as 🔌 API Controller
    participant LLM as 🧠 LangGraph
    participant Match as 📊 Matcher
    participant Stripe as 💳 Stripe
    participant Expert as 👤 Expert
    participant Bus as 📡 Odoo Bus

    User->>UI: 1. Clicks "Ask Someone"
    UI->>API: 2. POST /request (question + context)
    API->>LLM: 3. Infer field from question
    LLM-->>API: 4. field_id
    API->>Match: 5. Find matching experts
    Match-->>API: 6. Top 5 experts
    API->>Stripe: 7. Create Payment Intent (manual capture)
    Stripe-->>API: 8. escrow_id
    API->>API: 9. Create expert.session record
    API-->>UI: 10. Return session_id + expert list

    UI->>Expert: 11. Expert receives notification
    Expert->>API: 12. POST /session/<id>/accept
    API->>Bus: 13. Notify requester (session accepted)
    Bus-->>UI: 14. Real-time notification

    User->>UI: 15. Chat message
    UI->>API: 16. POST /session/<id>/message
    API->>Bus: 17. Broadcast message
    Bus-->>Expert: 18. Real-time message

    User->>UI: 19. Click "Complete Session"
    UI->>API: 20. POST /session/<id>/complete
    API->>Stripe: 21. Capture payment
    Stripe-->>API: 22. Payment captured
    API->>API: 23. Create invoice (platform fee + expert earnings)
    API->>Bus: 24. Notify both parties

    User->>UI: 25. Rate expert
    Expert->>UI: 26. Rate requester
    UI->>API: 27. POST /session/<id>/rate
    API->>API: 28. Update reputations
    API-->>UI: 29. Success
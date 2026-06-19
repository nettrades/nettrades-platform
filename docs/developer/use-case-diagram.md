# USER PERSPECTIVE — Use Case Diagram

Purpose: Shows how different types of users interact with the platform and what business capabilities are available to each role.

---

## Use Case Diagram

```mermaid
flowchart TD
    subgraph Users["?? User Types"]
        Guest["Guest / Unauthenticated<br>????????????????<br>• Website Visitor<br>• Job Seeker"]
        Member["Registered Member<br>????????????????<br>• Has Odoo Account<br>• Basic Profile"]
        Expert["Verified Expert<br>????????????????<br>• Qualified in Fields<br>• Can Answer Questions"]
        Freelancer["Freelancer<br>????????????????<br>• Offers Services<br>• Has Portfolio"]
        Client["Client / Company<br>????????????????<br>• Posts Jobs/Projects<br>• Hires Talent"]
        Admin["System Administrator<br>????????????????<br>• Full System Control"]
    end

    subgraph System["?? NETTRADES.AI Platform"]
        direction TB
        
        subgraph PublicFeatures["?? Public Features"]
            BrowseJobs["Browse Job Postings"]
            BrowseFreelancers["Browse Freelancers"]
            ReadForum["Read Forum / Knowledge Base"]
            Register["Register Account"]
        end

        subgraph MemberFeatures["?? Member Features"]
            PostJob["Post Job Opening"]
            PostProject["Post Freelance Project"]
            ApplyJob["Apply to Job"]
            BidProject["Bid on Project"]
            AskQuestion["Ask a Question (Free)"]
            VoteAnswer["Vote on Answers (Good Answer)"]
            ViewReputation["View Reputation Score"]
            InitiateConsultation["Initiate Paid Consultation"]
        end

        subgraph ExpertFeatures["? Expert Features"]
            AnswerQuestion["Answer Questions"]
            EarnReputation["Earn Reputation Points"]
            ReceiveConsultation["Receive Consultation Request"]
            GetPaid["Get Paid (Stripe Escrow)"]
        end

        subgraph AdminFeatures["?? Admin Features"]
            ManageFields["Manage Professional Fields"]
            ManageGPU["Manage GPU Nodes & Cluster"]
            ManageFineTuning["Manage Fine-Tuning Pipeline"]
            ViewMetrics["View System Metrics & Logs"]
            ManageUsers["Manage Users & Roles"]
            ConfigureLLM["Configure LLM Providers"]
        end
    end

    Guest --> BrowseJobs
    Guest --> BrowseFreelancers
    Guest --> ReadForum
    Guest --> Register

    Member --> PostJob
    Member --> PostProject
    Member --> ApplyJob
    Member --> BidProject
    Member --> AskQuestion
    Member --> VoteAnswer
    Member --> ViewReputation
    Member --> InitiateConsultation

    Expert --> AnswerQuestion
    Expert --> EarnReputation
    Expert --> ReceiveConsultation
    Expert --> GetPaid

    Admin --> ManageFields
    Admin --> ManageGPU
    Admin --> ManageFineTuning
    Admin --> ViewMetrics
    Admin --> ManageUsers
    Admin --> ConfigureLLM

    classDef guest fill:#e3f2fd,stroke:#1565c0;
    classDef member fill:#e8f5e9,stroke:#2e7d32;
    classDef expert fill:#fff3e0,stroke:#e65100;
    classDef admin fill:#fce4ec,stroke:#c62828;
    classDef system fill:#f3e5f5,stroke:#6a1b9a;

    class Guest guest;
    class Member member;
    class Expert expert;
    class Admin admin;
    class System system;
# User FAQ – Frequently Asked Questions

This page answers common questions from end‑users (companies, freelancers, job‑seekers, and experts).

---

## General

### What is NETTRADES.AI?

NETTRADES.AI is an autonomous enterprise platform that connects companies, freelancers, job‑seekers, researchers, partners, and customers. It uses AI to match talent to opportunities, manages a distributed GPU marketplace, and provides expert help through "Ask Someone".

### Is my data safe?

Yes. Your data is stored securely. For companies running the platform on their own infrastructure, data never leaves their control. For public users, we use industry‑standard encryption and access controls. Read our [Privacy Policy](/governance/privacy) for more details.

### How do I create an account?

Click **Sign Up** on the homepage, choose your role (Company, Freelancer, Job Seeker, Researcher, or Expert), fill in your details, and verify your email. You can also sign up using your LinkedIn or GitHub account.

---

## Jobs & Matching

### How does AI job matching work?

Our LangGraph agents analyse job descriptions and candidate profiles (CVs, skills, experience) to compute a match score. The algorithm considers skills, experience, location, availability, and reputation. You can see the reasoning behind each match.

### Can I post a job for free?

Yes, posting jobs is free for registered companies. You only pay when you hire through our platform (success fee applies for external hires via the global network).

### How do I apply for a job?

Browse jobs, click **Apply Now**, review the AI‑generated cover letter, edit if needed, and submit. Your application is sent instantly.

### What happens after I apply?

The employer receives your application. They may shortlist you, invite you for an interview, or reject your application. You'll receive notifications on your dashboard.

### How do I find freelancers?

Post a project with a description, required skills, and budget. The AI will recommend suitable freelancers. You can also browse the freelancer directory.

---

## Ask Someone (Expert Help)

### What is "Ask Someone"?

"Ask Someone" lets you request paid help from verified professionals. You describe your question, the AI infers the field, matches you with experts, and you chat with them in real‑time. Payment is held in escrow until you're satisfied.

### How much does it cost?

The expert sets their rate (per minute or per session). The platform adds a configurable fee (default 15%). You are only charged after the session completes and you confirm satisfaction.

### How do I become an expert?

You need to be verified by an administrator. You must have sufficient reputation in your field and sign the Expert Agreement. Once verified, you can accept sessions and earn money.

### Are my questions private?

Yes. Only the expert sees your question. If the administrator enables training, only the expert's answer is used to improve the AI – your question is never stored.

---

## GPU Marketplace

### How do I share my GPU?

Download the GPU agent installer from the GPU Manager, run it on your GPU machine, and follow the instructions. The agent auto‑detects your GPU, registers with the network, and you can start sharing. You earn tokens for every inference request processed on your GPU.

### Can I use my GPU while sharing?

Yes. The agent runs in the background. You can continue using your GPU for your own work; the sharing only uses idle capacity.

### How do I rent GPU capacity?

Go to the GPU Marketplace, choose your requirements (GPU type, memory, duration), and pay with tokens or credit card. Your job runs on the distributed network.

### What are tokens?

Tokens are the platform's currency. You earn tokens by sharing GPUs or contributing "Good Answers". You spend tokens to access AI features, rent GPUs, or post jobs to the global network.

### How do I earn tokens?

- Share idle GPUs
- Receive "Good Answer" votes on your contributions
- Refer new users
- Complete expert sessions (as an expert)

### How do I check my token balance?

Go to your dashboard → **Token Balance**. You'll see your current balance and transaction history.

---

## Account & Profile

### How do I update my profile?

Log in, go to **My Account** → **Profile**. You can edit your details, upload a CV, add skills, and link your LinkedIn/GitHub.

### How do I change my password?

Go to **My Account** → **Security** → **Change Password**.

### I forgot my password. What do I do?

Click **Forgot Password** on the login page, enter your email, and follow the reset link.

### How do I delete my account?

Contact support at [support@nettrades.ai](mailto:support@nettrades.ai) to request account deletion.

---

## Reputation & Voting

### What is a "Good Answer" vote?

When you see a helpful answer (AI‑generated or human), you can click **Good Answer**. This increases the answerer's reputation and helps improve the AI through fine‑tuning.

### How is reputation calculated?

Reputation is field‑specific. Each vote gives points (weighted more if you're a qualified professional). Reputation decays 1% daily if you're inactive for 30+ days. High reputation unlocks the ability to charge for expert sessions.

### How do I become a qualified professional?

You can be manually verified by an administrator, or you can be automatically promoted when your reputation exceeds the field's threshold (if `auto_karma_qualify` is enabled).

---

## Billing & Payments

### How do I pay for services?

For "Ask Someone", payment is held in escrow via Stripe. For GPU rentals, you pay with tokens or credit card. You can top up your token balance via the **Billing** section.

### What payment methods are accepted?

We accept credit/debit cards (Visa, Mastercard, Amex) via Stripe. Token purchases also support these methods.

### How do I get paid as an expert?

After a session, the client captures the payment. The platform deducts its fee and transfers the remaining amount to your connected Stripe account. Payouts are processed according to the schedule (daily, weekly, or monthly).

---

## Support

### How do I get help?

- Check the [User Documentation](/user/)
- Browse the [FAQ](/user/faq) (this page)
- Contact support at [support@nettrades.ai](mailto:support@nettrades.ai)
- Join our community on [Discord](https://discord.gg/nettrades)

---

## Next Steps

- [Getting Started](/user/getting-started)
- [Job Matching](/user/job-matching)
- [Ask Someone](/user/ask-someone)
- [GPU Marketplace](/user/gpu-marketplace)
# CostGuard

## 1. Team Details

**Team Name / ID:** Vibing agents

**Team Lead:** K Sai Charan

**Team Members:**

<!--
One line per person, including the team lead. Role is optional.
Pick one, combine two, write your own, or leave it blank:
  Agent Whisperer (agents, prompts, LLMs)
  Backend Developer
  Frontend Developer
  UI/UX Designer
  Integrations Engineer (APIs, tools, connecting services)
  Data Engineer (data, databases, retrieval)
  Product & Pitch Lead (idea, presentation, demo)
  Cool Team Member (a bit of everything)
-->

- K Sai Charan | Team Lead
- T Lokesh |
- J Varun | 
- Ch Vivekananda Reddy |

**Repo Link (Optional):** [Link, or N/A]

**Demo Link (Optional):** [Link, or N/A]

---

## 2. Problem Statement

<!-- Paste the full problem statement exactly as it was given to you. Don't shorten, fix, or reword anything. No character limit here. -->

Build an autonomous cloud cost-optimization agent that monitors a simulated cloud environment, investigates unexpected spending, chooses safe actions, executes them through APIs, and verifies whether the action actually improved the situation. The agent receives natural-language requests and structured cloud state. AI must play a meaningful role in deciding what to investigate and what action to take; deterministic backend code must enforce safety constraints.

---

## 3. TL;DR

<!-- One line each. A judge should get your idea in 10 seconds. -->

**Problem:** Cloud costs rise unexpectedly, and teams struggle to find waste without risking service performance.

**Solution:** CostGuard uses AI to investigate usage, choose a safe action, enforce safety rules, execute it, and verify the result.

**Who benefits:** Engineering and FinOps teams reduce cloud waste while keeping services healthy, available, and within latency limits.

---

## 4. Scope of the Project

**What are you building?**

We are building CostGuard, an autonomous cloud cost-optimization agent. It takes a user's request and cloud service data, investigates the cause of unnecessary spending, chooses a safe action, executes it through a cloud API, and verifies whether the action actually improved the situation.

**How does it solve the problem statement?**

CostGuard combines AI reasoning with deterministic safety rules. AI investigates metrics, traffic and trends and selects an action, while safety rules enforce capacity, latency, health and data-freshness limits before execution. The result is then verified.


**Key features you're building for this hackathon:**

<!-- Up to 5 features. -->

- AI-based investigation and action selection
- Checks safety limits before taking any action
- Checks if the cloud data is old or has changed
- Failed-action recovery and safe fallback
- Before/after verification with cost impact

**What are you deliberately NOT doing? (Optional)**

We are not building a real cloud deployment or 24/7 monitoring system. The hackathon MVP uses a simulated cloud environment and mocked APIs.

---

## 5. Why an Agentic Approach?

<!-- This is an Agentic AI hackathon, so this is one of the most important answers in the file. Be specific. "It uses an LLM" is not an answer. -->

**What does your agent decide or do on its own?**

<!-- e.g. plans its steps, picks which tool to call, handles unexpected input, retries when something fails, hands work to another agent. -->

The agent investigates the service state, decides which data or tool to check, identifies the cause, chooses a safe action, handles failures, and verifies the result before responding.

**Why wouldn't a fixed script, if-else rules, or a simple chatbot be enough?**

A fixed script follows predefined rules and cannot adapt to changing traffic, stale data, or failed actions. A chatbot can explain problems but cannot investigate, choose tools, safely execute actions, and verify their results.

---

## 6. Who It's For & What Changes

**Who or what is this for?**

<!-- Doesn't have to be end users. It could be people, a team, a business, developers, or an internal system or process. -->

Cloud engineering and FinOps teams managing cloud costs and service reliability.

**The world today, without your solution:**

<!-- What happens right now? Who struggles, and what does it cost them in time, money, effort, errors, or missed opportunities? -->

Teams must manually investigate rising cloud costs across metrics, traffic and services. Cost cutting can be slow and risky because a wrong change may increase latency, reduce availability, or affect service health.

**The world with your solution, fully built and scaled to production:**

<!-- Imagine your whole idea is built properly and used by everyone it's meant for. What's different? -->

CostGuard investigates cloud usage, identifies waste, chooses a safe action, executes it, and verifies the result. Teams get lower cloud costs with less manual effort while protecting service reliability.

**What your hackathon build actually delivers today:**

<!-- Of everything you proposed, which part have you built, and which part of the problem does that piece solve right now? A small piece that truly works is a great answer. -->

A request-triggered MVP that accepts cloud state and a natural-language request, investigates the data, selects safe actions, executes them through mocked APIs, handles failures and stale data, and verifies the outcome.

**Before vs. After**

<!--
2 to 4 rows. Pick things that change: time, cost, effort, accuracy, scale, reach, manual work, risk.
Max 80 characters per cell. Replace the example row with your own.
-->

| What Changes | Today | With Our Current Build | At Production Scale |
|--------------|-------|------------------------|---------------------|
| [e.g. Time to answer a student query] | [e.g. 2–3 days over email] | [e.g. Instant for fee questions only] | [e.g. Under a minute for most queries] |
| Cost investigation | Manual analysis        | AI-assisted investigation    | Automated investigation |
| Cloud actions      | Manually decided       | Safely executed via mock API | Automated through cloud APIs |
| Safety checking    | Human responsibility   | Built-in safety rules        | Continuous policy enforcement |
| Result verification| Often checked manually | Before/after verification    | Automated verification and recovery |

---

---

## 7. Architecture & Agents

<!--
All the examples in this section describe ONE made-up project, a college helpdesk agent,
so you can see how the parts fit together. Aim for this level of detail, no more.
You don't need to list every library or every function.
-->

**How is your system put together?**

<!--
Example:
Students ask questions in a web chat. A Triage Agent sorts each message, an Answer Agent
replies using college policy documents, and anything needing a human becomes a helpdesk ticket.
-->

CostGuard receives a user request and cloud data, checks data freshness, and uses an AI agent to investigate the service and suggest actions. A safety layer approves only safe actions, which are executed through the Cloud Control API. The result is then verified and reported to the user.

### 7.1 Agents

<!--
One line per agent. For each one, say what its job is, which model it uses and why that model
fits the job, and what it talks to (other agents, APIs, databases, services).

Example:
- **Triage Agent:** Reads each message and decides if it's a policy question, a complaint, or needs a human. Uses Llama 3.1 8B locally, since sorting is simple and student data stays on our machine. Talks to the Answer Agent and Web Chat.
- **Answer Agent:** Answers policy questions from college documents and files a ticket when approval is needed. Uses Claude Sonnet because it handles long policy text and reasons well about exceptions. Talks to College Docs Store and Helpdesk Ticket API.
-->

### 7.1 Agents

- **CostGuard Reasoning Agent:** Investigates service metrics, traffic and trends, identifies the likely cause and chooses a safe action. Uses a Groq API or local Ollama model and works with cloud-state data and service history.

- **Execution Agent:** Executes the approved action through the Cloud Control API and handles failures such as unavailable capacity. Uses tool-calling and communicates with the mocked Cloud Control API.

- **Verification Agent:** Checks the service again after the action and compares before/after results to confirm whether it helped. Uses the Groq API or local Ollama model with deterministic checks and service metrics.

- **Response Agent:** Turns the investigation, action and verification results into a clear explanation for the user. Uses the Groq API or local Ollama model and reads the execution trace and stored state.

### 7.2 Services, APIs, Databases & Memory

<!--
One line for everything that isn't an agent: databases, APIs, external services, tools,
and your interface (web app, bot, CLI). Say what it is, what it does, and who uses it.
Mention if it's mocked.

Example:
- **College Docs Store (Chroma vector database):** Holds fee, exam, and hostel policy PDFs. Used by the Answer Agent.
- **Helpdesk Ticket API (mocked):** Creates a ticket for the right college office. Used by the Answer Agent.
- **Web Chat (Streamlit):** Where students type questions and see answers. Talks to the Triage Agent.
-->

- **Cloud State / JSON Data:** Provides service metrics, traffic, health, costs and constraints used by CostGuard for investigation and decisions.

- **Mock Cloud Control API (FastAPI):** Simulates cloud actions such as scale up, scale down, resize, stop service and delay batch. Used by the Execution Agent.

- **SQLite State Store:** Stores recent service observations and action history so the agents can track trends and compare before/after states.

- **Streamlit Interface:** Lets users submit a request with cloud data and view the agent's decisions, actions, verification and cost impact.

**How does your system remember things (memory & state)?**

<!--
Example:
Each chat keeps its last 10 messages in session memory so follow-up questions make sense.
Tickets are saved in SQLite so students can check their status later.
-->

CostGuard stores recent observations and actions for each service in SQLite. This history helps detect traffic trends, identify stale data, and compare the service state before and after an action.

**Diagram Link (Optional):** [Link to a photo or drawing of your architecture, or N/A]

### 7.3 Example Walkthrough

<!--
Take ONE realistic input and show how it moves through your system: which agent picks it up,
what gets passed on, which tools or databases are used, and what comes out at the end.
Up to 8 steps. If the flow branches, use 3a / 3b.

Example:
**Example input:** A student types "Can I pay my semester fee late? I'm waiting on my scholarship."

1. [Web Chat] Sends the message and the student's ID to the Triage Agent.
2. [Triage Agent] Classifies it as a fee-policy question and passes it to the Answer Agent.
3. [Answer Agent] Finds the late-fee policy (uses: College Docs Store) and sees scholarship cases need approval.
4. [Answer Agent] Explains the policy and files an approval request (uses: Helpdesk Ticket API).
5. [Web Chat] Shows the student the answer and their ticket number.

**Final output:** A clear answer quoting the late-fee policy, plus a ticket raised with the accounts office.
-->

**Example input:** "Orders traffic is increasing. Keep the service within its latency target."

1. [Intake] Reads the request and orders-api metrics and creates a unified service state.

2. [Freshness Checker] Checks whether the service data is current before making any decision.

3. [Reasoning Agent] Detects traffic rising from 2100 to 4200 requests/min and latency reaching 260ms.

4. [Reasoning Agent] Suggests scaling up because traffic is rising and latency is close to the 300ms limit.

5. [Safety Engine] Checks instance limits, latency and health, then approves only a safe scale-up action.

6. [Execution Agent] Calls the Cloud Control API to increase instances, handling any execution failure.

7. [Verification Agent] Re-checks the service and compares its state before and after the action.

8. [Response Agent] Explains the action, result and whether latency and cost targets were maintained.


**Final output:** Orders-api is scaled safely to handle rising traffic, with the action and verified result clearly reported.


**Anything special about how your workflow runs? (Optional)**

<!--
An algorithm you use, how agents decide what to do next, routing logic, loops, agents working
in parallel, scoring, self-checks. Anything you want us to notice.

Example:
The Triage Agent gives a confidence score with every decision. Below 0.7, the message skips the
Answer Agent and goes straight to a human, so students never get a confident wrong answer.
-->

The agent does not blindly follow the user's cost goal. It considers traffic, latency, health and history, while the safety engine can block unsafe actions. After execution, the result is checked before the agent reports success. If an action fails, the workflow can re-evaluate the state and try another safe action or escalate.

---

## 8. Tech Stack

<!-- Write N/A for any row that doesn't apply. Models are already listed per agent in 7.1. Max 60 characters per cell. -->

| Layer | Technology |
|-------|------------|
| Frontend / Interface | Streamlit |
| Backend | Python, FastAPI |
| Agent Framework | LangGraph |
| Database / Storage | SQLite |
| Hosting | Local machine |
| Other | Groq API / Ollama, Mock Cloud API |

---

## 9. What to Expect From Our Current Build

<!--
Be honest. Unfinished, faked, or hard-coded parts are completely normal at a hackathon.
Telling us means we judge what you actually built, and that works in your favour.
Max 120 characters per bullet.
-->

**Working:**

- [Natural-language request and cloud-state input are accepted and processed]
- [AI analyzes service metrics and selects an action]
- [Safety checks validate actions before execution]
- [Actions and results are shown with before/after verification]

**Partly working, mocked, or hard-coded:**

- [Cloud Control API is simulated using FastAPI]
- [Cloud service metrics and pricing use supplied/sample data]
- [SQLite stores a limited rolling history for the prototype]


**Not working or not built yet:**

- [Real cloud-provider API integration]
- [24/7 background monitoring and automatic alerts]
- [Advanced cost forecasting and production-scale deployment]

**What we'd most like to be judged on:**

CostGuard's core agentic workflow: AI investigates the cloud state and chooses an action, while deterministic safety checks prevent unsafe changes. The system then executes and verifies the result instead of assuming success.

---

## 10. Future Scope

<!-- 2 or 3 things you're NOT building yet but plan to. If you clear the checkpoint, you may be asked to build one of them, so keep them concrete and doable. -->

### Idea 1

**Name:** Continuous Cost Monitoring

**What it is:** CostGuard continuously monitors service metrics and cloud spending instead of waiting for a user request.

**Why it matters:** Problems can be detected early, reducing unexpected costs and preventing performance issues.

**How we'd build it:** Add a background monitoring service that periodically collects metrics and triggers the existing CostGuard workflow when risks are detected.

**Done when:** A simulated service change automatically triggers investigation and the system reports the detected issue and action.

### Idea 2

**Name:** Predictive Cost Forecasting

**What it is:** Predict future cloud spending and identify services likely to exceed their expected budget before the cost problem occurs.

**Why it matters:** Teams can act before unexpected spending becomes a large bill.

**How we'd build it:** Store historical cost and usage data, train a forecasting model, and give predictions to the reasoning agent as another decision signal.

**Done when:** Given historical usage, the system predicts future cost and flags a likely spending increase.

### Idea 3

**Name:** Multi-Cloud CostGuard

**What it is:** Extend CostGuard from the simulated API to real cloud providers while keeping the same reasoning and safety workflow.

**Why it matters:** Organizations can manage cost optimization across multiple cloud environments from one system.

**How we'd build it:** Add provider-specific adapters for AWS, Azure and GCP behind a common Cloud Control API.

**Done when:** The same request can safely investigate and execute an approved action on multiple cloud providers.

---

## 11. Additional Notes (Optional)

<!-- Anything else you'd like us to know. -->

CostGuard is designed around a simple principle: cost optimization should never blindly trade away reliability. AI handles investigation and decisions, while deterministic safety checks control what can actually be executed. Every action is verified afterward, and when data is stale or an action fails, the system chooses a safe next step instead of assuming success.

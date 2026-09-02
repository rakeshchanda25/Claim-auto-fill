# How This App Works — The Complete Flow

This document explains, in plain language, what this app does and exactly what happens — step by step — every time someone uses it. It's written for anyone: you don't need to read code to follow it. Every major step has a picture next to it.

---

## 1. What is this app, in one paragraph?

This is a tool that creates **fake-but-realistic insurance documents** — police reports, medical bills, discharge summaries, ACORD certificates, and 10 other types — for testing purposes. You can generate a single document, "recreate" one based on an uploaded example, or build a whole **packet** of related documents for one claim (e.g. a police report + a medical bill + an insurance certificate, all about the same fake accident). The twist: if you give it a **real claim number**, it will fetch the real claim from **Guidewire** (the insurance company's claim system) and use the real facts — real name, real dates, real policy number — instead of making everything up.

---

## 2. The three ways to generate a document

```mermaid
flowchart LR
    A[User opens the app] --> B{Which mode?}
    B -->|Generate| C["🪄 Make a brand-new document\nfrom nothing but a type + scenario"]
    B -->|Recreate| D["🔄 Upload an example document,\nkeep its people/numbers,\nchange the story"]
    B -->|Build Packet| E["📦 Make 3-5 related documents\nfor ONE claim, all matching"]
```

**Generate** — "Give me a Police Report for a rear-end collision." The app invents a driver, a car, a date, an officer — everything.

**Recreate** — "Here's a real form I found, make a NEW fake one that looks like it, but for a different scenario." The app reads the uploaded file, keeps the same person's name/policy number/etc., but writes a fresh story for the new scenario.

**Build Packet** — "Give me every document for one auto accident claim." The app creates 5 documents (police report, accident report, medical notes, medical bill, insurance certificate) that all agree with each other — same person, same claim number, same date.

---

## 3. The big picture — everything at once

```mermaid
flowchart TB
    subgraph Browser["🖥️ Your Browser"]
        UI[AI Generator tab:\npick doc type, scenario,\ntype optional instructions]
    end

    subgraph Server["⚙️ The Server (app.py)"]
        API["/api/ai-generate"]
        GW_CHECK{Did you type\na claim number?}
        GW[Look up the real\nclaim in Guidewire]
        PROMPT[Build instructions\nfor the AI agent]
        AGENT["🤖 AI Agent\n(reads the instructions,\ncalls the right tools)"]
    end

    subgraph DataLayer["📋 Data & Rendering"]
        FAKER["Faker\n(invents anything\nGuidewire didn't have)"]
        TEMPLATE["Document template\n(HTML + styling)"]
        PDF["📄 Final PDF"]
    end

    UI -->|"Generate" button| API
    API --> GW_CHECK
    GW_CHECK -->|yes| GW
    GW_CHECK -->|no| PROMPT
    GW --> PROMPT
    PROMPT --> AGENT
    AGENT --> FAKER
    FAKER --> TEMPLATE
    TEMPLATE --> PDF
    PDF -->|download| UI
```

**In plain words:** you click a button in the browser → the server checks if you mentioned a real claim → if yes, it fetches the real claim → it builds a set of instructions → an AI agent follows those instructions, filling in gaps with fake data where needed → a PDF comes out the other end.

---

## 4. Step by step: what happens when you click "Generate"

```mermaid
sequenceDiagram
    actor You
    participant Browser
    participant Server as app.py
    participant GW as Guidewire
    participant Agent as AI Agent
    participant Tools as Document Tools
    participant PDF as PDF Renderer

    You->>Browser: Pick "Police Report", scenario "Rear-end collision"
    You->>Browser: (Optional) type "claim id 000-00-053109"
    Browser->>Server: POST /api/ai-generate

    alt You typed a claim number
        Server->>Server: Spot the claim number in your text
        Server->>GW: "Give me everything about this claim"
        GW-->>Server: Real name, policy #, loss date, location...
        Server->>Server: Save these facts for later ("staging")
    end

    Server->>Agent: Here are your instructions (the "prompt")
    Agent->>Tools: Call generate_synthetic_data(...)
    Tools->>Tools: Use the REAL Guidewire facts first
    Tools->>Tools: Faker invents everything else
    Tools-->>Agent: "Data is ready"
    Agent->>PDF: render_document_to_pdf(...)
    PDF-->>Agent: "PDF is ready"
    Agent-->>Server: "Done!"
    Server-->>Browser: Sends the PDF file
    Browser-->>You: Download starts
```

---

## 5. The Guidewire lookup, in detail

This is the part that makes documents *real* instead of purely fake.

```mermaid
flowchart TD
    A["You type something like:\n'generate this for claim id 000-00-053109'"] --> B[Server scans your text\nfor a claim ID or number]
    B --> C{Found one?}
    C -->|No| D["Skip Guidewire entirely.\nEverything is 100% Faker."]
    C -->|Yes| E["Call the real Guidewire API"]
    E --> F{Claim found\nand reachable?}
    F -->|No / error| G["Log a warning,\ncontinue with pure Faker.\n(Never breaks the request.)"]
    F -->|Yes| H["Pull out the useful facts:\nname, claim #, policy #,\nloss date, location, adjuster..."]
    H --> I["These facts now take PRIORITY\nover anything Faker would invent"]
```

**The golden rule:** *Guidewire data first, Faker fills the gaps.* Nothing ever breaks just because Guidewire is slow, down, or the claim doesn't exist — it just quietly falls back to normal fake-data generation.

### What we actually pull from Guidewire

| From Guidewire | Lands on | Example |
|---|---|---|
| `claim_number` | Every document's claim number field | `000-00-053109` |
| `policy_number` | Every document's policy number field | `9185479590` |
| `insured` (the person) | Whichever field THAT document uses for the person's name | see next section |
| `loss_date` | Anchors every date field so nothing is chronologically wrong | see §7 |
| `loss_location` | The location field, wherever one exists | `4521 Maple Grove Rd, Columbus, OH` |
| `loss_type` / `loss_cause` | Extra context facts, where relevant | `Auto` / `Collision with pedestrian` |
| `assigned_adjuster`, `jurisdiction`, `policy_type`... | Whichever field matches | — |
| Agent's name (from the claim's contact list) | ACORD-25's "producer" field | — |
| Adjuster's own notes + real attached documents | Free-text context (see §8) | — |

---

## 6. The tricky part: "the same person" has a different field name on every document

This was a real bug we found and fixed. Every document type calls "the claimant's name" something different:

```mermaid
flowchart LR
    NAME(["Micheal Turner\n(the real Guidewire insured)"])
    NAME --> A["Medical Record\nfield: patient_name"]
    NAME --> B["Demand Letter\nfield: claimant_name"]
    NAME --> C["Litigation Document\nfield: plaintiff_name"]
    NAME --> D["Auto Accident Report\nfield: employee → name\n(nested!)"]
    NAME --> E["Police Report\nfield: parties_involved[0] → name\n(nested list!)"]
```

Without special handling, putting "Micheal Turner" into a document only works if you happen to guess the right field name. So the app has an **alias table** — one function that knows all five names for "the claimant" and fills in whichever one a given document actually uses, including reaching inside nested boxes (like `employee.name`).

> 🐛 **Real bug this fixed**: the Auto Accident Report's "STATE EMPLOYEE" section never had a name field in the template *at all* — you could see the *other* driver's name, but never the claim owner's. We added the missing field to both the data and the printed form.

---

## 7. The date problem: "the report can't be older than the incident"

```mermaid
flowchart TD
    subgraph Before["❌ Before the fix"]
        B1["Faker picks a random date\nfor 'today' (dos)"] --> B2["incident_date = random"]
        B1 --> B3["report_date = random"]
        GW1["Guidewire says loss_date\n= Aug 1, 2026"] -.->|"overwrites ONLY\nincident_date"| B2
        B3 -.->|"never touched!"| B3STILL["report_date stays\nrandomly in 2025 😬"]
    end

    subgraph After["✅ After the fix"]
        A1["Guidewire's loss_date\nbecomes the ANCHOR\nbefore anything is generated"] --> A2["incident_date = Aug 1, 2026"]
        A1 --> A3["report_date = Aug 1, 2026"]
        A1 --> A4["Case number's embedded\nyear = 2026"]
    end
```

**The old approach**: generate everything randomly first, then paste the real date onto ONE field. Every *other* field that depended on "today's date" (report date, case numbers with the year baked in, etc.) never found out about the real date.

**The fix**: the real loss date is now used as the *starting point* for generation, not a patch applied afterward. Every date-based field is computed *from* it, so they're automatically consistent — no field can end up in a different year than the real incident.

---

## 8. Claim notes & real attached documents — used, but never "dumped"

Guidewire also has messy, free-text stuff: the adjuster's own notes, and snippets from real documents already on the claim (a real police report narrative, a real ER summary). We use this — but carefully, because it's prose, not clean field values, and different document types need it applied differently.

```mermaid
flowchart TD
    NOTES["Adjuster's notes +\nreal document excerpts"] --> MODE{Which mode?}

    MODE -->|Generate / Recreate| LLM["Given to the AI agent as\nplain-English context.\nThe AI decides how (or if)\nto weave it into the narrative\nit's already writing."]

    MODE -->|Build Packet| RULES["No AI writing step here —\nso a RULE decides instead:"]
    RULES --> R1["Is this doc type's category\na match? (e.g. a police report\nonly gets ACCIDENT excerpts,\nnever medical ones)"]
    R1 -->|Match| ADD["Add it to that document's\n'extra scenario details' section"]
    R1 -->|No match| SKIP["Skip it entirely\n(e.g. ACORD-25 has no\nnarrative section at all)"]
```

**Why this matters**: an earlier version of this dumped the SAME big block of notes into every single document in a packet, whether it made sense there or not. That's wrong — a Certificate of Insurance has no place for "the ER discharge summary said..." So now, each document only gets the notes/excerpts that are actually *about* that kind of document.

---

## 9. Build Packet — how five documents end up agreeing with each other

```mermaid
flowchart TD
    START["build_packet('auto-accident-packet', ...)"] --> FIRST["Generate the FIRST document\n(Police Report)"]
    FIRST --> DERIVE["From it, decide the packet's\nONE shared identity:\n- name\n- location\n- incident date"]
    DERIVE --> LOOP["For each of the other 4 documents:"]
    LOOP --> GEN["Generate it independently\n(own random VIN, own witnesses, etc.)"]
    GEN --> SYNC["Overwrite its name/location/date\nfields with the ONE shared set\n(using the alias table from §6)"]
    SYNC --> NEXT{More documents?}
    NEXT -->|yes| LOOP
    NEXT -->|no| DONE["📦 All 5 documents render,\nall agreeing on who/where/when"]
```

This works **whether or not** you gave it a real claim: if you did, "the shared identity" comes from Guidewire; if you didn't, it's just whatever the first document randomly generated — either way, every document in the packet tells the same story.

---

## 10. Two safety nets, not one — how the data *actually* gets applied

This was the trickiest bug to find. Early on, Guidewire's data was described in the AI's instructions as *text* — like a note taped to the AI's desk saying "please use this." The problem: an AI reads a prompt, it doesn't *execute* it like code. A big block of text describing 15 fields could get skimmed, mis-copied, or dropped entirely.

```mermaid
flowchart LR
    subgraph Staged["✅ Safety Net #1 — always happens"]
        S1["Server saves the Guidewire\nfacts BEFORE the AI even starts"]
        S2["Every tool the AI calls\nreads that saved data\nautomatically"]
        S1 --> S2
    end

    subgraph LLMArg["➕ Safety Net #2 — extra, not required"]
        L1["The AI is ALSO told\nit CAN pass the same data\nas an argument"]
        L2["If it does, that gets\nmerged in on top"]
        L1 --> L2
    end

    Staged --> RESULT["Either way,\nthe real data is applied"]
    LLMArg --> RESULT
```

**In short**: the server doesn't *hope* the AI remembers to use the real data — it stages it directly where the document-building code will find it, guaranteed. The AI can *also* pass it explicitly (useful if it found something extra worth adding), but the guaranteed path never depends on the AI doing the right thing.

---

## 11. A complete walkthrough — one real example

Let's trace one real request end to end: **"Build the Auto Accident Packet for claim 000-00-053109."**

```mermaid
flowchart TD
    A["1️⃣ You type:\n'claim id 000-00-053109'\nand pick 'Build Packet' → Auto Accident"] --> B

    B["2️⃣ Server finds '000-00-053109'\nin your text"] --> C

    C["3️⃣ Server calls Guidewire.\nGets back: Micheal Turner,\npolicy 9185479590,\nloss date Aug 1 2026,\nlocation in Columbus OH,\nadjuster John Wesley..."] --> D

    D["4️⃣ Server saves these facts\n('staging'), then builds the\nAI's instructions"] --> E

    E["5️⃣ AI agent calls build_packet(...)"] --> F

    F["6️⃣ Five documents generate,\neach pulling Guidewire's real facts\nwherever it has a matching field,\nFaker filling in the rest\n(VIN numbers, exact injuries, etc.)"] --> G

    G["7️⃣ Every document gets synced:\nsame name (however each\ndocument spells that field),\nsame claim #, same date"] --> H

    H["8️⃣ Police Report + Auto Loss Notice\nalso get the real accident narrative\n(matched by category)"] --> I

    I["9️⃣ All 5 render to PDF,\nzipped together"] --> J

    J["🔟 You download one ZIP file\nwith 5 consistent, realistic\ninsurance documents"]
```

**The result**: a Police Report, an Auto Loss Notice, ER Visit Notes, an ER Bill, and an ACORD-25 Certificate — all about "Micheal Turner," all with claim number `000-00-053109`, all dated August 1, 2026 — some of them (the ones about the accident itself) even echoing real detail from the actual claim file.

---

## 12. What happens when things go wrong

```mermaid
flowchart TD
    A{What failed?} -->|Guidewire unreachable\nor claim not found| B["✅ Falls back to pure Faker.\nRequest still succeeds."]
    A -->|No claim ID typed at all| C["✅ Normal - just uses Faker\nlike Guidewire was never involved."]
    A -->|Reference upload doesn't\nmatch the document type| D["⚠️ Reports which values\ncouldn't be placed\n('unmapped_keys'),\nrest still generates fine."]
    A -->|The AI agent itself\n(the LLM) fails or errors| E["❌ This is the one real\nfailure point - needs the\nfull AI framework running\n(only available on the Linux VM,\nnot this local dev sandbox)."]
```

Almost every failure mode quietly degrades to "just use fake data" rather than blocking you. The one hard requirement is the AI agent itself, which needs the full server environment to run.

---

## 13. Everything that lives where (a map of the code)

```mermaid
flowchart TB
    subgraph Frontend["frontend/"]
        F1[index.html - the 3 tabs]
        F2[main.js - button clicks, API calls]
    end

    subgraph Backend["app.py"]
        B1["/api/ai-generate - the main endpoint"]
        B2[fetch_claim_facts - talks to Guidewire]
    end

    subgraph AI["ai_doc_generator/"]
        A1[prompt_builder.py - writes the AI's instructions]
        A2[tools.py - the actual document-building logic]
        A3[agent_factory.py - sets up the AI agent]
    end

    subgraph Data["renderers/"]
        D1[synthetic_data.py - Faker-based data per doc type]
        D2["templates/ - one HTML file per document type\n(13 total)"]
        D3[html_renderer.py - turns HTML into a PDF]
    end

    subgraph External["Outside this app"]
        E1["guidewire.py - the Guidewire API client"]
    end

    F2 --> B1
    B1 --> B2
    B2 --> E1
    B1 --> A1
    A1 --> A3
    A3 --> A2
    A2 --> D1
    D1 --> D2
    D2 --> D3
```

---

## 14. Quick glossary

| Term | Plain-English meaning |
|---|---|
| **Faker** | A tool that invents realistic-looking fake data (names, addresses, dates) |
| **Scenario** | The "story" a document tells (e.g. "rear-end collision," "fire damage") |
| **Packet** | A bundle of 3-5 related documents about one fake claim |
| **Staging** | Saving data on the server *before* the AI runs, so the document-building code can find it reliably |
| **Anchor date** | The real incident date, used as the starting point for every other date in a document |
| **Alias table** | The lookup that knows "insured_name," "patient_name," and "employee.name" all mean the same thing |
| **Skill file** | A short reference doc telling the AI what fields a document type has |
| **Tool** (AI sense) | A specific action the AI is allowed to take, like "generate data" or "render a PDF" |

---

*This document describes the app as of this session's changes. If the code changes significantly, this file should be updated to match.*

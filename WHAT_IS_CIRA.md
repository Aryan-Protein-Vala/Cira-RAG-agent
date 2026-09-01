# WHAT IS CIRA?

CIRA stands for **Corporate Intelligence & Reporting Assistant**. It is a modern, AI-powered system designed to let business users ask plain-English questions about their company's SAP Business One data and get immediate, accurate, and visual answers.

## The Core Problem CIRA Solves

Traditionally, if a manager or executive wants to know something about their business—for example, *"What was our total revenue from Top 5 customers last month?"* or *"Show me all open purchase orders over $10,000 pending delivery"*—they have to:
1. Open a complex ERP system (like SAP Business One).
2. Know exactly which menus, modules, and screens to click through.
3. Export the data to Excel to calculate totals or create charts.
4. Or worse, submit a ticket to the IT department to write a custom SQL query, which takes days.

CIRA bridges this gap by acting as an **intelligent middleman** between the human and the database.

## How CIRA Works

CIRA is built using a modern AI agent architecture consisting of three main layers:

### 1. The Frontend (Next.js / React)
A sleek, chat-based web interface where users can securely log in and type their questions just like they are talking to a human analyst. It renders the answers beautifully with rich data tables, charts, and succinct textual summaries.

### 2. The AI Planner & Backend (FastAPI / Python)
When a user asks a question, CIRA's backend (powered by LLMs like OpenAI/OpenRouter via LangChain/LangGraph) doesn't just guess an answer. Instead, it acts as an autonomous agent:
- It uses **Semantic Search** to understand what the user means (e.g., mapping the word "invoices" to the SAP table `OINV`).
- It **Introspects the Database Schema** to find exactly which columns exist and what they mean.
- It formulates a **safe, read-only SQL query** or an OData request to fetch *only* the relevant data.
- It executes the query and summarizes the raw data into a human-readable response and a chart payload.

### 3. The Database Connector (SAP HANA / MS SQL Server)
CIRA securely connects to the company's internal ERP database. It was originally built for **SAP HANA** and the **SAP B1 Service Layer**, but now natively supports **Microsoft SQL Server** as well. Because it uses strict, read-only guardrails, it guarantees that the AI can never modify, delete, or corrupt the company's live ERP data.

## Key Features

- **Dynamic Schema Discovery:** CIRA searches the database's metadata (`SYS.TABLE_COLUMNS` or `sys.columns`) live. This means if your company adds custom User-Defined Fields (UDFs) like `U_Region` to SAP, CIRA instantly knows about them and can answer questions about them without any code changes.
- **Auto-Charting:** CIRA automatically detects dimensions and measures (dates, amounts, categories) and returns the data properly structured so the frontend can immediately plot bar charts, line graphs, and pie charts.
- **Enterprise Security:** Complete isolation between the LLM and your data. Raw database rows are *never* sent to OpenAI. CIRA only sends the *schema* (column names and types) to the LLM to generate the SQL. The actual data stays securely on your servers and is sent directly to the user's browser.
- **Multi-Backend Support:** Works with direct SQL (HANA or MSSQL) for deep, complex queries (joins, window functions), or the SAP B1 Service Layer (OData) for lighter entity queries.

In short, CIRA turns an intimidating, complex enterprise database into a friendly, conversational assistant that any employee can use to make data-driven decisions in seconds.

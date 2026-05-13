import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime, date, timedelta
from pathlib import Path

APP_TITLE = "Legal CLM + AML Command Centre"
DB_PATH = "legal_clm_aml.db"

st.set_page_config(page_title=APP_TITLE, page_icon="⚖️", layout="wide")

# -----------------------------
# DATABASE
# -----------------------------
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = db()
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT UNIQUE,
    client_name TEXT,
    country TEXT,
    client_type TEXT,
    contact_person TEXT,
    email TEXT,
    services TEXT,
    risk_level TEXT,
    status TEXT,
    created_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS legal_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_code TEXT UNIQUE,
    title TEXT,
    matter_type TEXT,
    client_id TEXT,
    owner TEXT,
    priority TEXT,
    status TEXT,
    stage TEXT,
    next_action TEXT,
    approval_required TEXT,
    approver TEXT,
    hours_spent REAL,
    due_date TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_code TEXT UNIQUE,
    client_id TEXT,
    counterparty TEXT,
    contract_type TEXT,
    workflow_stage TEXT,
    risk_rating TEXT,
    value_amount REAL,
    currency TEXT,
    start_date TEXT,
    end_date TEXT,
    renewal_date TEXT,
    owner TEXT,
    approver TEXT,
    signature_status TEXT,
    repository_link TEXT,
    next_action TEXT,
    key_risks TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS aml_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aml_code TEXT UNIQUE,
    client_id TEXT,
    entity_name TEXT,
    jurisdiction TEXT,
    service_requested TEXT,
    kyc_status TEXT,
    kyb_status TEXT,
    sumsub_link TEXT,
    document_request TEXT,
    risk_score INTEGER,
    risk_level TEXT,
    pep_sanctions_status TEXT,
    ongoing_review_date TEXT,
    release_decision TEXT,
    next_action TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_code TEXT UNIQUE,
    client_id TEXT,
    linked_record_type TEXT,
    linked_record_code TEXT,
    document_name TEXT,
    document_type TEXT,
    version TEXT,
    status TEXT,
    file_link TEXT,
    expiry_date TEXT,
    notes TEXT,
    created_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT UNIQUE,
    category TEXT,
    body TEXT,
    created_at TEXT
)
""")

conn.commit()

# -----------------------------
# HELPERS
# -----------------------------
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def run_query(query, params=()):
    return pd.read_sql_query(query, conn, params=params)

def execute(query, params=()):
    cur.execute(query, params)
    conn.commit()

def next_code(prefix, table, column):
    df = run_query(f"SELECT {column} FROM {table} WHERE {column} LIKE ? ORDER BY id DESC LIMIT 1", (f"{prefix}-%",))
    if df.empty:
        return f"{prefix}-001"
    last = df.iloc[0][column]
    try:
        num = int(str(last).split("-")[-1]) + 1
    except Exception:
        num = 1
    return f"{prefix}-{num:03d}"

def country_short(country):
    mapping = {
        "India": "IN", "Singapore": "SG", "United States": "US", "United Kingdom": "UK",
        "Japan": "JP", "Vietnam": "VN", "Philippines": "PH", "Cambodia": "KH",
        "Malaysia": "MY", "Thailand": "TH", "UAE": "AE", "Canada": "CA"
    }
    return mapping.get(country, country[:2].upper() if country else "XX")

def kpi_card(label, value):
    st.markdown(f"""
    <div style='background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:18px;box-shadow:0 1px 8px rgba(0,0,0,.04)'>
        <div style='font-size:13px;color:#6b7280'>{label}</div>
        <div style='font-size:30px;font-weight:800;color:#111827'>{value}</div>
    </div>
    """, unsafe_allow_html=True)

def workflow_next(stage):
    flow = ["Business Intake", "Legal Intake", "Drafting", "Negotiation", "Internal Approval", "Signature", "Repository", "Renewal Monitoring", "Compliance", "Closure"]
    if stage in flow and flow.index(stage) < len(flow) - 1:
        return flow[flow.index(stage) + 1]
    return "Completed / Monitor"

def aml_risk_score(jurisdiction, service, pep, docs):
    score = 0
    high_juris = ["High Risk", "Offshore", "Sanctioned / Restricted"]
    if jurisdiction in high_juris: score += 35
    if service in ["Crypto IBAN", "Virtual Asset Service", "Cross-border Remittance", "High Risk Payment Services"]: score += 30
    if pep == "Potential Match / Pending Clearance": score += 25
    if docs != "Complete": score += 20
    if score >= 70: return score, "High"
    if score >= 40: return score, "Medium"
    return score, "Low"

def replace_vars(template, data):
    text = template
    for k, v in data.items():
        text = text.replace("{{" + k + "}}", str(v or ""))
    return text

# Default templates
if run_query("SELECT COUNT(*) as c FROM templates").iloc[0]["c"] == 0:
    execute("INSERT INTO templates(template_name, category, body, created_at) VALUES(?,?,?,?)", (
        "Document Request - AML/KYB", "AML",
        """Dear {{client_name}},\n\nTo complete the onboarding/KYB review, kindly provide the following documents:\n\n1. Company registry extract issued within the last 12 months.\n2. Document listing all ultimate beneficial owners.\n3. Registered address proof.\n4. Authorised signatory details and ID documents.\n5. Any supporting document if the registry reflects inactive or dissolved status.\n\nPlease note that self-issued documents should be signed by the registered agent or authorised officer.\n\nRegards,\nLegal & Compliance Team""",
        now()
    ))
    execute("INSERT INTO templates(template_name, category, body, created_at) VALUES(?,?,?,?)", (
        "Contract Approval Note", "CLM",
        """Contract Approval Note\n\nClient: {{client_name}}\nCounterparty: {{counterparty}}\nContract Type: {{contract_type}}\nRisk Rating: {{risk_rating}}\nCurrent Stage: {{workflow_stage}}\nNext Action: {{next_action}}\n\nKey Risks:\n{{key_risks}}\n\nRecommendation:\nSubject to commercial confirmation and legal approval, this contract may proceed to the next stage.""",
        now()
    ))
    conn.commit()

# -----------------------------
# STYLE
# -----------------------------
st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
[data-testid="stSidebar"] {background: #f3f6fb;}
h1 {font-size: 42px !important; font-weight: 850 !important;}
h2, h3 {font-weight: 800 !important;}
.stButton button {border-radius: 12px; font-weight: 700;}
[data-testid="stMetricValue"] {font-weight: 800;}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# NAVIGATION
# -----------------------------
st.sidebar.title(APP_TITLE)
page = st.sidebar.radio(
    "Go to",
    [
        "1. Executive Dashboard",
        "2. Legal Task Manager",
        "3. Contract CLM",
        "4. Legal Doc Automation",
        "5. AML / KYC / KYB",
        "6. Documents Repository",
        "7. Reports Export",
        "8. Setup Guide"
    ]
)

# -----------------------------
# DASHBOARD
# -----------------------------
if page == "1. Executive Dashboard":
    st.title("Executive Legal Dashboard")
    st.caption("Live command centre for tasks, contracts, AML, approvals, reminders and pending action.")

    tasks = run_query("SELECT * FROM legal_tasks")
    contracts = run_query("SELECT * FROM contracts")
    aml = run_query("SELECT * FROM aml_cases")
    docs = run_query("SELECT * FROM documents")

    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Open Legal Tasks", len(tasks[tasks["status"].isin(["Open", "In Progress", "Pending Approval"])]) if not tasks.empty else 0)
    with c2: kpi_card("Active Contracts", len(contracts[~contracts["workflow_stage"].isin(["Closure", "Repository"])]) if not contracts.empty else 0)
    with c3: kpi_card("AML Cases Pending", len(aml[~aml["release_decision"].isin(["Approved / Released", "Rejected"])]) if not aml.empty else 0)
    with c4: kpi_card("Documents Stored", len(docs))

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Urgent Task Actions")
        if tasks.empty:
            st.info("No legal tasks yet.")
        else:
            t = tasks.sort_values(["due_date", "priority"], na_position="last").head(10)
            st.dataframe(t[["task_code", "title", "client_id", "priority", "stage", "status", "next_action", "due_date", "hours_spent"]], use_container_width=True, hide_index=True)
    with col2:
        st.subheader("Contracts Needing Movement")
        if contracts.empty:
            st.info("No contracts yet.")
        else:
            c = contracts.sort_values(["renewal_date", "updated_at"], na_position="last").head(10)
            st.dataframe(c[["contract_code", "counterparty", "contract_type", "workflow_stage", "risk_rating", "signature_status", "next_action", "renewal_date"]], use_container_width=True, hide_index=True)

    st.subheader("AML / KYB Risk Watch")
    if aml.empty:
        st.info("No AML cases yet.")
    else:
        st.dataframe(aml[["aml_code", "entity_name", "jurisdiction", "service_requested", "kyc_status", "kyb_status", "risk_score", "risk_level", "release_decision", "next_action"]], use_container_width=True, hide_index=True)

# -----------------------------
# TASK MANAGER
# -----------------------------
elif page == "2. Legal Task Manager":
    st.title("Legal Task Manager")
    st.caption("Full workflow view: status, next step, time spent, approvals, owner, pending action and due dates.")

    with st.expander("Create / Add Legal Task", expanded=True):
        with st.form("task_form"):
            cols = st.columns(3)
            title = cols[0].text_input("Task Title")
            matter_type = cols[1].selectbox("Matter Type", ["Contract", "AML/KYB", "Corporate", "Regulatory", "Litigation", "Employment", "Data Protection", "Other"])
            client_id = cols[2].text_input("Client ID / Matter Client")
            cols = st.columns(4)
            owner = cols[0].text_input("Owner", value="Legal Team")
            priority = cols[1].selectbox("Priority", ["Low", "Medium", "High", "Critical"])
            status = cols[2].selectbox("Status", ["Open", "In Progress", "Pending Approval", "Blocked", "Completed"])
            stage = cols[3].selectbox("Stage", ["Intake", "Review", "Drafting", "Negotiation", "Approval", "Execution", "Filing", "Monitoring", "Closed"])
            cols = st.columns(4)
            approval_required = cols[0].selectbox("Approval Required?", ["No", "Yes"])
            approver = cols[1].text_input("Approver")
            hours_spent = cols[2].number_input("Hours Spent", min_value=0.0, step=0.25)
            due_date = cols[3].date_input("Due Date", value=date.today() + timedelta(days=3))
            next_action = st.text_area("Next Action / How to move forward")
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Legal Task")
            if submitted and title:
                code = next_code("TASK", "legal_tasks", "task_code")
                execute("""INSERT INTO legal_tasks VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    code, title, matter_type, client_id, owner, priority, status, stage, next_action,
                    approval_required, approver, hours_spent, str(due_date), notes, now(), now()
                ))
                st.success(f"Task created: {code}")

    df = run_query("SELECT * FROM legal_tasks ORDER BY id DESC")
    st.subheader("Task Workflow Board")
    if not df.empty:
        status_filter = st.multiselect("Filter Status", sorted(df["status"].dropna().unique()), default=list(sorted(df["status"].dropna().unique())))
        f = df[df["status"].isin(status_filter)]
        st.dataframe(f[["task_code", "title", "matter_type", "client_id", "owner", "priority", "status", "stage", "next_action", "approval_required", "approver", "hours_spent", "due_date"]], use_container_width=True, hide_index=True)
    else:
        st.info("No tasks created yet.")

# -----------------------------
# CLM
# -----------------------------
elif page == "3. Contract CLM":
    st.title("Contract Lifecycle Management")
    st.caption("End-to-end CLM: Business → Legal Intake → Drafting → Negotiation → Approval → Signature → Repository → Renewal → Compliance → Closure")

    stages = ["Business Intake", "Legal Intake", "Drafting", "Negotiation", "Internal Approval", "Signature", "Repository", "Renewal Monitoring", "Compliance", "Closure"]

    with st.expander("Create Contract Record", expanded=True):
        with st.form("contract_form"):
            cols = st.columns(4)
            client_id = cols[0].text_input("Client ID")
            counterparty = cols[1].text_input("Counterparty")
            contract_type = cols[2].selectbox("Contract Type", ["NDA", "MSA", "Service Agreement", "Purchase Agreement", "MoU", "Lease", "Employment", "Carbon Credit Agreement", "CORC Supply", "Other"])
            workflow_stage = cols[3].selectbox("Workflow Stage", stages)
            cols = st.columns(4)
            risk_rating = cols[0].selectbox("Risk Rating", ["Low", "Medium", "High", "Critical"])
            value_amount = cols[1].number_input("Contract Value", min_value=0.0, step=1000.0)
            currency = cols[2].selectbox("Currency", ["USD", "INR", "JPY", "SGD", "EUR", "GBP"])
            signature_status = cols[3].selectbox("Signature Status", ["Not Started", "Sent for Signature", "Partly Signed", "Executed"])
            cols = st.columns(4)
            start_date = cols[0].date_input("Start Date", value=date.today())
            end_date = cols[1].date_input("End Date", value=date.today() + timedelta(days=365))
            renewal_date = cols[2].date_input("Renewal / Notice Date", value=date.today() + timedelta(days=335))
            owner = cols[3].text_input("Owner", value="Legal Team")
            approver = st.text_input("Approver / Business Owner")
            repository_link = st.text_input("Executed Contract / Draft Link")
            key_risks = st.text_area("Key Risks / Negotiation Points")
            auto_next = workflow_next(workflow_stage)
            next_action = st.text_area("Next Action", value=f"Move to: {auto_next}")
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Contract")
            if submitted and counterparty:
                code = next_code("CON", "contracts", "contract_code")
                execute("""INSERT INTO contracts VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    code, client_id, counterparty, contract_type, workflow_stage, risk_rating, value_amount,
                    currency, str(start_date), str(end_date), str(renewal_date), owner, approver,
                    signature_status, repository_link, next_action, key_risks, notes, now(), now()
                ))
                st.success(f"Contract created: {code}")

    df = run_query("SELECT * FROM contracts ORDER BY id DESC")
    if not df.empty:
        st.subheader("CLM Pipeline")
        st.dataframe(df[["contract_code", "client_id", "counterparty", "contract_type", "workflow_stage", "risk_rating", "signature_status", "approver", "next_action", "renewal_date", "repository_link"]], use_container_width=True, hide_index=True)
        st.subheader("Stage Summary")
        st.bar_chart(df["workflow_stage"].value_counts())
    else:
        st.info("No contracts created yet.")

# -----------------------------
# DOC AUTOMATION
# -----------------------------
elif page == "4. Legal Doc Automation":
    st.title("Legal Document Automation")
    st.caption("Template-based legal document generation similar to legal document automation workflows: reusable templates, variables and generated drafts.")

    tab1, tab2 = st.tabs(["Generate Document", "Manage Templates"])

    with tab1:
        templates = run_query("SELECT * FROM templates ORDER BY template_name")
        clients = run_query("SELECT * FROM clients ORDER BY client_name")
        contracts = run_query("SELECT * FROM contracts ORDER BY id DESC")
        aml = run_query("SELECT * FROM aml_cases ORDER BY id DESC")

        if templates.empty:
            st.warning("No templates available.")
        else:
            template_name = st.selectbox("Choose Template", templates["template_name"].tolist())
            template_body = templates[templates["template_name"] == template_name].iloc[0]["body"]
            st.text_area("Template Preview", template_body, height=220)

            client_name = st.text_input("Client Name")
            counterparty = st.text_input("Counterparty")
            contract_type = st.text_input("Contract Type")
            risk_rating = st.selectbox("Risk Rating", ["Low", "Medium", "High", "Critical"])
            workflow_stage = st.text_input("Workflow Stage")
            next_action = st.text_area("Next Action")
            key_risks = st.text_area("Key Risks")

            if st.button("Generate Draft"):
                generated = replace_vars(template_body, {
                    "client_name": client_name,
                    "counterparty": counterparty,
                    "contract_type": contract_type,
                    "risk_rating": risk_rating,
                    "workflow_stage": workflow_stage,
                    "next_action": next_action,
                    "key_risks": key_risks,
                    "date": str(date.today())
                })
                st.subheader("Generated Draft")
                st.text_area("Copy this draft", generated, height=420)
                st.download_button("Download as TXT", generated, file_name=f"{template_name.replace(' ','_')}.txt")

    with tab2:
        with st.form("template_form"):
            name = st.text_input("Template Name")
            category = st.selectbox("Category", ["CLM", "AML", "Corporate", "Email", "Notice", "Other"])
            body = st.text_area("Template Body - use variables like {{client_name}}, {{counterparty}}, {{date}}", height=300)
            if st.form_submit_button("Save Template") and name and body:
                execute("INSERT OR REPLACE INTO templates(template_name, category, body, created_at) VALUES(?,?,?,?)", (name, category, body, now()))
                st.success("Template saved.")
        st.dataframe(run_query("SELECT template_name, category, created_at FROM templates ORDER BY id DESC"), use_container_width=True, hide_index=True)

# -----------------------------
# AML
# -----------------------------
elif page == "5. AML / KYC / KYB":
    st.title("AML / KYC / KYB Management")
    st.caption("KYC/KYB tracking, Sumsub link, document request, risk matrix, ongoing review and release decision.")

    with st.expander("Create AML / KYB Case", expanded=True):
        with st.form("aml_form"):
            cols = st.columns(4)
            client_id = cols[0].text_input("Client ID")
            entity_name = cols[1].text_input("Entity / Client Name")
            jurisdiction = cols[2].selectbox("Jurisdiction Risk", ["Low Risk", "Medium Risk", "High Risk", "Offshore", "Sanctioned / Restricted"])
            service_requested = cols[3].selectbox("Service Requested", ["Fiat Account", "Crypto IBAN", "Virtual Asset Service", "Cross-border Remittance", "Payment Services", "High Risk Payment Services", "Other"])
            cols = st.columns(4)
            kyc_status = cols[0].selectbox("KYC Status", ["Not Started", "Sent", "Pending", "Complete", "Rejected"])
            kyb_status = cols[1].selectbox("KYB Status", ["Not Started", "Sent", "Pending", "Complete", "Rejected"])
            pep = cols[2].selectbox("PEP / Sanctions", ["Clear", "Potential Match / Pending Clearance", "Rejected"])
            release_decision = cols[3].selectbox("Release Decision", ["Hold", "Additional Documents Required", "Approved / Released", "Rejected"])
            sumsub_link = st.text_input("Sumsub / Verification Link")
            document_request = st.text_area("Additional Document Request")
            review_date = st.date_input("Ongoing Review Date", value=date.today() + timedelta(days=180))
            docs_state = "Complete" if kyc_status == "Complete" and kyb_status == "Complete" else "Incomplete"
            score, level = aml_risk_score(jurisdiction, service_requested, pep, docs_state)
            st.info(f"Auto Risk Score: {score} / Risk Level: {level}")
            next_action = st.text_area("Next Action", value="Send reminder / request pending documents" if docs_state == "Incomplete" else "Proceed for compliance release approval")
            notes = st.text_area("Notes")
            if st.form_submit_button("Save AML Case") and entity_name:
                code = next_code("AML", "aml_cases", "aml_code")
                execute("""INSERT INTO aml_cases VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    code, client_id, entity_name, jurisdiction, service_requested, kyc_status, kyb_status,
                    sumsub_link, document_request, score, level, pep, str(review_date), release_decision,
                    next_action, notes, now(), now()
                ))
                st.success(f"AML case created: {code}")

    df = run_query("SELECT * FROM aml_cases ORDER BY id DESC")
    if not df.empty:
        st.subheader("AML Case Register")
        st.dataframe(df[["aml_code", "client_id", "entity_name", "jurisdiction", "service_requested", "kyc_status", "kyb_status", "risk_score", "risk_level", "pep_sanctions_status", "release_decision", "next_action", "ongoing_review_date"]], use_container_width=True, hide_index=True)
        st.subheader("Risk Matrix")
        st.bar_chart(df["risk_level"].value_counts())
    else:
        st.info("No AML cases created yet.")

# -----------------------------
# DOCUMENTS
# -----------------------------
elif page == "6. Documents Repository":
    st.title("Documents Repository")
    st.caption("Store links to contracts, annexures, amendments, KYC/KYB documents and executed versions.")

    with st.form("doc_form"):
        cols = st.columns(4)
        client_id = cols[0].text_input("Client ID")
        linked_record_type = cols[1].selectbox("Linked To", ["Client", "Contract", "AML", "Task"])
        linked_record_code = cols[2].text_input("Linked Record Code")
        document_type = cols[3].selectbox("Document Type", ["Draft", "Executed Contract", "Annexure", "Amendment", "KYC", "KYB", "Registry", "Approval", "Other"])
        document_name = st.text_input("Document Name")
        cols = st.columns(3)
        version = cols[0].text_input("Version", value="v1")
        status = cols[1].selectbox("Status", ["Draft", "Under Review", "Final", "Executed", "Expired", "Superseded"])
        expiry_date = cols[2].date_input("Expiry / Review Date", value=date.today() + timedelta(days=365))
        file_link = st.text_input("File Link")
        notes = st.text_area("Notes")
        if st.form_submit_button("Save Document") and document_name:
            code = next_code("DOC", "documents", "doc_code")
            execute("""INSERT INTO documents VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?)""", (code, client_id, linked_record_type, linked_record_code, document_name, document_type, version, status, file_link, str(expiry_date), notes, now()))
            st.success(f"Document saved: {code}")

    df = run_query("SELECT * FROM documents ORDER BY id DESC")
    st.dataframe(df, use_container_width=True, hide_index=True)

# -----------------------------
# REPORTS
# -----------------------------
elif page == "7. Reports Export":
    st.title("Reports Export")
    st.caption("Download monthly legal work summary, CLM status, AML risk report and document register.")

    tables = {
        "Legal Tasks": run_query("SELECT * FROM legal_tasks"),
        "Contracts": run_query("SELECT * FROM contracts"),
        "AML Cases": run_query("SELECT * FROM aml_cases"),
        "Documents": run_query("SELECT * FROM documents"),
        "Clients": run_query("SELECT * FROM clients")
    }
    selected = st.selectbox("Select Report", list(tables.keys()))
    df = tables[selected]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("Download CSV", df.to_csv(index=False), file_name=f"{selected.replace(' ','_')}_{date.today()}.csv")

# -----------------------------
# SETUP GUIDE
# -----------------------------
else:
    st.title("Setup Guide")
    st.markdown("""
### What this upgraded system now contains

1. **Executive Dashboard** — live summary of open legal work, active contracts, AML pending cases and documents.
2. **Legal Task Manager** — proper workflow tracking with owner, stage, status, approval, hours spent, next action and due date.
3. **Contract CLM** — complete contract lifecycle from business intake to closure, including risk rating, approval, signature status, repository link and renewal date.
4. **Legal Document Automation** — reusable templates with variables such as `{{client_name}}`, `{{counterparty}}`, `{{risk_rating}}` and generated drafts.
5. **AML / KYC / KYB Management** — Sumsub link, document request, KYC/KYB status, auto risk score, risk level, ongoing review and release decision.
6. **Documents Repository** — annexures, amendments, executed agreements, KYB/KYC documents and review dates.
7. **Reports Export** — download CSV reports for employer/team reporting.

### Working rule

- One client = one client master record.
- One agreement = one CLM contract record.
- One onboarding = one AML case.
- Every task must have a clear next action.
- Every executed document must be stored in the repository.
- Every high-risk AML case must remain on hold until compliance release is approved.
    """)

    st.warning("This Streamlit version is a strong free internal tracker and workflow tool. It is not a full replacement for paid enterprise CLM platforms unless user authentication, cloud database, role permissions and secure document storage are separately configured.")")

"""Intent catalogue derived from 2,000,000 historical ACME tickets (2023-2026).
34 question types cover 100% of the history and each maps to exactly one tier, so the
routing policy below is grounded in how HR Ops already works:

  Tier 1 (50%)  simple, answerable from policy or the employee's own records -> answered in real time
  Tier 2 (30%)  changes data / needs records or reports -> AI prepares (maker), analyst approves (checker)
  Tier 3 (20%)  sensitive -> specialist team; AI only prepares a confidential brief

Fields: kb = manifest topics to search (country-specific), records = systems-of-record lookups,
action = what the agent proposes (never applies), team = owner for tier 3.
"""
from __future__ import annotations

import re

C = r"(united states|united kingdom|india|singapore|ireland|australia|us|uk|in|sg|ie|au)"
INTENTS = [
    # ---------------- Tier 1: real-time answers
    dict(id="policy_question", tier=1, domain="Misc", label="General policy question (country)", pattern=r"quick question about .* policy",
         kb=[], records=[], action="clarify"),
    dict(id="handbook", tier=1, domain="Misc", label="Where is the employee handbook", pattern=r"employee handbook", kb=["HR Operations General FAQ"], records=[]),
    dict(id="contact", tier=1, domain="Misc", label="Who to contact for HR", pattern=r"who do i contact|who should i contact", kb=["HR Operations General FAQ"], records=[]),
    dict(id="paystub", tier=1, domain="Payroll", label="Show my latest paystub", pattern=r"(recent|latest|last) pay ?stub|show me my pay ?(stub|slip)", kb=["Pay Schedule & Payslips"], records=["payroll"]),
    dict(id="small_pay_error", tier=1, domain="Payroll", label="Small error on last paycheck", pattern=r"small error on my (last )?pay", kb=["Pay Schedule & Payslips", "Payroll Deductions"], records=["payroll"]),
    dict(id="next_pay_date", tier=1, domain="Payroll", label="Next pay date", pattern=r"next pay ?date", kb=["Pay Schedule & Payslips"], records=["payroll"]),
    dict(id="new_hire_enroll", tier=1, domain="Benefits", label="Benefits enrollment as new hire", pattern=r"enrol+ in benefits", kb=["Dependents & Enrollment", "Health Benefits Overview"], records=["benefits"]),
    dict(id="health_plans", tier=1, domain="Benefits", label="Available health plans", pattern=r"health plans (are )?available", kb=["Health Benefits Overview"], records=["benefits"]),
    dict(id="book_time_off", tier=1, domain="Time & Absence", label="Book time off", pattern=r"book time off", kb=["PTO / Annual Leave Policy"], records=["pto"], action="book_pto"),
    dict(id="parental_policy", tier=1, domain="Time & Absence", label="Parental leave policy", pattern=r"parental leave policy", kb=["Parental Leave Policy"], records=[]),
    dict(id="holidays", tier=1, domain="Time & Absence", label="Public holiday calendar", pattern=r"public holiday", kb=["Public Holiday Calendar"], records=[]),
    dict(id="days_off_level", tier=1, domain="Time & Absence", label="Annual leave entitlement by level", pattern=r"how many days off", kb=["PTO / Annual Leave Policy"], records=["pto"]),
    # ---------------- Tier 2: maker / checker
    dict(id="extended_leave", tier=2, domain="Time & Absence", label="Extended leave: PTO + parental", pattern=r"extended leave", kb=["Parental Leave Policy", "PTO / Annual Leave Policy"], records=["pto"], action="leave_case"),
    dict(id="bank_update", tier=2, domain="Payroll", label="Update bank account (direct deposit)", pattern=r"(update|change) my bank|direct deposit", kb=["Direct Deposit & Bank Changes"], records=["payroll"], action="bank_change", sensitive_data=True),
    dict(id="unknown_deduction", tier=2, domain="Payroll", label="Unrecognised payslip deduction", pattern=r"deduction i don.?t recogni", kb=["Payroll Deductions", "Pay Schedule & Payslips"], records=["payroll"], action="payroll_investigation"),
    dict(id="org_health", tier=2, domain="Misc", label="Org health report", pattern=r"org health", kb=["Org Health Reporting Guide"], records=["org"], action="report_org_health"),
    dict(id="headcount_report", tier=2, domain="Misc", label="Headcount report by department", pattern=r"headcount by department", kb=["Org Health Reporting Guide"], records=["org"], action="report_headcount"),
    dict(id="add_newborn", tier=2, domain="Benefits", label="Add newborn to coverage", pattern=r"add my newborn", kb=["Dependents & Enrollment"], records=["dependents", "benefits"], action="add_dependent"),
    dict(id="update_dependents", tier=2, domain="Benefits", label="Update dependents", pattern=r"update my dependents", kb=["Dependents & Enrollment"], records=["dependents", "benefits"], action="update_dependents"),
    dict(id="merit_explain", tier=2, domain="Compensation", label="How merit increases are calculated", pattern=r"merit increases", kb=["Salary Bands & Merit Increases"], records=["employee"]),
    dict(id="review_dates", tier=2, domain="Performance Management", label="Performance review cycle dates for team", pattern=r"performance review cycle dates", kb=["Performance Review Cycle"], records=["org"]),
    dict(id="bulk_transfer", tier=2, domain="Bulk Transactions", label="Bulk department transfer", pattern=r"department transfer for a group", kb=["Bulk Data Change Runbook"], records=[], action="bulk_change"),
    dict(id="manager_change", tier=2, domain="Employee/Manager Data Changes", label="Change an employee's manager", pattern=r"update my manager of employee|change (the )?manager (of|for) employee",
         kb=["Manager Reassignment Runbook"], records=["named_people"], action="change_manager"),
    dict(id="job_requisition", tier=2, domain="Employee/Manager Data Changes", label="Create job requisition from template employee", pattern=r"job requisition",
         kb=["Job Requisition Template Runbook"], records=["named_people"], action="create_requisition"),
    # ---------------- Tier 3: specialist teams (sensitive)
    dict(id="pay_significantly_wrong", tier=3, domain="Payroll", label="Pay significantly wrong (hardship)", pattern=r"pay is significantly wrong", kb=["Pay Schedule & Payslips"], records=["payroll"], team="Payroll specialists"),
    dict(id="confidential_complaint", tier=3, domain="Misc", label="Confidential workplace complaint", pattern=r"confidential complaint|harass|discriminat|retaliat", kb=[], records=[], team="Employee Relations"),
    dict(id="family_medical", tier=3, domain="Time & Absence", label="Family medical emergency (sick + unpaid leave)", pattern=r"family medical emergency|medical emergency", kb=["Sick Leave Policy"], records=["pto"], team="Leave & Accommodations"),
    dict(id="spouse_illness", tier=3, domain="Benefits", label="Spouse serious illness: benefits coverage", pattern=r"diagnosed with a serious illness|serious illness", kb=["Health Benefits Overview"], records=["benefits", "dependents"], team="Benefits specialists"),
    dict(id="bulk_comp_band", tier=3, domain="Bulk Transactions", label="Bulk compensation band change", pattern=r"bulk compensation band", kb=["Bulk Data Change Runbook", "Salary Bands & Merit Increases"], records=[], team="Total Rewards"),
    dict(id="offcycle_comp", tier=3, domain="Compensation", label="Off-cycle compensation adjustment", pattern=r"off-cycle compensation", kb=["Salary Bands & Merit Increases"], records=["named_people"], team="Total Rewards"),
    dict(id="pip", tier=3, domain="Performance Management", label="Put employee on a PIP", pattern=r"\bpip\b|performance improvement plan", kb=["Performance Improvement Plan (PIP) Process"], records=["named_people"], team="HR Business Partner"),
    dict(id="conduct_concern", tier=3, domain="Performance Management", label="Serious conduct concern", pattern=r"concerns about .*conduct", kb=["Performance Improvement Plan (PIP) Process"], records=["named_people"], team="Employee Relations"),
    dict(id="backdate_manager", tier=3, domain="Employee/Manager Data Changes", label="Backdate a manager change (audit)", pattern=r"backdate a manager change", kb=["Manager Reassignment Runbook"], records=["named_people"], team="HR Operations leadership"),
]
TIER_ROUTE = {1: "READY", 2: "TRANSACTION", 3: "NEEDS_APPROVAL"}
COUNTRY = {"united states": "US", "united kingdom": "UK", "india": "IN", "singapore": "SG", "ireland": "IE", "australia": "AU"}
COUNTRY_NAME = {v: k.title() for k, v in COUNTRY.items()}
LEVELS = {"ic": "IC", "manager": "Manager", "director": "Director", "md/vp": "MD/VP", "md": "MD/VP", "vp": "MD/VP"}

# Words that force tier 3 even for free text that matches nothing above (high recall on sensitive topics)
SENSITIVE = r"harass|discriminat|retaliat|bully|unsafe|assault|whistle|diagnos|surgery|disabilit|accommodation|mental health|pregnan|" \
            r"miscarriage|bereave|terminat|fired|layoff|severance|lawyer|attorney|lawsuit|visa|immigration|salary of|earns|pay equity|pip\b"


def match(text: str) -> dict | None:
    t = (text or "").lower()
    for it in INTENTS:
        if re.search(it["pattern"], t):
            return it
    return None


def mentioned_country(text: str) -> str | None:
    m = re.search(r"\b(united states|united kingdom|india|singapore|ireland|australia)\b", (text or "").lower())
    return COUNTRY[m.group(1)] if m else None


def mentioned_level(text: str) -> str | None:
    m = re.search(r"does an? (ic|manager|director|md/vp|md|vp) in", (text or "").lower())
    return LEVELS[m.group(1)] if m else None


def mentioned_people(text: str) -> list[str]:
    """Names in templates like 'employee Jane Doe', 'manager John Roe', 'for Jane Doe given', "about Jane Doe's"."""
    pats = [r"employee ([A-Z][\w'-]+(?: [A-Z][\w'-]+)+?)(?= to | on | as |[.,]|$)", r"manager ([A-Z][\w'-]+(?: [A-Z][\w'-]+)+?)(?=[.,]|$| )",
            r"adjustment for ([A-Z][\w'-]+(?: [A-Z][\w'-]+)+?) given", r"concerns about ([A-Z][\w'-]+(?: [A-Z][\w'-]+)+?)'s",
            r"manager change for ([A-Z][\w'-]+(?: [A-Z][\w'-]+)+?) due"]
    out = []
    for p in pats:
        for m in re.finditer(p, text or ""):
            n = m.group(1).strip()
            if n not in out and n.lower() not in ("of employee",):
                out.append(n)
    return out

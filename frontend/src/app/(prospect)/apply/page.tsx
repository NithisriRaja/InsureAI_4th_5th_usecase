"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Building2, Car, Check, HeartPulse, Home, type LucideIcon, PiggyBank, Send, Shield, Umbrella, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { AgentProgress } from "@/components/agent-progress";
import { cx, ErrorBox } from "@/components/ui";
import { ACTIVE_RUN, api, type LeadOut } from "@/lib/api";
import { LINE } from "@/lib/format";

/* ---------------------------------------------------------------- policy questions
 * What each policy line needs, taken from the backend rulebook (rulebook.py: required facts,
 * underwriting rules) and the product eligibility columns in products.csv. */

type Kind = "int" | "float" | "money" | "yesno" | "text" | "choice" | "multi" | "conditions" | "bmi" | "children";
type Field = { key: string; label: string; kind: Kind; required?: boolean; hint?: string; options?: [string, string][]; group?: string };

const LEVEL: [string, string][] = [["low", "Low"], ["medium", "Medium"], ["high", "High"]];
const CLAIMS: Field = { key: "prior_claims_3y", label: "Claims in the last 3 years", kind: "int", hint: "0 if none" };

const FIELDS: Record<string, Field[]> = {
  motor: [
    { key: "vehicle_year", label: "Vehicle year", kind: "int", required: true, hint: "e.g. 2019" },
    { key: "vehicle_value", label: "Vehicle value", kind: "money" },
    { key: "driving_years", label: "Years holding a driving licence", kind: "int", required: true },
    { key: "annual_mileage", label: "Annual mileage (km)", kind: "int" },
    CLAIMS,
  ],
  medical: [
    { key: "smoker", label: "Do you smoke?", kind: "yesno", required: true },
    { key: "bmi", label: "Height and weight", kind: "bmi" },
    { key: "dependents", label: "Dependents to cover", kind: "int", hint: "Family plans need at least 1" },
    { key: "pre_existing_conditions", label: "Existing medical conditions", kind: "conditions" },
  ],
  home: [
    { key: "property_type", label: "Property type", kind: "choice", options: [["apartment", "Apartment"], ["townhouse", "Townhouse"], ["villa", "Villa"]] },
    { key: "property_year", label: "Year built", kind: "int", required: true },
    { key: "rebuild_value", label: "Rebuild value", kind: "money", required: true, hint: "Cost to rebuild the property" },
    CLAIMS,
  ],
  personal_accident: [
    { key: "occupation_risk", label: "Occupation risk", kind: "choice", required: true, options: LEVEL, hint: "High = manual or hazardous work" },
    { key: "dependents", label: "Dependents", kind: "int" },
  ],
  life: [
    { key: "smoker", label: "Do you smoke?", kind: "yesno", required: true },
    { key: "term_years", label: "Cover term (years)", kind: "int", required: true },
    { key: "annual_income", label: "Annual income", kind: "money", required: true },
    { key: "existing_cover", label: "Existing life cover", kind: "money" },
    { key: "dependents", label: "Dependents", kind: "int" },
    { key: "bmi", label: "Height and weight", kind: "bmi" },
    { key: "occupation_risk", label: "Occupation risk", kind: "choice", options: LEVEL },
    { key: "pre_existing_conditions", label: "Existing medical conditions", kind: "conditions" },
  ],
  savings: [
    { key: "term_years", label: "Saving term (years)", kind: "int", required: true },
    { key: "annual_income", label: "Annual income", kind: "money", required: true },
    { key: "savings_goal", label: "Savings goal", kind: "choice", required: true, options: [["education", "Education"], ["retirement", "Retirement"], ["wealth", "Wealth building"], ["other", "Other"]] },
    { key: "risk_appetite", label: "Risk appetite", kind: "choice", options: [["conservative", "Conservative"], ["balanced", "Balanced"], ["growth", "Growth"]] },
    { key: "dependents", label: "Dependents", kind: "int", hint: "Education plans need at least 1" },
  ],
  family: [
    { group: "Your household", key: "adults_to_cover", label: "Adults to cover (including you)", kind: "int", hint: "e.g. 2" },
    { group: "Your household", key: "dependents", label: "Children / dependants to cover", kind: "int", required: true, hint: "0 if none" },
    { group: "Your household", key: "children", label: "Details of each child or dependant", kind: "children" },
    { group: "Your household", key: "primary_earner", label: "Are you the main earner?", kind: "yesno" },
    { group: "Health", key: "smoker", label: "Does the main applicant smoke?", kind: "yesno", required: true },
    { group: "Health", key: "bmi", label: "Height and weight of the main applicant", kind: "bmi" },
    { group: "Health", key: "pre_existing_conditions", label: "Existing medical conditions in the family", kind: "conditions" },
    { group: "Health", key: "family_medical_history", label: "Serious illness running in the family?", kind: "yesno", hint: "Parents or siblings, e.g. heart disease or cancer" },
    { group: "Health", key: "occupation_risk", label: "Main earner's occupation risk", kind: "choice", options: LEVEL, hint: "High = manual or hazardous work" },
    { group: "Money", key: "annual_income", label: "Household yearly income", kind: "money", required: true },
    { group: "Money", key: "monthly_budget", label: "Monthly budget for insurance", kind: "money", hint: "What the family is comfortable paying" },
    { group: "Money", key: "existing_cover", label: "Existing life cover", kind: "money" },
    { group: "Money", key: "existing_health_cover", label: "Already have health insurance?", kind: "yesno" },
    { group: "Plans", key: "term_years", label: "How many years of cover?", kind: "int", required: true, hint: "e.g. 20, until the children are independent" },
  ],
  group: [
    { key: "employee_count", label: "Number of employees", kind: "int", required: true },
    { key: "average_employee_age", label: "Average employee age", kind: "int" },
    { key: "industry_risk", label: "Industry risk", kind: "choice", options: LEVEL },
    CLAIMS,
  ],
};

const LINES: { key: string; blurb: string; icon: LucideIcon }[] = [
  { key: "family", blurb: "Health, income, illness, education and accident cover; we pick the best fit", icon: Users },
  { key: "motor", blurb: "Car cover, comprehensive or third-party", icon: Car },
  { key: "medical", blurb: "Individual and family health plans", icon: HeartPulse },
  { key: "home", blurb: "Buildings and contents", icon: Home },
  { key: "personal_accident", blurb: "Cover for accidents and injury", icon: Umbrella },
  { key: "life", blurb: "Term, critical illness, whole-of-life", icon: Shield },
  { key: "savings", blurb: "Education, regular and wealth plans", icon: PiggyBank },
  { key: "group", blurb: "Schemes for a company's employees", icon: Building2 },
];

const CONDITIONS: [string, string][] = [
  ["hypertension", "Hypertension"],
  ["diabetes", "Diabetes"],
  ["asthma", "Asthma"],
  ["heart_disease", "Heart disease"],
  ["cancer", "Cancer"],
  ["stroke", "Stroke"],
  ["other", "Other"],
];

/** The conditions to send: the ticked ones, with "Other" replaced by what the customer typed. */
function conditionsOf(f: Form, key: string): string[] {
  const v = f[key];
  const picked = Array.isArray(v) ? v : [];
  const typed = text(f, `${key}_other`)
    .split(/[,;]/)
    .map((x) => x.trim().toLowerCase().replace(/^[=+@-]+/, "").slice(0, 60))
    .filter(Boolean);
  return [...picked.filter((x) => x !== "other"), ...typed];
}

/** Fields in order, split under their group heading ("" = no heading). */
function groupsOf(fields: Field[]): [string, Field[]][] {
  const out: [string, Field[]][] = [];
  for (const f of fields) {
    const g = f.group ?? "";
    const last = out[out.length - 1];
    if (last && last[0] === g) last[1].push(f);
    else out.push([g, [f]]);
  }
  return out;
}

/* ---------------------------------------------------------------- form state */

type Value = string | boolean | string[];
type Form = Record<string, Value>;

const INITIAL: Form = {};
const BASIC_KEYS = ["first_name", "last_name", "dob", "gender", "nationality", "country_of_residence", "emirate", "email", "phone", "employment_status", "occupation", "income_band", "marital_status", "spouse_name", "spouse_age"];
// Basic details that are only stored for the record: the backend never uses them in a decision.
const PROTECTED_KEYS = ["gender", "nationality", "marital_status"];
const BASIC_FACTS = ["country_of_residence", "emirate", "employment_status", "occupation", "income_band"];

const GENDER: [string, string][] = [["female", "Female"], ["male", "Male"], ["prefer_not_to_say", "Prefer not to say"]];
const MARITAL: [string, string][] = [["single", "Single"], ["married", "Married"], ["divorced", "Divorced"], ["widowed", "Widowed"]];
const EMIRATES: [string, string][] = ["Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"].map((x) => [x, x]);
const EMPLOYMENT: [string, string][] = [["employed", "Employed"], ["self_employed", "Self-employed"], ["business_owner", "Business owner"], ["student", "Student"], ["homemaker", "Homemaker"], ["retired", "Retired"], ["unemployed", "Unemployed"]];
const INCOME: [string, string][] = [["under_60k", "Under AED 60,000"], ["60k_120k", "AED 60,000 – 120,000"], ["120k_240k", "AED 120,000 – 240,000"], ["240k_480k", "AED 240,000 – 480,000"], ["480k_960k", "AED 480,000 – 960,000"], ["over_960k", "Over AED 960,000"]];
const COUNTRIES: [string, string][] = [
  "United Arab Emirates", "Afghanistan", "Algeria", "Australia", "Bahrain", "Bangladesh", "Brazil", "Canada", "China", "Egypt", "France", "Germany", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Italy", "Japan", "Jordan", "Kenya", "Kuwait", "Lebanon", "Libya", "Malaysia", "Morocco", "Nepal", "Netherlands", "New Zealand", "Nigeria", "Oman", "Pakistan", "Palestine", "Philippines", "Qatar", "Russia", "Saudi Arabia", "Singapore", "South Africa", "South Korea", "Spain", "Sri Lanka", "Sudan", "Sweden", "Switzerland", "Syria", "Tunisia", "Turkey", "Ukraine", "United Kingdom", "United States", "Yemen", "Other",
].map((x) => [x, x]);
const text = (f: Form, k: string) => (typeof f[k] === "string" ? (f[k] as string).trim() : "");

function validateBasic(f: Form): Record<string, string> {
  const e: Record<string, string> = {};
  if (f.marital_status === "married") {
    if (!text(f, "spouse_name")) e.spouse_name = "Required";
    const age = Number(text(f, "spouse_age"));
    if (!text(f, "spouse_age")) e.spouse_age = "Required";
    else if (!(age >= 16 && age <= 110)) e.spouse_age = "Enter an age from 16 to 110";
  }
  if (!text(f, "first_name")) e.first_name = "Required";
  if (!text(f, "last_name")) e.last_name = "Required";
  const dob = text(f, "dob");
  if (!dob) e.dob = "Required";
  else if (new Date(dob) > new Date()) e.dob = "Can't be in the future";
  const email = text(f, "email");
  const phone = text(f, "phone");
  if (!email && !phone) e.email = "Enter an email or a phone number";
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) e.email = "Not a valid email";
  if (phone && !/^\+?\d{7,15}$/.test(phone.replace(/[\s()-]/g, ""))) e.phone = "7 to 15 digits";
  return e;
}

/** Lowest and highest cover offered per policy type (from products.csv). */
const COVER: Record<string, [number, number]> = {
  family: [50_000, 8_000_000],
  motor: [10_000, 600_000],
  medical: [150_000, 5_000_000],
  home: [50_000, 8_000_000],
  personal_accident: [100_000, 2_000_000],
  life: [100_000, 20_000_000],
  savings: [50_000, 20_000_000],
  group: [100_000, 10_000_000],
};
const aed = (n: number) => `AED ${n.toLocaleString("en-US")}`;

function validateCover(f: Form): Record<string, string> {
  const e: Record<string, string> = {};
  if (!f.product_line) e.product_line = "Choose a policy type";
  const amount = Number(text(f, "sum_insured"));
  const range = COVER[f.product_line as string];
  if (!(amount > 0)) e.sum_insured = "Enter an amount above 0";
  else if (range && amount > range[1]) e.sum_insured = `The most we cover is ${aed(range[1])}`;
  return e;
}

/** How many children / dependants to ask about, from the "dependants" answer (at most 10). */
const childCount = (f: Form) => Math.min(10, Math.max(0, Math.floor(Number(text(f, "dependents")) || 0)));

/** Body mass index from height (cm) and weight (kg), to one decimal; null until both are usable. */
function bmiOf(f: Form): number | null {
  const h = Number(text(f, "height_cm"));
  const w = Number(text(f, "weight_kg"));
  if (!(h >= 100 && h <= 230 && w >= 25 && w <= 300)) return null;
  return Math.round((w / (h / 100) ** 2) * 10) / 10;
}

function validateDetails(f: Form): Record<string, string> {
  const e: Record<string, string> = {};
  for (const fld of FIELDS[f.product_line as string] ?? []) {
    if (fld.kind === "children") {
      for (let i = 1; i <= childCount(f); i++) {
        if (!text(f, `child_${i}_name`)) e[`child_${i}_name`] = "Required";
        const age = text(f, `child_${i}_age`);
        if (!age) e[`child_${i}_age`] = "Required";
        else if (!(Number(age) >= 0 && Number(age) <= 110)) e[`child_${i}_age`] = "0 to 110";
      }
      continue;
    }
    if (fld.kind === "bmi") {
      const h = text(f, "height_cm");
      const w = text(f, "weight_kg");
      if ((h || w) && bmiOf(f) === null) e.bmi = "Enter a height of 100 to 230 cm and a weight of 25 to 300 kg";
      continue;
    }
    if (fld.required && (fld.kind === "yesno" ? !f[fld.key] : !text(f, fld.key))) e[fld.key] = "Required";
    if (fld.kind === "conditions" && Array.isArray(f[fld.key]) && (f[fld.key] as string[]).includes("other") && !text(f, `${fld.key}_other`))
      e[fld.key] = "Write the condition, or untick Other";
    const raw = text(f, fld.key);
    if (raw && (fld.kind === "int" || fld.kind === "money" || fld.kind === "float") && !(Number(raw) >= 0)) e[fld.key] = "Enter a number";
  }
  return e;
}

/** Declared facts for the API. Money goes in minor units (cents); the sum insured in whole units. */
function toDeclared(f: Form): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const fld of FIELDS[f.product_line as string] ?? []) {
    const v = f[fld.key];
    if (fld.kind === "children") {
      const kids = Array.from({ length: childCount(f) }, (_, i) => ({
        name: text(f, `child_${i + 1}_name`).replace(/[;|]/g, " ").replace(/^[=+@-]+/, "").trim(),
        age: Math.round(Number(text(f, `child_${i + 1}_age`))),
      })).filter((k) => k.name && Number.isFinite(k.age));
      if (kids.length) {
        out.children = kids.map((k) => `${k.name} (${k.age})`);
        out.youngest_child_age = Math.min(...kids.map((k) => k.age));
      }
    } else if (fld.kind === "bmi") {
      const b = bmiOf(f);
      if (b !== null) out.bmi = b;
    } else if (fld.kind === "conditions") out[fld.key] = conditionsOf(f, fld.key);
    else if (fld.kind === "multi") out[fld.key] = Array.isArray(v) ? v : [];
    else if (fld.kind === "yesno") {
      if (v) out[fld.key] = v === "yes";
    } else if (typeof v === "string" && v.trim()) {
      const n = Number(v);
      out[fld.key] = fld.kind === "int" ? Math.round(n) : fld.kind === "float" ? n : fld.kind === "money" ? Math.round(n * 100) : v.trim();
    }
  }
  return out;
}

function toBody(f: Form) {
  const opt = (k: string) => text(f, k) || null;
  return {
    first_name: text(f, "first_name"),
    last_name: text(f, "last_name"),
    dob: opt("dob"),
    email: opt("email"),
    phone: opt("phone"),
    product_line: f.product_line as string,
    sum_insured: Math.round(Number(text(f, "sum_insured"))),
    declared: {
      ...Object.fromEntries(BASIC_FACTS.filter((k) => text(f, k)).map((k) => [k, text(f, k)])),
      ...(f.marital_status === "married" ? { spouse_name: text(f, "spouse_name"), spouse_age: Math.round(Number(text(f, "spouse_age"))) } : {}),
      ...toDeclared(f),
    },
    protected: Object.fromEntries(PROTECTED_KEYS.filter((k) => text(f, k)).map((k) => [k, text(f, k)])),
    source: "web",
    // No consent step: sending the application counts as agreeing to be assessed and contacted
    // on the email or phone given.
    consent_profiling: true,
    consent_marketing: true,
    consent_email: !!text(f, "email"),
    consent_sms: !!text(f, "phone"),
  };
}

/* ---------------------------------------------------------------- inputs */

// Look of this page: soft pill fields on a white card in the app brand colour.
const PRIMARY = "bg-brand text-white shadow-[0_6px_18px_-4px_rgba(37,99,235,0.6)] hover:bg-brand-hover";
const INPUT = "h-10 w-full rounded-full border border-transparent bg-[#f1f4f9] px-4 text-[13px] text-ink placeholder:text-[#a9b2c0] transition focus:border-brand/50 focus:bg-white focus:outline-none focus-visible:outline-none focus:ring-4 focus:ring-brand/15";

function Row({ label, required, hint, error, children }: { label: string; required?: boolean; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <span className="mb-1.5 block pl-1 text-[11px] font-semibold text-ink">
        {label}
        {required && <span className="text-bad"> *</span>}
      </span>
      {children}
      {error ? <p className="mt-1 pl-1 text-xs text-bad">{error}</p> : hint && <p className="mt-1 pl-1 text-xs text-muted-ink">{hint}</p>}
    </div>
  );
}

function Select({ value, onChange, options, placeholder = "Select" }: { value: string; onChange: (v: string) => void; options: [string, string][]; placeholder?: string }) {
  return (
    <select className={cx(INPUT, "appearance-none bg-[length:16px] bg-[right_14px_center] bg-no-repeat pr-10", !value && "text-[#a9b2c0]")} style={{ backgroundImage: "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='%2364748b' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M4 6l4 4 4-4'/></svg>\")" }} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {options.map(([k, label]) => (
        <option key={k} value={k} className="text-ink">
          {label}
        </option>
      ))}
    </select>
  );
}

function Chips({ options, value, onChange, multi }: { options: [string, string][]; value: Value | undefined; onChange: (v: Value) => void; multi?: boolean }) {
  const picked = (k: string) => (multi ? Array.isArray(value) && value.includes(k) : value === k);
  const toggle = (k: string) => {
    if (!multi) return onChange(k);
    const cur = Array.isArray(value) ? value : [];
    onChange(cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]);
  };
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(([k, label]) => (
        <button
          key={k}
          type="button"
          aria-pressed={picked(k)}
          onClick={() => toggle(k)}
          className={cx("h-9 rounded-full px-4 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/20", picked(k) ? "bg-brand text-white shadow-[0_4px_12px_-3px_rgba(37,99,235,0.6)]" : "bg-[#f1f4f9] text-ink-2 hover:bg-[#e6ebf3]")}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Control({ fld, form, set, error, errors }: { fld: Field; form: Form; set: (k: string, v: Value) => void; error?: string; errors?: Record<string, string> }) {
  const v = form[fld.key];
  const str = typeof v === "string" ? v : "";
  let control: ReactNode;
  if (fld.kind === "children") {
    const n = childCount(form);
    if (n === 0) return null;
    return (
      <div className="space-y-3">
        <span className="block pl-1 text-[11px] font-semibold text-ink">{fld.label}</span>
        {Array.from({ length: n }, (_, i) => (
          <div key={i} className="grid grid-cols-[1fr_7rem] gap-3">
            <Row label={`Child ${i + 1}: name`} required error={errors?.[`child_${i + 1}_name`]}>
              <input className={INPUT} value={text(form, `child_${i + 1}_name`)} onChange={(e) => set(`child_${i + 1}_name`, e.target.value)} />
            </Row>
            <Row label="Age" required error={errors?.[`child_${i + 1}_age`]}>
              <input className={INPUT} type="number" min={0} max={110} inputMode="numeric" value={text(form, `child_${i + 1}_age`)} onChange={(e) => set(`child_${i + 1}_age`, e.target.value)} />
            </Row>
          </div>
        ))}
      </div>
    );
  }
  if (fld.kind === "bmi") {
    const b = bmiOf(form);
    const num = (key: string, placeholder: string) => (
      <input className={INPUT} type="number" min={0} inputMode="decimal" placeholder={placeholder} value={text(form, key)} onChange={(e) => set(key, e.target.value)} />
    );
    return (
      <Row label={fld.label} error={error} hint={b !== null ? `BMI worked out for you: ${b}` : "We work out the BMI from these"}>
        <div className="grid grid-cols-2 gap-3">
          {num("height_cm", "Height (cm), e.g. 170")}
          {num("weight_kg", "Weight (kg), e.g. 70")}
        </div>
      </Row>
    );
  }
  if (fld.kind === "yesno") {
    control = <Chips options={[["yes", "Yes"], ["no", "No"]]} value={v} onChange={(x) => set(fld.key, x)} />;
  } else if (fld.kind === "choice") {
    control = <Chips options={fld.options ?? []} value={v} onChange={(x) => set(fld.key, x)} />;
  } else if (fld.kind === "conditions" || fld.kind === "multi") {
    control = <Chips multi options={fld.kind === "multi" ? (fld.options ?? []) : CONDITIONS} value={v} onChange={(x) => set(fld.key, x)} />;
  } else {
    control = (
      <input
        className={INPUT}
        type={fld.kind === "text" ? "text" : "number"}
        min={0}
        step={fld.kind === "float" ? "0.1" : 1}
        inputMode={fld.kind === "text" ? "text" : "decimal"}
        value={str}
        onChange={(e) => set(fld.key, e.target.value)}
      />
    );
  }
  if (fld.kind === "conditions" && Array.isArray(v) && v.includes("other")) {
    control = (
      <div className="space-y-2.5">
        {control}
        <input className={INPUT} placeholder="Write the condition, e.g. thyroid disorder (separate several with commas)" value={text(form, `${fld.key}_other`)} onChange={(e) => set(`${fld.key}_other`, e.target.value)} autoFocus />
      </div>
    );
  }
  const hint = fld.kind === "conditions" ? "Leave all unselected if none" : fld.kind === "multi" ? "Choose all that apply" : fld.hint;
  return (
    <Row label={fld.label} required={fld.required} hint={hint} error={error}>
      {control}
    </Row>
  );
}

/* ---------------------------------------------------------------- page */

const STEPS = ["Basic Details", "Policy Type", "Cover Details"];

function Stepper({ step }: { step: number }) {
  return (
    <ol className="mx-auto mb-8 flex max-w-md items-start">
      {STEPS.map((label, i) => (
        <li key={label} className="relative flex flex-1 flex-col items-center text-center">
          {i > 0 && <span className={cx("absolute top-3 right-1/2 h-px w-full", i <= step ? "bg-brand" : "bg-rule")} aria-hidden />}
          <span className={cx("relative z-10 grid size-6 place-items-center rounded-full text-[11px] font-bold", i <= step ? "bg-brand text-white" : "bg-[#eef1f6] text-muted-ink")}>
            {i < step ? <Check className="size-3" aria-hidden /> : i + 1}
          </span>
          <span className={cx("mt-1.5 text-[11px] font-semibold", i === step ? "text-ink" : "text-muted-ink")}>{label}</span>
        </li>
      ))}
    </ol>
  );
}

const HEADING = ["Basic Details", "What does the customer need?", "About the cover"];

function Backdrop({ children }: { children: ReactNode }) {
  return (
    <div className="relative isolate -mx-4 -my-6 overflow-hidden px-4 py-10 sm:-mx-6 sm:px-6" style={{ background: "linear-gradient(to bottom, #dbe8ff 0, #dbe8ff 400px, #0a1128 400px)" }}>
      <span className="pointer-events-none absolute -top-16 left-1/2 -z-10 size-72 rounded-full bg-gradient-to-br from-[#93b4f5] to-[#dbe8ff] opacity-80" aria-hidden />
      <span className="pointer-events-none absolute top-40 -left-12 -z-10 size-28 rounded-full bg-gradient-to-br from-[#7aa2f0] to-[#dbe8ff]" aria-hidden />
      <span className="pointer-events-none absolute top-48 -right-10 -z-10 size-32 rounded-full bg-gradient-to-br from-[#a9c4f7] to-[#3b6fe0]" aria-hidden />
      <span className="pointer-events-none absolute -bottom-20 left-10 -z-10 size-72 rounded-full bg-gradient-to-br from-[#2f5fd0] to-[#12243d]" aria-hidden />
      <span className="pointer-events-none absolute right-16 -bottom-6 -z-10 size-20 rounded-full bg-gradient-to-br from-[#6f9bf0] to-[#2563eb]" aria-hidden />
      {children}
    </div>
  );
}

export default function ApplyPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Form>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const set = (k: string, v: Value) => {
    setForm((f) => ({ ...f, [k]: v }));
    setErrors((e) => (e[k] ? { ...e, [k]: "" } : e));
  };
  // Switching the policy type drops the answers that belong to the old one.
  const pickLine = (line: string) => {
    if (line === form.product_line) return;
    const keep = Object.fromEntries(Object.entries(form).filter(([k]) => BASIC_KEYS.includes(k) || k === "sum_insured"));
    setForm({ ...keep, product_line: line });
    setErrors({});
  };

  const submit = useMutation({
    // refresh: submitting a customer who already exists takes these answers and checks them again.
    mutationFn: () => api<{ lead_id: string; created: boolean; run: { status: string } | null }>("/leads", { method: "POST", query: { refresh: true }, body: toBody(form) }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["leads-all"] });
      // The agents are queued: wait for them here. Otherwise there is nothing to wait for, so open it.
      if (r.run && ACTIVE_RUN.includes(r.run.status)) setLeadId(r.lead_id);
      else router.push(`/customers/${r.lead_id}?from=apply`);
    },
  });

  const [leadId, setLeadId] = useState<string | null>(null);
  const waiting = useQuery({
    queryKey: ["apply-lead", leadId],
    queryFn: () => api<LeadOut>(`/leads/${leadId}`),
    enabled: !!leadId,
    refetchInterval: 1_500,
  });
  const runStatus = waiting.data?.latest_run?.status;
  useEffect(() => {
    if (leadId && waiting.data && !ACTIVE_RUN.includes(runStatus ?? "")) router.push(`/customers/${leadId}?from=apply`);
  }, [leadId, waiting.data, runStatus, router]);
  // Never trap the user: open the customer page after three minutes whatever the state.
  useEffect(() => {
    if (!leadId) return;
    const t = setTimeout(() => router.push(`/customers/${leadId}?from=apply`), 180_000);
    return () => clearTimeout(t);
  }, [leadId, router]);

  const validators = [validateBasic, validateCover, validateDetails];
  const next = () => {
    const e = validators[step](form);
    setErrors(e);
    if (Object.keys(e).length) return;
    if (step < 2) setStep(step + 1);
    else submit.mutate();
  };
  const line = form.product_line as string | undefined;

  if (leadId)
    return (
      <Backdrop>
        <div className="mx-auto max-w-[640px]">
          <AgentProgress name={text(form, "first_name")} />
        </div>
      </Backdrop>
    );

  return (
    <Backdrop>
      <div className="mx-auto max-w-[640px]">
        <div className="space-y-5 rounded-3xl bg-white p-6 shadow-[0_24px_60px_-20px_rgba(10,17,40,0.45)] sm:px-12 sm:py-9">
          <header className="text-center">
            <h1 className="font-display text-lg font-bold text-ink">New Application</h1>
            <p className="mx-auto mt-1 max-w-md text-[11px] text-muted-ink">The AI checks the rules and recommends the best policy, with reasons.</p>
          </header>
          <Stepper step={step} />
          <h2 className="font-display text-sm font-bold text-ink">{HEADING[step]}</h2>
          {step === 0 && (
            <>
              <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
                <Row label="First name" required error={errors.first_name}>
                  <input className={INPUT} value={text(form, "first_name")} onChange={(e) => set("first_name", e.target.value)} autoComplete="given-name" />
                </Row>
                <Row label="Last name" required error={errors.last_name}>
                  <input className={INPUT} value={text(form, "last_name")} onChange={(e) => set("last_name", e.target.value)} autoComplete="family-name" />
                </Row>
                <Row label="Date of birth" required error={errors.dob}>
                  <input className={INPUT} type="date" max={new Date().toISOString().slice(0, 10)} value={text(form, "dob")} onChange={(e) => set("dob", e.target.value)} />
                </Row>
                <Row label="Gender">
                  <Select value={text(form, "gender")} onChange={(v) => set("gender", v)} options={GENDER} />
                </Row>
                <Row label="Nationality">
                  <Select value={text(form, "nationality")} onChange={(v) => set("nationality", v)} options={COUNTRIES} />
                </Row>
                <Row label="Country of residence">
                  <Select value={text(form, "country_of_residence")} onChange={(v) => set("country_of_residence", v)} options={COUNTRIES} />
                </Row>
                <Row label="Emirate of residence">
                  <Select value={text(form, "emirate")} onChange={(v) => set("emirate", v)} options={EMIRATES} />
                </Row>
                <Row label="Email" error={errors.email} hint="An email or a phone number is needed">
                  <input className={INPUT} type="email" value={text(form, "email")} onChange={(e) => set("email", e.target.value)} autoComplete="email" />
                </Row>
                <Row label="Mobile number" error={errors.phone}>
                  <input className={INPUT} type="tel" value={text(form, "phone")} onChange={(e) => set("phone", e.target.value)} autoComplete="tel" placeholder="+971 50 123 4567" />
                </Row>
                <Row label="Employment status">
                  <Select value={text(form, "employment_status")} onChange={(v) => set("employment_status", v)} options={EMPLOYMENT} />
                </Row>
                <Row label="Occupation">
                  <input className={INPUT} value={text(form, "occupation")} onChange={(e) => set("occupation", e.target.value)} placeholder="e.g. Accountant" />
                </Row>
                <Row label="Annual income (AED)">
                  <Select value={text(form, "income_band")} onChange={(v) => set("income_band", v)} options={INCOME} />
                </Row>
                <Row label="Marital status">
                  <Select value={text(form, "marital_status")} onChange={(v) => set("marital_status", v)} options={MARITAL} />
                </Row>
                {form.marital_status === "married" && (
                  <>
                    <Row label="Spouse's name" required error={errors.spouse_name}>
                      <input className={INPUT} value={text(form, "spouse_name")} onChange={(e) => set("spouse_name", e.target.value)} />
                    </Row>
                    <Row label="Spouse's age" required error={errors.spouse_age}>
                      <input className={INPUT} type="number" min={16} max={110} inputMode="numeric" value={text(form, "spouse_age")} onChange={(e) => set("spouse_age", e.target.value)} />
                    </Row>
                  </>
                )}
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <div>
                <span className="mb-2 block pl-1 text-xs font-semibold text-ink">Choose a policy type <span className="text-bad">*</span></span>
                <div className="grid gap-3 sm:grid-cols-2">
                  {LINES.map(({ key, blurb, icon: Icon }) => (
                    <button
                      key={key}
                      type="button"
                      aria-pressed={line === key}
                      onClick={() => pickLine(key)}
                      className={cx("flex items-center gap-3 rounded-2xl border-2 p-3.5 text-left transition-colors", line === key ? "border-brand bg-brand-soft" : "border-transparent bg-[#f1f4f9] hover:bg-[#e6ebf3]")}
                    >
                      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-white text-brand">
                        <Icon className="size-5" aria-hidden />
                      </span>
                      <span className="min-w-0">
                        <span className="block font-semibold text-ink">{LINE[key]}</span>
                        <span className="block text-xs text-muted-ink">{blurb}</span>
                      </span>
                    </button>
                  ))}
                </div>
                {errors.product_line && <p className="mt-2 text-xs text-bad">{errors.product_line}</p>}
              </div>
              <Row label="Cover amount (sum insured)" required error={errors.sum_insured} hint={COVER[line ?? ""] ? `Between ${aed(COVER[line ?? ""][0])} and ${aed(COVER[line ?? ""][1])} for this policy type` : "Whole currency units, e.g. 250000"}>
                <input className={INPUT} type="number" min={0} max={COVER[line ?? ""]?.[1]} placeholder={COVER[line ?? ""] ? `Up to ${COVER[line ?? ""][1].toLocaleString("en-US")}` : undefined} inputMode="numeric" value={text(form, "sum_insured")} onChange={(e) => set("sum_insured", e.target.value)} />
              </Row>
            </>
          )}

          {step === 2 && line && (
            <>
              <p className="text-sm text-muted-ink">
                A few questions about the <strong className="text-ink">{LINE[line]}</strong> cover. Fields marked * are needed for the check.
              </p>
              {groupsOf(FIELDS[line]).map(([title, fields]) => (
                <section key={title} className="space-y-4">
                  {title && <h3 className="flex items-center gap-2 pt-2 text-sm font-bold text-ink"><span className="size-1.5 rounded-full bg-brand" aria-hidden />{title}</h3>}
                  <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
                    {fields.map((fld) => (
                      <div key={fld.key} className={fld.kind === "conditions" || fld.kind === "multi" || fld.kind === "children" ? "sm:col-span-2" : undefined}>
                        <Control fld={fld} form={form} set={set} error={errors[fld.key]} errors={errors} />
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </>
          )}

          {submit.isError && <ErrorBox error={submit.error} />}

          <div className="flex flex-col items-center gap-3 pt-4">
            <button type="button" onClick={next} disabled={submit.isPending} className={cx("inline-flex h-10 items-center gap-2 rounded-full px-8 text-[13px] font-bold focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30 transition-colors disabled:opacity-60", PRIMARY)}>
              {step < 2 ? (
                <>
                  Save &amp; Continue <ArrowRight className="size-4" aria-hidden />
                </>
              ) : (
                <>
                  <Send className="size-4" aria-hidden /> {submit.isPending ? "Checking..." : "Get recommendation"}
                </>
              )}
            </button>
            {step > 0 && (
              <button type="button" onClick={() => setStep(step - 1)} disabled={submit.isPending} className="inline-flex items-center gap-1 text-xs font-semibold text-muted-ink hover:text-ink">
                <ArrowLeft className="size-3.5" aria-hidden /> Back
              </button>
            )}
          </div>
        </div>
      </div>
    </Backdrop>
  );
}

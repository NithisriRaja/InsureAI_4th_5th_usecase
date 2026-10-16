const CURRENCY = process.env.NEXT_PUBLIC_CURRENCY ?? "AED";

/** Whole currency units (the API's lead `sum_insured` and LLM-facing amounts). */
export function money(major: number | null | undefined): string {
  if (major === null || major === undefined) return "—";
  return `${CURRENCY} ${Math.round(major).toLocaleString("en-US")}`;
}

export function human(key: string): string {
  const s = key.replace(/^declared\./, "").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function date(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function ageFrom(dob: string | null | undefined): number | null {
  if (!dob) return null;
  const d = new Date(dob);
  const now = new Date();
  let a = now.getFullYear() - d.getFullYear();
  if (now.getMonth() < d.getMonth() || (now.getMonth() === d.getMonth() && now.getDate() < d.getDate())) a--;
  return a >= 0 ? a : null; // a future date of birth is invalid data, not an age
}

export const LINE: Record<string, string> = {
  motor: "Motor",
  medical: "Medical",
  home: "Home",
  personal_accident: "Personal accident",
  life: "Life & protection",
  savings: "Savings & wealth",
  group: "Employee benefits",
};

export const ACTION: Record<string, string> = {
  contact_and_quote: "Contact & quote",
  nurture: "Nurture",
  refer_to_underwriter: "Refer to underwriter",
  request_info: "Request info",
  do_not_contact: "Do not contact",
};

export const TEAM: Record<string, string> = {
  sales: "Sales & marketing",
  adviser: "Adviser",
  underwriting: "Underwriter",
};

export const OWNER: Record<string, string> = {
  direct: "Direct",
  broker: "Broker",
  adviser: "Adviser",
  employer: "Employer",
};

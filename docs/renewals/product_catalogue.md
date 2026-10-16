# Product lines and products

The insurance products in this demo, grouped by product line: **7 lines, 15 products**, amounts in AED.

They are modelled on the types of cover UAE insurers commonly offer (compulsory motor third party, the Dubai Essential Benefits health plan, home, life, savings and employee benefits). Names, limits and prices are realistic placeholders, **not any company's actual products or rates**; replace them with the insurer's own catalogue before a client pilot.

Source of truth: `rulebook.PRODUCTS` in `backend/`, loaded into `backend/data/products.csv` by the seed script.

## At a glance

| Product line | Sold through | Products |
|---|---|---|
| Motor | broker, direct | Motor Third Party Liability, Motor Comprehensive |
| Medical | broker, direct | Essential Health Plan, Enhanced Family Health Plan |
| Home | broker, direct | Home Contents Insurance, Home Buildings & Contents Insurance |
| Personal accident | broker, direct | Personal Accident Cover |
| Life & protection | adviser | Term Life Protection, Critical Illness Protection, Unit-Linked Protection & Savings Plan |
| Savings & wealth | adviser | Education Savings Plan, Regular Savings Plan, Single-Premium Investment Plan |
| Employee benefits | broker, employer | Group Health Insurance, Group Life Insurance |

## Motor

| Product | What it covers | Ages | Cover (sum insured) | Typical premium | Max retention discount | Stays in force by | Extra cover offered |
|---|---|---|---|---|---|---|---|
| **Motor Third Party Liability** (`MOTOR_TPL`) | UAE-compulsory cover for injury to others and damage to their property, with third-party property damage up to AED 2,000,000. | 18–80 | AED 1,000,000 – AED 2,000,000 | from AED 850 per year | 10% | Yearly renewal | Personal Accident Cover |
| **Motor Comprehensive** (`MOTOR_COMPREHENSIVE`) | Own damage, theft, fire and third-party liability, with agency or premier-garage repair and UAE-wide roadside assistance. | 18–75 | AED 20,000 – AED 800,000 | from AED 1,800 per year | 15% | Yearly renewal | Personal Accident Cover |

## Medical

| Product | What it covers | Ages | Cover (sum insured) | Typical premium | Max retention discount | Stays in force by | Extra cover offered |
|---|---|---|---|---|---|---|---|
| **Essential Health Plan** (`MEDICAL_ESSENTIAL`) | Basic health cover meeting the Dubai Essential Benefits Plan, annual limit AED 150,000 within a restricted network. | 18–65 | AED 150,000 – AED 250,000 | from AED 950 per year | 5% | Yearly renewal | Personal Accident Cover |
| **Enhanced Family Health Plan** (`MEDICAL_FAMILY`) | Family health cover with a wide UAE network, out-patient, maternity and dental benefits, annual limit up to AED 5,000,000. | 18–65 | AED 1,000,000 – AED 5,000,000 | from AED 12,000 per year | 12% | Yearly renewal | Personal Accident Cover |

## Home

| Product | What it covers | Ages | Cover (sum insured) | Typical premium | Max retention discount | Stays in force by | Extra cover offered |
|---|---|---|---|---|---|---|---|
| **Home Contents Insurance** (`HOME_CONTENTS`) | Contents and personal belongings for tenants and owners against fire, theft, water damage and accidental damage. | 18–85 | AED 50,000 – AED 750,000 | from AED 450 per year | 10% | Yearly renewal | — |
| **Home Buildings & Contents Insurance** (`HOME_BUILDINGS_CONTENTS`) | Building and contents cover for owner-occupied villas and apartments, including alternative accommodation. | 21–85 | AED 500,000 – AED 8,000,000 | from AED 1,800 per year | 15% | Yearly renewal | — |

## Personal accident

| Product | What it covers | Ages | Cover (sum insured) | Typical premium | Max retention discount | Stays in force by | Extra cover offered |
|---|---|---|---|---|---|---|---|
| **Personal Accident Cover** (`PA_INDIVIDUAL`) | Lump sum for accidental death or permanent disability, worldwide, 24 hours a day. | 18–65 | AED 100,000 – AED 2,000,000 | from AED 300 per year | 10% | Yearly renewal | — |

## Life & protection

| Product | What it covers | Ages | Cover (sum insured) | Typical premium | Max retention discount | Stays in force by | Extra cover offered |
|---|---|---|---|---|---|---|---|
| **Term Life Protection** (`LIFE_TERM`) | Level life cover for a fixed term of 10 to 30 years; pays a lump sum on death or terminal illness. | 18–60 | AED 250,000 – AED 10,000,000 | from AED 1,500 per year, paid monthly | 0% | Ongoing premiums, 10–30 year term | Critical Illness Protection |
| **Critical Illness Protection** (`LIFE_CRITICAL_ILLNESS`) | Lump sum on first diagnosis of a listed critical illness such as cancer, heart attack or stroke. | 18–55 | AED 100,000 – AED 3,000,000 | from AED 1,200 per year, paid monthly | 0% | Ongoing premiums, 10–20 year term | — |
| **Unit-Linked Protection & Savings Plan** (`LIFE_UNIT_LINKED`) | Regular-premium plan for 10 to 25 years combining life cover with savings invested in a choice of funds. | 18–60 | AED 250,000 – AED 10,000,000 | from AED 12,000 per year, paid monthly | 0% | Ongoing premiums, 10–25 year term | Critical Illness Protection |

## Savings & wealth

| Product | What it covers | Ages | Cover (sum insured) | Typical premium | Max retention discount | Stays in force by | Extra cover offered |
|---|---|---|---|---|---|---|---|
| **Education Savings Plan** (`SAVINGS_EDUCATION`) | Regular savings towards a child's university fees, with life cover that keeps the plan going if the parent dies. | 21–55 | AED 100,000 – AED 2,000,000 | from AED 6,000 per year, paid monthly | 0% | Ongoing premiums + milestone, 5–18 year term | Term Life Protection |
| **Regular Savings Plan** (`SAVINGS_REGULAR`) | Flexible monthly savings for 10 to 25 years into a choice of funds, with a death benefit. | 18–60 | AED 100,000 – AED 5,000,000 | from AED 6,000 per year, paid monthly | 0% | Ongoing premiums, 10–25 year term | Term Life Protection |
| **Single-Premium Investment Plan** (`SAVINGS_SINGLE_PREMIUM`) | One-off investment into a managed fund range with a death benefit; reviewed with the adviser every year. | 18–75 | AED 100,000 – AED 20,000,000 | from AED 100,000 single premium | 0% | Annual review, 5–10 year term | — |

## Employee benefits

| Product | What it covers | Ages | Cover (sum insured) | Typical premium | Max retention discount | Stays in force by | Extra cover offered |
|---|---|---|---|---|---|---|---|
| **Group Health Insurance** (`GROUP_MEDICAL`) | Employer health scheme for staff and dependants, meeting UAE mandatory health insurance rules. | n/a (company) | AED 150,000 – AED 5,000,000 | from AED 60,000 per year | 8% | Scheme anniversary (yearly) | — |
| **Group Life Insurance** (`GROUP_LIFE`) | Employer-paid death-in-service cover, usually a multiple of each employee's salary. | n/a (company) | AED 500,000 – AED 20,000,000 | from AED 15,000 per year | 8% | Scheme anniversary (yearly) | — |

## Documents asked for at renewal or review

| Line | Documents |
|---|---|
| Motor | Vehicle registration (Mulkiya) copy, Valid UAE driving licence, Vehicle inspection report, No-claims certificate |
| Medical | Renewed Emirates ID, Residence visa copy, Updated dependant details |
| Home | Updated contents valuation, Ejari tenancy contract, Title deed copy, List of high-value items |
| Personal accident | Occupation declaration, Beneficiary nomination form |
| Life & protection | Beneficiary nomination form, FATCA / CRS self-certification form, Renewed Emirates ID, Health declaration for reinstatement |
| Savings & wealth | FATCA / CRS self-certification form, Source of funds declaration, Renewed Emirates ID, Updated investment risk profile |
| Employee benefits | Updated employee census, Renewed trade licence, Signed renewal acceptance |

## How the agents use this

- **Renewal agent:** each product's lifecycle sets when a policy needs attention (expiry, scheme anniversary, missed premium, review or milestone); grace days decide when cover is in grace or lapsed.
- **Retention agent:** the max discount caps any retention offer (fixed-term products only).
- **Recommendation agent:** the extra cover listed is what may be suggested; the customer must be inside its age band and not already hold it.
- **Who approves:** life and savings products are regulated advice and go to an adviser.

See [business_rules.md](business_rules.md) for the full rules and limits. Check the sample data any time with `python -m backend.scripts.audit_data`.

# Where every number comes from

| What is said | Source | How fresh |
|---|---|---|
| Which exact drug was meant, and its package codes | RxNorm, US National Library of Medicine | Looked up live; kept up to 7 days |
| "Pharmacies pay about…" | CMS NADAC, a weekly survey of what retail pharmacies pay wholesalers | Latest weekly publication; kept up to 12 hours |
| "Cost Plus Drugs sells it for…" | Cost Plus Drugs public price API | Live; kept up to 12 hours. Before shipping |
| "Amazon RxPass covers it for $5 a month" | Amazon's RxPass list | Read by hand; the date is in the answer's sources |
| "Medicare's negotiated price … this year" | CMS fact sheet, negotiated prices for 2026 (10 drugs) | Published August 2024 |
| "From January 2027, Medicare's negotiated price…" | CMS fact sheet, negotiated prices for 2027 (15 drugs) | Published November 2025 |
| "…stops at $2,100" | Medicare.gov, Part D costs for 2026 | Yearly |

## What each figure is not

- **What pharmacies pay** is a cost, not a price. Nobody can buy at it.
- **A cash price** is paid outside insurance. It usually doesn't count toward
  a deductible or Medicare's yearly limit, so someone who will reach that
  limit can pay more over the year by paying less per refill.
- **RxPass** needs Prime, isn't available with Medicaid, and doesn't ship to
  California or Washington. Amazon lists medicines without strengths, so a
  match means "may be covered". It is never the basis for "you're overpaying".
- **Medicare's negotiated price** is what Medicare pays. What a person pays
  depends on their plan. CMS gives one figure for every strength and form of
  a drug, for a typical 30-day supply; one package can cost more or less.
- A negotiated price is quoted as current only in its first year. After that
  CMS raises it with inflation, and the old figure is not repeated.

## A comparison is only ever like for like

Two prices are compared only when both belong to package codes (NDCs) that
RxNorm lists for the same clinical drug: same ingredient, same strength, same
form. A cash quote for "metformin 500 mg" that turns out to be the
extended-release tablet is not used to price the regular one.

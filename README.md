# Fair Refill

**An Alexa+ add-on that answers one question: am I paying more than I need to for this prescription?**

One in five Americans over 65 has skipped medicine because of cost. And in a
JAMA study, for more than a quarter of generic prescriptions the insured
patient's copay was *more* than the drug's cash price (Van Nuys et al., 2018,
using 2013 claims). Most people never find out, because nobody tells them and
they don't know to ask.

> *"Alexa, ask Fair Refill if I'm overpaying for my atorvastatin. I pay $40 a month."*
>
> "You may be paying about $35 a month more than you need to for atorvastatin 20 mg tablet. Cost Plus Drugs sells it for $5.41 a month plus shipping, and Amazon RxPass covers it for $5 a month with Prime, outside insurance. Ask your pharmacist whether paying cash would cost less than your insurance. They're allowed to tell you."

> **Status: in development, private.** The pricing core below is built and
> tested on live data. The MCP server and the simulated Alexa+ front end come
> next. Built for the Amazon Developer Hackathon, Alexa+ track.

## Where every number comes from

| Source | What it is | How it's used |
|---|---|---|
| [RxNorm](https://lhncbc.nlm.nih.gov/RxNav/) (National Library of Medicine) | Identifies the exact drug (ingredient, strength and form) and lists its package codes (NDCs) | Makes sure a price is only ever compared for the **identical** drug |
| [NADAC](https://data.medicaid.gov/) (CMS, weekly) | What pharmacies pay per tablet | "Pharmacies pay about 84 cents a month" |
| [Cost Plus Drugs API](https://costplusdrugs.github.io/apidocs/) | A cash price anyone can buy at | The reference for "you may be overpaying"; a quote counts only if its NDC is the identical drug's |
| [CMS negotiated prices, 2026](https://www.cms.gov/files/document/fact-sheet-negotiated-prices-initial-price-applicability-year-2026.pdf) | Medicare's price for 10 brand drugs | "Medicare's negotiated price for Eliquis is $231" |
| [Amazon RxPass](https://pharmacy.amazon.com/rxpass) | $5 a month for listed generics, with Prime | Mentioned along with its conditions; never the basis for "you're overpaying" |

## The rules it keeps

- **The identical drug only.** It never suggests a different medicine, strength or dose, or skipping one.
- **Brand to generic is a question** for the pharmacist or doctor, never an instruction.
- **Every figure says what it is:** what pharmacies pay, a price you can buy at, or Medicare's price. Each is dated.
- **It says what it can't do.** Inhalers, liquids and creams are priced per gram or millilitre, and it doesn't estimate those yet.
- **Every answer ends with a next step:** your pharmacist, your doctor or your plan. Since 2018, federal law lets pharmacists tell you when paying cash costs less.

```bash
pip install -e ".[dev]"
pytest -q                 # offline: replays responses recorded from the live APIs
```

## Licence

Apache-2.0.

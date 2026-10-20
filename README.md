# Fair Refill

**An Alexa+ add-on that answers one question: am I paying more than I need to for this prescription?**

One in five Americans aged 65 and over reported not taking a medicine as
prescribed because of its cost (Dusetzina et al., JAMA Network Open, 2023; a
2022 survey). And in a
JAMA study, for more than a quarter of generic prescriptions the insured
patient's copay was *more* than the drug's cash price (Van Nuys et al., 2018,
using 2013 claims). Most people never find out, because nobody tells them and
they don't know to ask.

> *"Alexa, ask Fair Refill if I'm overpaying for my atorvastatin. I pay $40 a month."*
>
> "You may be paying about $29 a month more than you need to for atorvastatin 20 mg tablet. Cost Plus Drugs delivers it for about $11 a month, or $3.83 a month if your doctor prescribes three months at once, and Amazon RxPass covers it for $5 a month with Prime, outside insurance. Cash prices usually don't count toward your deductible or Medicare's yearly limit. Ask your pharmacist whether paying cash would cost less than your insurance. They're allowed to tell you."

> **Status: in development, private.** Built for the Amazon Developer
> Hackathon, Alexa+ track.

## What a month costs, measured

On 20 October the add-on's own sources were asked about every tablet and capsule strength of the 37 common generics it keeps ready, 275 in all ([docs/savings.md](docs/savings.md), made by `tools/measure_savings.py`):

- Cost Plus Drugs sells 35 of the 37 generics.
- Where it sells a strength, a month delivered costs **$11.21 at the median**, and 88% cost under $15.
- Three months in one fill comes to **$4.38 a month at the median**.

These are prices, not what anyone pays: copays vary by plan, and no public source lists them. Anyone whose copay is above the delivered price for their medicine is who the add-on is for, and the add-on tells them which side of that line they're on.

## Run it

```bash
pip install -e .
python -m fair_refill.simulator      # http://127.0.0.1:8765
```

That starts two things on one port:

- **The add-on:** an MCP server at `/mcp`, over Streamable HTTP. It speaks protocol 2025-11-25, the version Alexa+ documents, and newer versions too. Seven tools: check a price, price the one you picked, save / list / check all / remove from your list, and Medicare's yearly limits. Its card is an MCP App (`ui://fair-refill/card.html`).
- **A simulated Alexa+** at `/`. It uses the add-on the way Alexa+ would: as an MCP client, speaking its answers and hosting its card on an Echo Show-style screen. Alexa+'s own developer tools aren't open to hackathon entrants, so this stands in for them. The add-on is real either way.

On start it also looks up every strength of 53 commonly asked-about medicines in the background, and again every five hours, so those questions are answered from a local copy in well under a second instead of the 5 to 15 seconds a first lookup takes. A full round takes eight to ten minutes. `python -m fair_refill.prewarm` runs one round by hand; `FAIR_REFILL_PREWARM=0` turns it off. A kept price is the source's own answer, never more than 12 hours old, and is still spoken with the source's date.

Point any MCP client at `http://127.0.0.1:8765/mcp` to use the add-on directly. `python -m fair_refill.server` runs the add-on alone.

## Where every number comes from

| Source | What it is | How it's used |
|---|---|---|
| [RxNorm](https://lhncbc.nlm.nih.gov/RxNav/) (National Library of Medicine) | Identifies the exact drug (ingredient, strength and form) and lists its package codes (NDCs) | Makes sure a price is only ever compared for the **identical** drug |
| [NADAC](https://data.medicaid.gov/) (CMS, weekly) | What pharmacies pay per tablet | "Pharmacies pay about 84 cents a month" |
| [Cost Plus Drugs API](https://costplusdrugs.github.io/apidocs/) | A cash price anyone can buy at, for one month and for three | The reference for "you may be overpaying", with its $5.25 shipping added; a quote counts only if its NDC is the identical drug's |
| [CMS negotiated prices, 2026](https://www.cms.gov/files/document/fact-sheet-negotiated-prices-initial-price-applicability-year-2026.pdf) | Medicare's price for 10 brand drugs | "Medicare's negotiated price for Eliquis is $231" |
| [CMS negotiated prices, 2027](https://www.cms.gov/files/document/fact-sheet-negotiated-prices-ipay-2027.pdf) | Medicare's price for 15 more, from 1 January 2027 | "From January 2027, Medicare's negotiated price for Ozempic is about $274" |
| [Amazon RxPass](https://pharmacy.amazon.com/rxpass) | $5 a month for listed generics, with Prime | Mentioned along with its conditions; never the basis for "you're overpaying" |

## The rules it keeps

- **The identical drug only.** It never suggests a different medicine, strength or dose, or skipping one.
- **Brand to generic is a question** for the pharmacist or doctor, never an instruction.
- **Every figure says what it is:** what pharmacies pay, a price you can buy at, or Medicare's price. Each is dated.
- **A cash price is the price at the door.** Cost Plus's quote leaves out $5.25 shipping an order, so that's added before anything is said. "You may be overpaying" is measured against a month at a time, delivered: the prescription the person holds now.
- **Three months at once is offered, not advised.** The fee and the shipping are per fill, so three months in one fill costs far less per month. It needs a different prescription, so it's said as "if your doctor prescribes three months at once".
- **A cash price comes with its catch.** Money paid outside insurance usually doesn't count toward a deductible or Medicare's yearly limit, so for someone on several medicines the cheaper refill can be the dearer year. Every answer that gives a cash price says so.
- **A price that starts in January is said as coming,** not as this year's. And a negotiated price is quoted as current only in its first year, because CMS raises it with inflation after that.
- **It says what it can't do.** Inhalers, liquids and creams are priced per gram or millilitre, and it doesn't estimate those yet.
- **Every answer ends with a next step:** your pharmacist, your doctor or your plan. Since 2018, federal law lets pharmacists tell you when paying cash costs less.

## Run it on AWS

[`deploy/aws/`](deploy/aws/README.md) builds a container and runs it on Amazon ECS Express Mode at a public HTTPS address. There, each browser keeps its own list of medicines under a random key, so no visitor sees another's.

```bash
deploy/aws/deploy.sh
```

## The Agent Skill

[`skills/fair-refill/`](skills/fair-refill/SKILL.md) is an [Agent Skill](https://agentskills.io) for the add-on: how to hold the conversation around its tools, what to say, and the rules an answer must keep. Copy the folder into an agent's skills directory. The add-on also serves it, at `skill://fair-refill/SKILL.md`, so a client that connects can read how it's meant to be used. A test keeps the skill and the server in step: it names every tool the server has and none it doesn't.

```bash
pip install -e ".[dev]"
pytest -q                 # offline: replays responses recorded from the live APIs
```

## The demo film

The film in the submission is made from the product, not recorded by hand:

```bash
pip install -e ".[video]"
FAIR_REFILL_PORT=8791 python -m fair_refill.simulator    # in another terminal
python video/capture.py     # frames: the real page after each question and each answer
python video/narrate.py     # voices (GEMINI_API_KEY), or --engine say for a free draft
python video/verify.py      # a second model transcribes the voices and checks every word
python video/build.py       # video/out/fair-refill-demo.mp4, and it must be under 3 minutes
```

- **The pictures are the simulator's own page.** A link can carry a conversation (`/?ask=first+question&ask=second`), and the page asks each question in turn without speaking. The same links work for sharing an answer.
- **The assistant's voice reads only what the add-on answered** when the frames were taken (`video/out/answers.json`). The script holds the questions and the narration, and no words for the assistant.
- **The voices are checked.** Hosted voice models slip: one take said "three months at months", and the next dropped "your deductible or" from a sentence. `verify.py` fails a take that drops, adds or changes two or more words in a row, and lists one-word differences for a person to judge.

## Licence

Apache-2.0.

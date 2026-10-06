# Fair Refill — submission

> **DRAFT, 6 Oct 2026. Delete this box before submitting.**
> Open items are marked **TODO**. Checked against the official rules
> (https://amazonappdev2026.devpost.com/rules) on 6 Oct: judging is four
> equally weighted criteria (tech implementation, design, potential impact,
> quality of the idea), and product feedback has five set questions.

**Amazon Developer Hackathon 2026, Alexa+ track.**
Solo entry by Aditya (GitHub `Aditya-galaxy`).

| | |
|---|---|
| Repository | https://github.com/Aditya-galaxy/fair-refill (Apache-2.0) — **TODO:** make public, or add `testing@devpost.com` and the six Amazon reviewers as collaborators |
| Demo video | **TODO:** link (under 3 minutes, public on YouTube or Vimeo) |
| Friction log | [FRICTION_LOG.md](FRICTION_LOG.md) |
| Product feedback | [below](#product-feedback) |

## In one sentence

Fair Refill is an Alexa+ add-on that answers one spoken question, "am I paying
more than I need to for this prescription?", using live public prices for the
identical medicine, and ends every answer by sending the person to their
pharmacist.

## The problem

One in five Americans over 65 has skipped medicine because of cost. In a JAMA
study of 2013 claims (Van Nuys et al., 2018), the insured patient's copay was
higher than the drug's cash price for more than a quarter of generic
prescriptions. Since 2018 federal law has let pharmacists say when paying cash
is cheaper, but only if the patient asks, and most people don't know there is
anything to ask.

The people this affects most are the people a voice assistant suits best:
older, on several medicines, and not likely to compare prices across three
websites.

## What it does

> **"Alexa, ask Fair Refill if I'm overpaying for my atorvastatin 20 milligrams. I pay forty dollars a month."**
>
> "You may be paying about $35 a month more than you need to for atorvastatin
> 20 mg tablet. Cost Plus Drugs sells it for $5.41 a month plus shipping, and
> Amazon RxPass covers it for $5 a month with Prime, outside insurance. Cash
> prices usually don't count toward your deductible or Medicare's yearly
> limit. Ask your pharmacist whether paying cash would cost less than your
> insurance. They're allowed to tell you."

That is the add-on's real answer on 6 Oct 2026, from CMS's weekly price file
and Cost Plus's price that day. It also:

- asks which one when a name is ambiguous ("Which atorvastatin do you take: 4 mg/ml liquid, 10 mg tablet, 20 mg tablet, 40 mg tablet, or 80 mg tablet?") and prices the exact choice;
- corrects a misheard name ("lipiter" to Lipitor) and says what it found;
- gives Medicare's 2026 negotiated price for the ten drugs that have one (Eliquis: $231 for 30 days, down from $521) and the $2,100 yearly cap;
- gives the price that starts on 1 January 2027 for the fifteen drugs CMS negotiated next ("From January 2027, Medicare's negotiated price for Ozempic is about $274 for a typical 30-day supply, down from a list price of $959"), and during Medicare open enrollment (15 Oct to 7 Dec) says that now is the time to check how each plan covers it;
- keeps a list of someone's medicines and checks them all at once, with a total;
- shows a card on devices with a screen: what you pay, the comparison price, the next step, and the sources.

## How it's built

- **An MCP server** over Streamable HTTP with seven tools, written to Alexa+'s requirements for MCP add-ons: one tool per thing a person wants, a short spoken answer in every result, stable IDs for choices, and no error codes reaching the person.
- **The card is an MCP App** (`ui://fair-refill/card.html`), served by the add-on itself.
- **An Agent Skill** (`skills/fair-refill/`) says how to hold the conversation around the tools and which rules an answer must keep. The add-on serves it as a resource too, and a test fails if the skill and the server's tools drift apart.
- **Four public sources**, joined on the exact drug:
  RxNorm (National Library of Medicine) identifies the medicine and its package codes;
  CMS NADAC gives what pharmacies pay, weekly;
  the Cost Plus Drugs API gives a cash price anyone can buy at;
  CMS's 2026 and 2027 fact sheets give Medicare's negotiated prices.
  Amazon RxPass is mentioned where its list includes the medicine, with its conditions.
- **A simulated Alexa+** that uses the add-on as an MCP client, speaks its answers, and hosts its card on an Echo Show-style screen. Alexa+'s own developer tools are not open to entrants (friction log, entry 1), so this stands in for them. The add-on is the real thing; only the front end is simulated.
- **Pre-warming.** A first lookup touches three public APIs and took 6 to 12 seconds when measured on 6 Oct. The server looks up every strength of 53 commonly asked-about medicines when it starts and every five hours after, which made the same questions answer in under 100 ms through the simulator. A kept price is the source's own answer, at most 12 hours old.
- **108 tests**, all offline: they replay 98 responses recorded from the live APIs, so they test real data without the network. CI runs them on Python 3.11 and 3.13.

Run it:

```bash
pip install -e .
python -m fair_refill.simulator      # http://127.0.0.1:8765
```

## The rules it keeps

This is health-adjacent, so what it refuses to do matters as much as what it does.

- **The identical drug only.** Two prices are compared only when both are for package codes of the same clinical drug: same ingredient, strength and form. It never suggests a different medicine, strength or dose, or skipping one. A test fails if an answer contains "switch to", "skip" or "take less".
- **Brand to generic is a question** for the pharmacist or doctor, never an instruction.
- **A cash price comes with its catch.** Money paid outside insurance usually doesn't count toward a deductible or Medicare's yearly limit, so someone on several medicines could pay less per refill and more over the year. Every answer that gives a cash price says so.
- **Every figure says what it is** (what pharmacies pay, a price you can buy at, or Medicare's price) and carries its date.
- **It says what it can't do.** Inhalers, liquids and creams are priced per gram or millilitre; it says it can't compare those yet instead of estimating.
- **Every answer ends with a next step:** the pharmacist, the doctor or the plan.
- **A person's medicine list stays on their machine.** It is health information and is never sent anywhere.

## What's not there yet

- It has not run on Alexa+ itself, only against the simulator and generic MCP clients.
- Price comparisons cover tablets and capsules only. Injections and inhalers get an answer only where Medicare has negotiated a price for the brand.
- Strengths are said the way RxNorm writes them, so 50 micrograms of levothyroxine is found but spoken as "0.05 mg".
- One cash-price source. Cost Plus doesn't carry every drug (Eliquis, for one), and for those the answer has no "you can buy it for" figure.
- The JAMA figure is from 2013 claims. It is the best published number and the answer to "is this still true" is what the add-on is for.

## Demo video outline (under 3 minutes)

**TODO: record.** Start the simulator a few minutes early so the answers are warm.

1. (0:00) The problem, in two sentences, over the simulator's idle screen.
2. (0:20) "Am I overpaying for my atorvastatin 20 milligrams? I pay forty dollars a month." Answer and card.
3. (0:50) "Check my metformin." It asks which one; pick "the 500 milligram extended release".
4. (1:15) "How much should Lipitor 20 cost?" Brand against generic, as a question for the pharmacist.
5. (1:40) "Is my Eliquis too expensive?" Medicare's negotiated price and the yearly cap. Then "What will Ozempic cost me next year?" for the January 2027 price.
6. (2:00) "Remember this", then "check all my medicines". The total.
7. (2:20) "What about my albuterol inhaler?" It says what it can't do.
8. (2:35) Ten seconds on the build: MCP server, card as an MCP App, sources on screen. Close on the pharmacist line.

## Product feedback

The full detail, with workarounds, is in [FRICTION_LOG.md](FRICTION_LOG.md).
The three things that would have changed this project most:

1. **Give entrants something to test Alexa+ against.** The Alexa+ track exists to build for the MCP Toolkit, CLI and Web Simulator, and all three are preview-only for selected partners. This entry had to build its own Alexa+ stand-in, so the one thing it can't show is the add-on running on Alexa+. A rate-limited sandbox for the Web Simulator would fix that. Failing that, the preview-only notice belongs on every setup page, not only in the FAQ.
2. **Say up front what works outside the US.** Ring's API supports US-located devices only, and the Playground doesn't cover enough of the payloads to stand in. That ruled the Ring track out before any code was written. A table of which track features non-US entrants can demo would save others the same week.
3. **Pin starter samples to an SDK version.** The MCP Python SDK renamed `FastMCP` to `MCPServer` in v2, so samples written for v1 fail on a fresh install. The SDK's own error message points to the fix, which is how it should be done.

What worked well: building the add-on as a plain MCP server meant it could be developed and tested with any MCP client, with no Amazon account or device, and the same server should be what Alexa+ calls. Having the card as an MCP App kept the screen experience inside the add-on.

**TODO (Aditya):** add anything from your own time with the docs, the forum, or registration that isn't in the friction log. Each new item should also go in `FRICTION_LOG.md`; it counts for up to 10% of the score.

# Fair Refill — submission

**Amazon Developer Hackathon 2026, Alexa+ track.**
Solo entry by Aditya (GitHub `Aditya-galaxy`).

| | |
|---|---|
| Repository | https://github.com/Aditya-galaxy/fair-refill (Apache-2.0) |
| Demo video | _link to be added_ |
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
> "You may be paying about $29 a month more than you need to for atorvastatin
> 20 mg tablet. Cost Plus Drugs delivers it for about $11 a month, or $3.83 a
> month if your doctor prescribes three months at once, and Amazon RxPass
> covers it for $5 a month with Prime, outside insurance. Cash prices usually
> don't count toward your deductible or Medicare's yearly limit. Ask your
> pharmacist whether paying cash would cost less than your insurance. They're
> allowed to tell you."

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
  the Cost Plus Drugs API gives a cash price anyone can buy at, for one month and for three;
  CMS's 2026 and 2027 fact sheets give Medicare's negotiated prices.
  Amazon RxPass is mentioned where its list includes the medicine, with its conditions.
- **A simulated Alexa+** that uses the add-on as an MCP client, speaks its answers, and hosts its card on an Echo Show-style screen. Alexa+'s own developer tools are not open to entrants (friction log, entry 1), so this stands in for them. The add-on is the real thing; only the front end is simulated.
- **Pre-warming.** A first lookup touches three public APIs and took 6 to 12 seconds when measured on 6 Oct. The server looks up every strength of 53 commonly asked-about medicines when it starts and every five hours after, which made the same questions answer in under 100 ms through the simulator. A kept price is the source's own answer, at most 12 hours old.
- **118 tests**, all offline: they replay 111 responses recorded from the live APIs, so they test real data without the network. CI runs them on Python 3.11 and 3.13.

Run it:

```bash
pip install -e .
python -m fair_refill.simulator      # http://127.0.0.1:8765
```

## The rules it keeps

This is health-adjacent, so what it refuses to do matters as much as what it does.

- **The identical drug only.** Two prices are compared only when both are for package codes of the same clinical drug: same ingredient, strength and form. It never suggests a different medicine, strength or dose, or skipping one. A test fails if an answer contains "switch to", "skip" or "take less".
- **Brand to generic is a question** for the pharmacist or doctor, never an instruction.
- **A cash price is the price at the door.** Cost Plus's quote leaves out $5.25 shipping an order, so that's added before anything is said or compared. Someone paying $9 a month is not told they're overpaying because a quote says $5.41.
- **Three months at once is offered, not advised.** Cost Plus charges its fee per fill and shipping per order, so three months in one fill costs far less per month ($3.83 against $10.66 for atorvastatin 20 mg). It needs a different prescription, so the answer says "if your doctor prescribes three months at once".
- **A cash price comes with its catch.** Money paid outside insurance usually doesn't count toward a deductible or Medicare's yearly limit, so someone on several medicines could pay less per refill and more over the year. Every answer that gives a cash price says so.
- **Every figure says what it is** (what pharmacies pay, a price you can buy at, or Medicare's price) and carries its date.
- **It says what it can't do.** Inhalers, liquids and creams are priced per gram or millilitre; it says it can't compare those yet instead of estimating.
- **Every answer ends with a next step:** the pharmacist, the doctor or the plan.
- **A person's medicine list stays on their machine.** It is health information and is never sent anywhere.

## What's not there yet

- It has not run on Alexa+ itself, only against the simulator and generic MCP clients.
- Price comparisons cover tablets and capsules only. Injections and inhalers get an answer only where Medicare has negotiated a price for the brand.
- One cash-price source. Cost Plus doesn't carry every drug (Eliquis, for one), and for those the answer has no "you can buy it for" figure.
- The JAMA figure is from 2013 claims. It is the best published number and the answer to "is this still true" is what the add-on is for.

## Product feedback

The rules ask five questions. The detail behind each answer, with steps and
workarounds, is in [FRICTION_LOG.md](FRICTION_LOG.md).

### Which tools, APIs and SDKs were used

- The Model Context Protocol: a self-hosted server over Streamable HTTP (spec 2025-11-25 and later), built with the MCP Python SDK 2.x.
- MCP Apps, for the card shown on devices with a screen.
- The open Agent Skills format, for `skills/fair-refill/`.
- Alexa+'s published requirements and design guidance for MCP add-ons, which the tools, the spoken answers and the card were written to.
- Not used, because they are closed to entrants: the Alexa+ Category SDK, MCP Toolkit, CLI and Web Simulator.

### What worked well

- **Building on an open protocol.** Because the add-on is a plain MCP server, it could be built and tested with any MCP client, with no Amazon account or device. The same server is what Alexa+ would call.
- **MCP Apps for the screen.** The card is a resource the add-on serves, so the spoken answer and the screen come from one place and can't disagree.
- **Voice guidance that is specific.** "Offer at most five options", "no error codes to the customer" and the far-field type scale are concrete enough to write tests against, and this project does.
- **The MCP SDK's error messages.** The one breaking change met on the way named its own fix (friction log, entry 4).

### What needs improvement

1. **Give entrants something to test Alexa+ against.** The Alexa+ track exists to build for the MCP Toolkit, CLI and Web Simulator, and all are preview-only for selected partners. This entry had to build its own Alexa+ stand-in, so the one thing it can't show is the add-on running on Alexa+. A rate-limited sandbox for the Web Simulator would fix that (entry 1).
2. **Say what Alexa+ does with an Agent Skill.** The track's "Build with Agent Skills" link leads to skills for scaffolding MCP Apps, not to how a skill is written or how Alexa+ loads one (entry 3).
3. **Say up front what works outside the US.** Ring's API supports US-located devices only, and the Playground doesn't cover enough of the payloads to stand in. That ruled the Ring track out before any code was written (entry 2).
4. **Pin starter samples to an SDK version** (entry 4).

### Onboarding

Mixed. Choosing the open standards made the first working server quick: no
account, no device, no approval. Finding out what could and couldn't be used
took longer than building it. Several Alexa+ setup pages read as if the tools
were available, and only the FAQ says they are preview-only. A notice at the
top of each of those pages would have saved that time.

### Would you build with these again

_To be answered by Aditya._

---

## Before submitting

Delete this section once every box is ticked.

- [ ] Record the demo video (plan below) and put its link in the table at the top. It must be under 3 minutes and public on YouTube or Vimeo, with no third-party logos on screen.
- [ ] Answer "Would you build with these again" above.
- [ ] Read the "Steps taken" lines in `FRICTION_LOG.md` and correct any that aren't what you did. Add anything else you hit; the log is worth up to 10%.
- [ ] Make the repository public, or add `testing@devpost.com`, `chris-trag`, `knmeiss`, `giolaq`, `anishamalde`, `mosesroth` and `emersonsklar` as collaborators. Invitations expire after 7 days.
- [ ] On Devpost: paste the description, choose the Alexa+ track and any mini challenges, and submit before Fri 23 Oct, 12:00 PT (Sat 24 Oct, 00:30 IST).

### Recording plan

Run `python -m fair_refill.prewarm` first, then start the simulator, so every answer is instant.

1. (0:00) The problem, in two sentences, over the simulator's idle screen.
2. (0:20) "Am I overpaying for my atorvastatin 20 milligrams? I pay forty dollars a month." Answer and card.
3. (0:50) "Check my metformin 500." It asks which one; say "the extended release".
4. (1:15) "How much should Lipitor 20 cost?" Brand against generic, as a question for the pharmacist.
5. (1:40) "Is my Eliquis too expensive?" Medicare's negotiated price and the yearly cap. Then "What will Ozempic cost me next year?" for the January 2027 price.
6. (2:00) "Remember this", then "check all my medicines". The total.
7. (2:20) "What about my albuterol inhaler?" It says what it can't do.
8. (2:35) Ten seconds on the build: MCP server, card as an MCP App, the Agent Skill. Close on the pharmacist line.

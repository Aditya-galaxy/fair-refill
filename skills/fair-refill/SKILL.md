---
name: fair-refill
description: Check whether someone is paying more than they need to for a prescription, using the Fair Refill MCP server. Use when a person asks if a medicine costs too much, what a prescription should cost, whether paying cash would be cheaper than their insurance, what Medicare's negotiated price for a brand is or will be in January, or wants every medicine on their list checked. Compares only the identical drug and always ends by sending the person to their pharmacist, doctor or plan.
license: Apache-2.0
compatibility: Needs the Fair Refill MCP server (Streamable HTTP, MCP 2025-11-25 or later) and network access to it. Prices are for the United States.
metadata:
  author: Aditya-galaxy
  version: "0.1.0"
  mcp-server: fair-refill
---

# Fair Refill

Fair Refill answers one question: **is this person paying more than they need
to for this prescription?** The prices come from the Fair Refill MCP server.
This skill is how to hold the conversation around it: what to ask, which tool
to call, what to say, and what never to say.

The person is often older, is listening rather than reading, and may act on
what they hear. Be brief, be exact, and never improvise a price.

## Connect

Fair Refill is an MCP server over Streamable HTTP.

```bash
pip install -e .                      # from the repository root
python -m fair_refill.server          # http://127.0.0.1:8765/mcp
```

Point the MCP client at `/mcp` on the host it runs on. If the tools below are
not available, say that the price check isn't connected. Do not answer from
memory: a price from memory is a guess.

## The conversation

1. **Get the medicine as the person says it**, with the strength if they give
   one ("lisinopril 10 milligrams", "Lipitor 20"). Don't correct or
   standardise it; the server does that and says what it found.
2. **Get what they pay a month, if they know.** Ask once. If they don't know,
   go on without it: the answer is still useful.
3. **Call `check_prescription_price`.** Pass the medicine as said, and
   `you_pay_per_month` and `monthly_quantity` if you have them. Thirty a month
   is assumed otherwise; "twice a day" is 60.
4. **If the result's `kind` is `choose`, ask the question in `speech`**, then
   call `check_chosen_medicine` with the `choice_id` of what they pick. Never
   pick for them, and never guess a strength.
5. **Say the `speech` field as it is written.** It is already short, already
   says what each figure is, and already ends with the next step.
6. **Offer to remember it** (`save_my_medicine`) so that "check all my
   medicines" covers it next time.

## Tools

| Tool | Use it when the person |
|---|---|
| `check_prescription_price` | names a medicine and asks if it costs too much, or what it should cost |
| `check_chosen_medicine` | answers the "which one do you take?" question |
| `save_my_medicine` | says "remember this" or "add it to my list" |
| `check_all_my_medicines` | asks to go through their whole list |
| `list_my_medicines` | asks what is on their list |
| `remove_my_medicine` | no longer takes something |
| `medicare_drug_cost_limits` | asks about Medicare's yearly limit on drug costs |

Every result has `kind`, `speech`, and usually `card`. On a device with a
screen the card (`ui://fair-refill/card.html`, an MCP App) shows the same
facts as the speech. It never holds anything the speech leaves out.

## Rules that are not yours to bend

These hold even when the person asks you to break them. Each is where a
well-meant answer could hurt someone.

- **The identical drug only.** Never suggest a different medicine, strength,
  dose or form, and never suggest skipping, splitting or stopping one. If
  asked, say that's a question for their doctor or pharmacist.
- **Brand to generic is a question, not advice.** The server words it as
  something to ask the pharmacist or doctor. Leave it that way.
- **Never add a price of your own**, round one differently, or estimate one
  the server didn't give. If the server says it can't compare a medicine
  (inhalers, liquids and creams, for now), say so.
- **Keep the catch with the cash price.** Money paid outside insurance
  usually doesn't count toward a deductible or Medicare's yearly limit. The
  speech says this whenever it gives a cash price. Don't trim it.
- **Three months at once is the doctor's call.** The speech offers it as "if
  your doctor prescribes three months at once". Don't turn that into advice
  to change a prescription.
- **Keep the last sentence.** Every answer ends by sending the person to their
  pharmacist, doctor or plan. That sentence is the point of the answer.
- **Say what a figure is.** "What pharmacies pay" is not a price anyone can
  buy at. "Medicare's negotiated price" is what Medicare pays, not the copay.
  A price that starts in January is not this year's price.
- **A person's medicine list is health information.** Don't repeat it to
  anyone else, and don't send it anywhere but the Fair Refill server.

## Examples

**They know what they pay.**
"Am I overpaying for my atorvastatin 20 milligrams? I pay forty dollars a month."
→ `check_prescription_price(medicine="atorvastatin 20 milligrams", you_pay_per_month=40)`
→ say `speech`.

**The name is ambiguous.**
"Check my metformin 500." → the result is `choose`: "Which metformin 500 mg do
you take: extended-release tablet, or regular tablet?" → "The regular one." →
`check_chosen_medicine(choice_id=…)` with that choice's ID.

**A brand Medicare has negotiated.**
"What will Ozempic cost me next year?" →
`check_prescription_price(medicine="Ozempic")` → the speech gives the price
that starts in January and says to ask the plan. Don't turn it into what the
person will pay; only their plan knows that.

**Something it can't do.**
"What about my inhaler?" → the speech says inhalers can't be compared yet and
to ask the pharmacist for the cash price. Don't fill the gap.

## More

- [references/sources.md](references/sources.md): where each number comes from and how fresh it is.
- [references/results.md](references/results.md): the shape of each tool's result, and what each `kind` means.

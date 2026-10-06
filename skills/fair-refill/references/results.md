# Tool results

Every tool returns an object with `kind` and `speech`. Read `speech` to the
person as written.

## `kind`

| `kind` | Meaning | What to do |
|---|---|---|
| `answer` | A price check, or a plain statement that this medicine can't be compared | Say `speech`. Show `card` if there is a screen |
| `choose` | The name fits more than one medicine | Ask `speech`, then call `check_chosen_medicine` with the chosen `choice_id` from `choices` |
| `not_found` | No medicine by that name | Say `speech`; it asks for the name on the label |
| `unavailable` | A price source didn't answer | Say `speech`; it asks them to try again in a minute. Don't substitute a remembered price |
| `saved`, `removed`, `list`, `empty` | The saved list changed or was read | Say `speech` |
| `summary` | Every saved medicine was checked | Say `speech`; `medicines` has one row each |

## Fields

- `speech`: one to five short sentences, with no codes or jargon.
- `card`: `title`, up to two `details`, one `action`, and `sources`. Nothing
  on it is missing from `speech`.
- `choices`: for `choose`, up to five `{choice_id, name}`. Offer them as given.
- `medicine`: for `answer`, the `{choice_id, name}` that was priced. Pass its
  `choice_id` to `save_my_medicine`. It is absent when the answer was for a
  whole brand rather than one strength; then there is nothing to save yet.

## Arguments

- `medicine`: the name as said, with the strength if given.
- `monthly_quantity`: tablets or capsules a month. Default 30.
- `you_pay_per_month`: dollars, if the person said.
- `choice_id`: only ever a value a previous result returned.

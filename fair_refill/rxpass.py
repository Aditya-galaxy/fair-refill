"""
Amazon RxPass: $5 a month for any number of eligible generics, for Prime members.

The list below is Amazon's, from https://pharmacy.amazon.com/rxpass, read on
2026-09-25. Amazon lists medicines without strengths, so a match only ever
means "may be covered — check your strength". Three conditions travel with
every mention, because each can make it the wrong choice for someone:

  * it doesn't go through insurance, so for someone on Medicare it doesn't
    count toward the $2,100 yearly limit on covered drug costs;
  * it isn't available to people on Medicaid or CHIP;
  * it doesn't ship to California or Washington.

Two spellings on Amazon's page are corrected here: "Hycosamine" is
hyoscyamine, and "Subvenite" is a brand of lamotrigine.
"""

from __future__ import annotations

PRICE_PER_MONTH = 5
SOURCE = "https://pharmacy.amazon.com/rxpass"
CHECKED = "2026-09-25"
CAVEATS = ("It doesn't use insurance, so it won't count toward Medicare's yearly limit",
           "It isn't available with Medicaid or in California or Washington")

# (ingredients, form) as a person would say the form; see rxnorm.Drug.spoken.
ELIGIBLE: frozenset[tuple[frozenset[str], str]] = frozenset({
    (frozenset({"allopurinol"}), "tablet"),
    (frozenset({"amlodipine", "olmesartan"}), "tablet"),
    (frozenset({"amlodipine"}), "tablet"),
    (frozenset({"amoxicillin"}), "tablet"),
    (frozenset({"atorvastatin"}), "tablet"),
    (frozenset({"azelastine"}), "eye drops"),
    (frozenset({"benztropine"}), "tablet"),
    (frozenset({"bupropion"}), "extended-release tablet"),
    (frozenset({"bupropion"}), "tablet"),
    (frozenset({"cephalexin"}), "capsule"),
    (frozenset({"cyclobenzaprine"}), "tablet"),
    (frozenset({"cyproheptadine"}), "tablet"),
    (frozenset({"donepezil"}), "tablet"),
    (frozenset({"doxazosin"}), "tablet"),
    (frozenset({"doxepin"}), "capsule"),
    (frozenset({"doxycycline"}), "capsule"),
    (frozenset({"doxycycline"}), "tablet"),
    (frozenset({"dutasteride"}), "capsule"),
    (frozenset({"escitalopram"}), "tablet"),
    (frozenset({"estradiol"}), "tablet"),
    (frozenset({"ezetimibe", "simvastatin"}), "tablet"),
    (frozenset({"finasteride"}), "tablet"),
    (frozenset({"fluticasone"}), "nasal spray"),
    (frozenset({"furosemide"}), "tablet"),
    (frozenset({"glipizide"}), "tablet"),
    (frozenset({"glyburide", "metformin"}), "tablet"),
    (frozenset({"glyburide"}), "tablet"),
    (frozenset({"hyoscyamine"}), "disintegrating tablet"),
    (frozenset({"hyoscyamine"}), "sublingual tablet"),
    (frozenset({"lamotrigine"}), "tablet"),
    (frozenset({"lisinopril"}), "tablet"),
    (frozenset({"losartan"}), "tablet"),
    (frozenset({"methimazole"}), "tablet"),
    (frozenset({"mometasone"}), "cream"),
    (frozenset({"naproxen"}), "tablet"),
    (frozenset({"nystatin", "triamcinolone"}), "ointment"),
    (frozenset({"nystatin"}), "cream"),
    (frozenset({"omeprazole"}), "delayed-release capsule"),
    (frozenset({"ondansetron"}), "disintegrating tablet"),
    (frozenset({"ondansetron"}), "tablet"),
    (frozenset({"oxybutynin"}), "extended-release tablet"),
    (frozenset({"phenytoin"}), "chewable tablet"),
    (frozenset({"piroxicam"}), "capsule"),
    (frozenset({"pramipexole"}), "tablet"),
    (frozenset({"quetiapine"}), "extended-release tablet"),
    (frozenset({"ramipril"}), "capsule"),
    (frozenset({"risperidone"}), "tablet"),
    (frozenset({"rizatriptan"}), "disintegrating tablet"),
    (frozenset({"ropinirole"}), "tablet"),
    (frozenset({"rosuvastatin"}), "tablet"),
    (frozenset({"sertraline"}), "tablet"),
    (frozenset({"sildenafil"}), "tablet"),
    (frozenset({"sotalol"}), "tablet"),
    (frozenset({"tamoxifen"}), "tablet"),
    (frozenset({"terazosin"}), "capsule"),
    (frozenset({"tizanidine"}), "capsule"),
    (frozenset({"venlafaxine"}), "tablet"),
})


def may_cover(ingredients: frozenset[str], form: str) -> bool:
    return (frozenset(i.lower() for i in ingredients), form) in ELIGIBLE

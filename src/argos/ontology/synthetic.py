"""Hand-authored synthetic fixtures for specialist development and eval.

Every fixture is anchored to a real NHTSA CRSS 2023 crash record (CASENUM in
the docstring), with the policy + party + document layers synthesized.

This is the anchor pair: same real crash, same synthesized policy, with ONE
document difference (the "heading home" quote in the police report). If the
Coverage specialist's output doesn't move between variants, the model is
anchoring on priors rather than reading evidence.

See docs/evals/coverage-anchor-pair-thresholds.md for the pre-written delta
thresholds that this pair must hit for the "reads evidence" claim.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from argos.ontology.types import (
    CoverageRequest,
    PolicyCoverage,
    Document,
    Policy,
    PolicyPeriod,
    SyntheticClaim,
)


CRSS_CASENUM = 202304845216
LOSS_DATE = date(2023, 3, 13)  # Monday in March 2023; CRSS gives weekday+month only


# Identifiers, kept stable across variants so AgentAction lineage matches.
POLICY_ID = "POL-NWL-2023-CA00-001"
POLICY_PERIOD_ID = "PP-NWL-2023-001"
POLICY_NUMBER = "NWL-CA-024471"
NAMED_INSURED_PARTY_ID = "PTY-NWL-INS"
CLAIMANT_PARTY_ID = "PTY-CLM-REYES"
COVERAGE_BI = "CP-NWL-2023-BI"
COVERAGE_PD = "CP-NWL-2023-PD"
COVERAGE_COLL = "CP-NWL-2023-COLL"
COVERAGE_COMP = "CP-NWL-2023-COMP"
REQUEST_ID = "EXP-2023-04471-REYES-BI"
CLAIM_ID = "CLM-2023-04471"


def _policy() -> Policy:
    return Policy(
        policy_id=POLICY_ID,
        client_program_id="CLIENT-NWL",
        policy_number=POLICY_NUMBER,
        named_insured_party_id=NAMED_INSURED_PARTY_ID,
        policy_form="CA00",
        jurisdiction_state="FL",
    )


def _policy_period() -> PolicyPeriod:
    return PolicyPeriod(
        policy_period_id=POLICY_PERIOD_ID,
        policy_id=POLICY_ID,
        effective_from=date(2023, 1, 1),
        effective_to=date(2023, 12, 31),
        status="in_force",
    )


def _coverages() -> list[PolicyCoverage]:
    return [
        PolicyCoverage(
            coverage_id=COVERAGE_BI,
            policy_period_id=POLICY_PERIOD_ID,
            coverage_type="auto_BI",
            limit_per_occurrence=1_000_000.0,
            limit_per_person=1_000_000.0,
            limit_aggregate=1_000_000.0,
            deductible=0.0,
        ),
        PolicyCoverage(
            coverage_id=COVERAGE_PD,
            policy_period_id=POLICY_PERIOD_ID,
            coverage_type="auto_PD",
            limit_per_occurrence=500_000.0,
            deductible=1_000.0,
        ),
        PolicyCoverage(
            coverage_id=COVERAGE_COLL,
            policy_period_id=POLICY_PERIOD_ID,
            coverage_type="auto_collision",
            limit_per_occurrence=150_000.0,
            deductible=2_500.0,
        ),
        PolicyCoverage(
            coverage_id=COVERAGE_COMP,
            policy_period_id=POLICY_PERIOD_ID,
            coverage_type="auto_comprehensive",
            limit_per_occurrence=150_000.0,
            deductible=1_000.0,
        ),
    ]


def _request() -> CoverageRequest:
    return CoverageRequest(
        request_id=REQUEST_ID,
        claim_id=CLAIM_ID,
        coverage_id=COVERAGE_BI,
        claimant_party_id=CLAIMANT_PARTY_ID,
        coverage_status="pending",
    )


# --- DOCUMENTS ---------------------------------------------------------------
#
# All four documents share the same skeleton across variants. The police report
# (DOC-002) has TWO versions: clean and with-flag. Everything else is identical.

DOC_DECLARATIONS = """\
NORTHWIND LOGISTICS, LLC
Commercial Automobile Policy — Declarations Page
Policy Number: NWL-CA-024471         Form: CA 00 01 (ISO Commercial Auto)
Policy Period: 01/01/2023 12:01 A.M. to 01/01/2024 12:01 A.M. (Standard Time)
Named Insured: Northwind Logistics, LLC, 4218 Causeway Blvd, Tampa, FL 33619
Producer: Gulf Coast Commercial Brokerage, Inc.

COVERED AUTOS SYMBOLS:
  Liability (Sym. 7) ............. Specifically Described Autos
  Physical Damage (Sym. 7) ....... Specifically Described Autos

LIABILITY COVERAGE:
  Bodily Injury / Property Damage Combined Single Limit ..... $1,000,000
  Each Accident                                              $1,000,000
  Deductible (Liability) ............................................. $0

PHYSICAL DAMAGE (per scheduled auto):
  Comprehensive ....... $1,000 deductible      Collision ....... $2,500 deductible

UNINSURED/UNDERINSURED MOTORIST:
  Bodily Injury — Florida Statutory ........... Rejected (signed UM rejection form on file)

SCHEDULE OF COVERED AUTOS (excerpt; full schedule at endorsement CA 99 03):
  Unit 14: 2019 Freightliner M2-106, VIN 1FVACWDT9KHKL4218, GVWR 24,500 lbs,
           Body: Box truck (24-ft), Garage: Tampa terminal, Class 2-D-T-1 (radius
           ≤ 200 mi, secondary class T — Truck), Use: pickup/delivery — general
           commodities. Liability + Comp + Collision.

ENDORSEMENTS:
  CA 99 03 — Auto Medical Payments Coverage ($5,000)
  CA 23 17 — Pollution Liability — Broadened Coverage for Covered Autos
  CA 04 49 — Loss Payable Clause (where applicable)
  CA 21 17 — Florida — Uninsured Motorists Coverage (REJECTED)

DRIVER ELIGIBILITY:
  All scheduled drivers must hold a valid CDL Class B for Unit 14. Annual MVR pull
  by Producer. Drivers must be 23 years of age or older with three years
  documented commercial driving experience.

Issued: 12/19/2022   Underwriter: K. Patel   Branch: Tampa
"""

DOC_RECORDED_STATEMENT = """\
RECORDED STATEMENT — Marcus Aliyah
Taken by: J. Whitaker, Senior Claim Specialist
Date: March 15, 2023, 10:14 A.M.
Re: Loss 03/13/2023, Northwind Logistics Policy NWL-CA-024471, Unit 14
Recording medium: Carrier dial-in line, 17 minutes 32 seconds (file #03-15-A-001)

  WHITAKER: OK Marcus, I'm recording. You understand we're recording, right?
  ALIYAH:   Yes ma'am, that's fine.
  WHITAKER: And you're, uh, you're providing this statement voluntarily?
  ALIYAH:   Yeah, yeah, that's correct.
  WHITAKER: Alright. Can you, uh, can you walk me through what happened on
            Monday afternoon — uh, that would be March 13?
  ALIYAH:   Sure. So Monday I, uh — I had a route, you know, the regular
            Brandon route. I think I had — let me think — I had eleven or
            twelve stops that day, mostly the strip center clients, and then
            the two big drops at the warehouse on Adamo. I finished the last
            drop, that was — that was probably around 4:15, 4:20, somewhere
            in there. The Adamo warehouse, the one off 50th Street.
  WHITAKER: OK. And then —
  ALIYAH:   And then I was heading back. I was supposed to log the truck back
            in at the Causeway terminal, that's the protocol, uh, before
            anything else.
  WHITAKER: Mm-hmm.
  ALIYAH:   Yeah, so I'm coming up Causeway, traffic's normal, it's, you
            know, it's late afternoon traffic, not horrible. And I'm coming
            up to the T at, uh, at Bermuda — Bermuda Avenue, that little
            T-intersection. And there's a Honda sedan in front of me, she's
            slowing down — I think she's turning, or maybe stopping, I
            couldn't really tell. I — uh, my foot was on the brake, but I
            don't think I got enough pressure, or, you know, maybe I
            misjudged the distance. The truck doesn't stop like a car, you
            know, the box truck loaded up.
  WHITAKER: Right.
  ALIYAH:   And I hit her. Not, not super hard, but, you know, the front of
            my truck hit the back of her car. I felt — I felt the impact and
            then the truck kind of, uh, it kind of skidded to the right and
            I clipped a sign or a pole or something on the shoulder. I'm not
            sure what.
  WHITAKER: OK. And the truck — was it loaded at the time?
  ALIYAH:   Empty. Or, uh, mostly empty. I had a couple of, uh, empty pallets
            in the back from one of the stops. That was it.
  WHITAKER: Got it. And the trip — what was the purpose of the trip you were
            on at the time of impact?
  ALIYAH:   I was returning to the terminal. That's, uh, that's the protocol.
            Log the truck in, do the post-trip inspection, drop the keys.
            Before I, you know, before I clock out.
  WHITAKER: And were you on your assigned route from dispatch?
  ALIYAH:   Yes ma'am. Causeway is the route back to the terminal. There's
            not really another way to get there from the Adamo warehouse,
            unless you wanted to go all the way around on the interstate,
            which, you know, nobody does.
  WHITAKER: OK. And you're — you've been driving for Northwind how long?
  ALIYAH:   Uh, this'll be my, this is my fourth year. I think — yeah, four
            years in May.
  WHITAKER: And the truck — Unit 14 — that's the truck you usually drive?
  ALIYAH:   Yes. Almost always. There's another driver who drives it when I'm
            off, but, you know, it's my, my regular unit.
  WHITAKER: Alright. Uh, one more thing — were you on the phone, or texting,
            or anything like that when the impact happened?
  ALIYAH:   No ma'am. Hands-free Bluetooth is the only thing we're allowed to
            do, and I wasn't even on a call. I was just driving.
  WHITAKER: OK Marcus, that's what I needed. I'll send you a transcript when
            it's done. Thank you for your time.
  ALIYAH:   No problem.

[End of recording. Transcript prepared by Cogent Reporting, Inc. 03/16/2023.]
"""

DOC_DISPATCH_LOG = """\
NORTHWIND LOGISTICS — Daily Dispatch Log
Date: 2023-03-13 (Monday)        Terminal: Tampa-Causeway        Dispatcher: R. Onuoha
Generated from Onfleet API export 2023-03-13 23:59:00 UTC.

Unit 14   Driver: M. Aliyah (FL CDL Class B, License #A2241-FL, exp. 2024-08-31)
Route: BR-Mon-A (Brandon corridor, Monday rotation)
Shift: 07:30 check-in → 17:00 scheduled check-out

  Stop  Time     Location                         Type       Status
  ----  ----     ---------------------------------- ---------- ----------
   1    08:14   3210 Tampa Rd (Brandon)            delivery   completed
   2    08:42   4180 Lakewood Ridge Blvd           delivery   completed
   3    09:08   5012 Causeway Square unit B        delivery   completed
   4    09:51   2200 Falkenburg Rd                 delivery   completed
   5    10:36   3414 N 50th St                     delivery   completed
   6    11:18   4471 E Adamo Dr (warehouse A)      delivery   completed
   7    12:04   [lunch — driver off-duty 30 min]   —          completed
   8    12:48   2218 Hillsborough Ave              delivery   completed
   9    13:32   6004 Falkenburg Rd                 delivery   completed
  10    14:10   4880 N 50th St                     pickup     completed
  11    14:58   3940 E Adamo Dr (warehouse B)      delivery   completed
  12    15:51   4471 E Adamo Dr (warehouse A)      delivery   completed   [final drop]

  16:42   INCIDENT REPORTED — Causeway Blvd / Bermuda Ave intersection.
          Driver radioed terminal at 16:44. PD dispatched. Tow scheduled 17:12.
          Truck inbound to terminal at time of incident; ETA to terminal was
          17:00 per route plan. Post-trip inspection / unit lock-in not yet
          performed (incident occurred prior to scheduled check-in).

  Authorization: Marcus Aliyah is the assigned driver of Unit 14 for the
  2023-03-13 BR-Mon-A route. No reassignment, no swap. Vehicle use during the
  return leg (Adamo → Causeway terminal) is on-duty per Northwind operations
  manual §4.3 (truck must be returned to terminal before driver clock-out).

  Signed: R. Onuoha (Dispatcher)         Filed: 2023-03-13 23:59
"""

POLICE_REPORT_HEADER = """\
HILLSBOROUGH COUNTY SHERIFF'S OFFICE — TRAFFIC CRASH REPORT
Report No.: HCSO-2023-CWY-04471          Reporting Deputy: K. Tovar, #4421
Date of Crash: 03/13/2023      Time: 16:42 hrs       Day: Mon
Location: Causeway Blvd at Bermuda Ave (T-intersection), Tampa, FL 33619
Weather: Clear      Light: Daylight     Road Surface: Dry, level, straight
Road Type: Two-way undivided, posted 45 MPH
Crash Type: Front-to-Rear, 2 vehicles
"""

POLICE_REPORT_BODY = """\
VEHICLES:
V-1: 2019 Freightliner M2-106 (24-ft box truck, no trailer), tag FL-TRK-Q4218.
     Owner: Northwind Logistics LLC. Insurer: per policy NWL-CA-024471.
     Driver: Aliyah, Marcus J., M/47, FL CDL Class B (License #A2241), DOB 12/04/1975.
     Travel speed: stated 45 MPH (PSL 45). Impact: 12 o'clock (front).
     Damage: disabling — front fascia, hood, radiator. Tow required.

V-2: 2022 Honda Civic 4dr sedan, tag FL-CIV-J0824.
     Owner / Driver: Reyes, Janet M., F/49, FL DL R624-184-49.
     Travel speed: estimated 35 MPH at impact. Impact: 6 o'clock (rear).
     Damage: disabling — rear bumper, trunk, frame deformation.

INJURIES:
V-2 driver Reyes complained of neck and lower-back pain on scene; transported
non-emergency by HCFR to Tampa General. Coded "Possible Injury (C)."
V-1 driver Aliyah no apparent injury, declined transport. Both belted.

NARRATIVE:
Eastbound on Causeway Blvd approaching the T-intersection with Bermuda Ave,
V-2 was decelerating in the eastbound through lane (driver later stated she
was preparing to turn right onto Bermuda Ave; right-turn signal was on per
witness W-1). V-1, traveling directly behind V-2 in the same lane, failed to
slow in time. V-1 front struck V-2 rear at approximately 12 MPH closing
speed. After initial contact, V-1 skidded right-front into a metal signpost
on the south shoulder, sustaining additional fixed-object damage.

V-1 driver stated: "My foot was on the brake but I don't think I got enough
pressure, or I misjudged the distance. The truck doesn't stop like a car
when you're loaded up." Driver was empty of cargo at the time.
{HOME_QUOTE_BLOCK}

WITNESSES:
W-1: Garza, Hector E. M/38. Eastbound directly behind V-1 in the next lane.
     Stated V-2 had right-turn signal active; V-1 closed without braking
     "until the last second."

CITATIONS / VIOLATIONS:
V-1 driver Aliyah cited under FSS 316.0895(1) — Following Too Closely.

CONTRIBUTING FACTORS:
V-1: Improper following distance (primary). No alcohol, no drugs. Not
     distracted per driver statement (hands-free only; no call active).
V-2: None coded.

REPORT FILED 03/13/2023 19:18 by Deputy K. Tovar #4421.
HCSO Records: HCSO-2023-CWY-04471.
"""

# The flag: a single sentence in the police narrative that introduces course-
# and-scope ambiguity. Variant A omits it; Variant B includes it.
HOME_QUOTE_INSERT = (
    "When asked about the purpose of the trip, V-1 driver stated, "
    '"I was on my way home for the day."'
)


def _police_report_text(*, with_home_quote: bool) -> str:
    insert = ("\n" + HOME_QUOTE_INSERT) if with_home_quote else ""
    body = POLICE_REPORT_BODY.replace("{HOME_QUOTE_BLOCK}", insert).rstrip()
    return POLICE_REPORT_HEADER + body + "\n"


def _documents(*, variant: Literal["clean", "with_flag"]) -> list[Document]:
    return [
        Document(
            document_id="DOC-001",
            claim_id=CLAIM_ID,
            document_type="declarations_page",
            received_date=date(2023, 3, 13),
            source="Producer file (Gulf Coast Commercial Brokerage)",
            body_text=DOC_DECLARATIONS,
        ),
        Document(
            document_id="DOC-002",
            claim_id=CLAIM_ID,
            document_type="police_report",
            received_date=date(2023, 3, 14),
            source="Hillsborough County Sheriff's Office",
            body_text=_police_report_text(with_home_quote=(variant == "with_flag")),
        ),
        Document(
            document_id="DOC-003",
            claim_id=CLAIM_ID,
            document_type="recorded_statement",
            received_date=date(2023, 3, 16),
            source="Carrier intake — Whitaker, J., recorded interview",
            body_text=DOC_RECORDED_STATEMENT,
        ),
        Document(
            document_id="DOC-004",
            claim_id=CLAIM_ID,
            document_type="dispatch_log",
            received_date=date(2023, 3, 14),
            source="Northwind Logistics — Onfleet API export",
            body_text=DOC_DISPATCH_LOG,
        ),
    ]


def _loss_facts(*, variant: Literal["clean", "with_flag"]) -> str:
    base = (
        "Monday 03/13/2023 at 4:42 P.M., Tampa FL. Northwind Logistics Unit 14 "
        "(2019 Freightliner M2-106 box truck, driver M. Aliyah) was eastbound on "
        "Causeway Blvd, returning to the Tampa-Causeway terminal after completing "
        "the BR-Mon-A delivery route (last drop logged 15:51 at the Adamo "
        "warehouse). At the T-intersection with Bermuda Ave, V-1 rear-ended a "
        "2022 Honda Civic (driver J. Reyes, 49F) that was decelerating to turn "
        "right onto Bermuda. Reyes reported neck and back pain at scene and was "
        "transported non-emergency to Tampa General. Aliyah was cited for FSS "
        "316.0895(1) Following Too Closely. Both drivers belted; no alcohol/drugs."
    )
    return base


def build_anchor_variant(variant: Literal["clean", "with_flag"]) -> SyntheticClaim:
    """Build one variant of the anchor pair.

    `clean` and `with_flag` differ in exactly one place: the police report
    (DOC-002). Everything else — policy, parties, dispatch log, recorded
    statement, loss_facts narrative — is byte-identical between the two.
    """
    return SyntheticClaim(
        policy=_policy(),
        policy_period=_policy_period(),
        coverages=_coverages(),
        request=_request(),
        documents=_documents(variant=variant),
        loss_date=LOSS_DATE,
        loss_facts=_loss_facts(variant=variant),
    )


def build_anchor_pair() -> tuple[SyntheticClaim, SyntheticClaim]:
    """Return (clean_variant, with_flag_variant) as a paired anchor fixture."""
    return build_anchor_variant("clean"), build_anchor_variant("with_flag")

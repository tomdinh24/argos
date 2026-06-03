/**
 * Action Type: applyCoverageDecision
 *
 * Mirrors `src/argos/services/orchestrator/coverage_actions.py::apply_coverage_decision`.
 * Flips a Claim's `coverage_posture` property to one of the four allowed
 * literal values, after the Coverage workflow's recommendation has been
 * committed by an adjuster.
 *
 * v1 vertical-slice scope: bare property mutation + enum validator.
 * Out of scope for v1: emitting a paired AgentAction + EvidenceCitation
 * row (the data-layer.md §6 audit pattern). That gets added when
 * EmitAgentAction is authored and chained as a side-effect.
 *
 * Foundry-side authoring:
 *   - Author the Action Type via Ontology Manager wizard (preferred for
 *     simple property mutations), OR
 *   - Paste this validator into a Code Repository function and reference
 *     it from the Action Type definition.
 *
 * Placeholder imports — these resolve to Foundry-generated types once
 * the `ClaimsV1` Object Type exists in the tenant's Code Repositories.
 */

// import { ClaimsV1 } from "@foundry/ontology";
// import { ActionContext } from "@foundry/actions-api";

type CoveragePosture =
    | "under_investigation"
    | "ROR_issued"
    | "denied"
    | "accepted";

const ALLOWED_COVERAGE_POSTURES: ReadonlySet<CoveragePosture> = new Set([
    "under_investigation",
    "ROR_issued",
    "denied",
    "accepted",
]);

interface ApplyCoverageDecisionInput {
    // Affected Claim instance (Foundry binds this from the Object Set the
    // action is invoked on).
    claim: /* ClaimsV1 */ { coverage_posture: string };
    // The new value to write. Must be one of the four allowed literals.
    newCoveragePosture: string;
}

/**
 * Validator: rejects writes where `newCoveragePosture` isn't in the
 * allowed literal set. Foundry runs this BEFORE the mutation; rejection
 * surfaces as a typed error in the UI / OSDK call site.
 */
export function validate(input: ApplyCoverageDecisionInput): void {
    if (!ALLOWED_COVERAGE_POSTURES.has(input.newCoveragePosture as CoveragePosture)) {
        throw new Error(
            `Invalid newCoveragePosture: "${input.newCoveragePosture}". ` +
            `Must be one of: ${Array.from(ALLOWED_COVERAGE_POSTURES).join(", ")}.`,
        );
    }
}

/**
 * Mutation: sets the Claim's coverage_posture to the validated input.
 * In the Foundry UI wizard this would be the "What does this action do?"
 * step — pick the target property, bind it to the input parameter.
 */
export function apply(input: ApplyCoverageDecisionInput): void {
    validate(input);
    input.claim.coverage_posture = input.newCoveragePosture;
}

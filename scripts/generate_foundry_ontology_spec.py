"""
Generate an AI FDE-ready ontology spec from foundry/ontology/object-types.yaml.

Output: foundry/ontology/ai-fde-spec.json — a worklist AI FDE chat can execute
to create Object Types, Link Types, and Action Types on a new global branch
and open a single proposal.

Per the verified pattern (memory: feedback-foundry-ontology-via-aifde):
  For each Object Type:
    1. create_object_type_permissions_datasets -> capture dataset RID
    2. substitute <DATASET_RID_FOR_*> + <ONTOLOGY_BRANCH_RID> placeholders
    3. create_object_type with substituted payload
  For each Link Type:
    1. create_link_type with source/target objectTypeId + cardinality
  For each Action Type:
    1. create_action_type with parameters + target object
  After all: create_or_update_global_branch_proposal once

Run:
    python3 scripts/generate_foundry_ontology_spec.py
"""

import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
YAML_SRC = REPO / "foundry" / "ontology" / "object-types.yaml"
JSON_OUT = REPO / "foundry" / "ontology" / "ai-fde-spec.json"

# Verified constants for the Argos Foundry stack (see memory).
ONTOLOGY_RID = "ri.ontology.main.ontology.88f01e1f-0987-467d-88a4-c500edf5692f"
NAMESPACE_RID = "ri.compass.main.folder.0aa063b2-0b86-4059-9058-9665ec11b6f3"
SAVE_LOCATION_FOLDER_RID = "ri.compass.main.folder.e00e25bd-d33c-4398-ba71-1e8630b0114f"

BRANCH_NAME = "argos-ontology-poc-2"
BRANCH_DESCRIPTION = (
    "Link Types + Action Types scale-out. Adds foreign-key edges between the "
    "28 existing Object Types and the 6 orchestrator action types."
)
PROPOSAL_TITLE = "Argos ontology — Link Types + Action Types"
PROPOSAL_DESCRIPTION = (
    "Second branch of the Argos ontology scale-out. Adds: "
    "(a) auto-derived Link Types from foreign-key property names, "
    "(b) six Action Types mirroring the orchestrator-level handlers "
    "(coverage, reserve, liability, recovery, closure, reopen). "
    "Object Types from argos-ontology-poc-1 are assumed already merged to main."
)

# YAML primitive -> Foundry property type.
TYPE_MAP = {
    "string": "string",
    "boolean": "boolean",
    "date": "date",
    "integer": "integer",
    "number": "double",
    "timestamp": "timestamp",
}

# Foreign-key alias map: property names that don't match a primary_key by exact
# name still reference a known Object Type. Keep this list explicit; auditing
# beats clever inference.
FK_ALIASES = {
    # All *_party_id variants -> Party
    "named_insured_party_id": "Party",
    "carrier_party_id": "Party",
    "fnol_reporter_party_id": "Party",
    "claimant_party_id": "Party",
    "assessed_by_party_id": "Party",
    "adverse_party_id": "Party",
    "adverse_carrier_party_id": "Party",
    "assigned_to_party_id": "Party",
    "requested_by_party_id": "Party",
    "decided_by_party_id": "Party",
    "lienholder_party_id": "Party",
    "reporting_responsible_party_id": "Party",
    "approved_by_party_id": "Party",
    # Workflow refs
    "source_event_id": "Event",
    "triggered_by_event_id": "Event",
    "damaged_risk_unit_id": "RiskUnit",
    "applies_to_exposure_id": "ClaimExposure",
    "source_document_id": "Document",
    "authority_decision_id": "AuthorityDecision",
    # Self-references
    "reverses_transaction_id": "FinancialTransaction",
    "superseded_by_assessment_id": "LiabilityAssessment",
    "parent_request_id": "AuthorityRequest",
    # Cross-domain
    "sourced_rule_id": "SpecialistConfig",
    "ledger_entry_id": "FinancialPosting",
    "agent_action_id": "AgentAction",
}

# Polymorphic / not-modeled FKs to silently skip (no single target type).
# model_id would point to a Model object type that doesn't exist in the
# ontology; add it later if/when we introduce a Model registry.
FK_SKIP = {"entity_id", "model_id"}


def pascal_to_kebab(name: str) -> str:
    """ClientProgram -> client-program."""
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def snake_to_camel(name: str) -> str:
    """client_program_id -> clientProgramId."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def snake_to_kebab(name: str) -> str:
    """client_program_id -> client-program-id."""
    return name.replace("_", "-")


def snake_to_title(name: str) -> str:
    """client_program_id -> Client Program Id."""
    return " ".join(p.capitalize() for p in name.split("_"))


def pluralize(name: str) -> str:
    """ClientProgram -> Client Programs. Naive +s rule, hand-edit if wrong."""
    if name.endswith("y") and not name.endswith(("ay", "ey", "iy", "oy", "uy")):
        return name[:-1] + "ies"
    if name.endswith(("s", "x", "z", "ch", "sh")):
        return name + "es"
    return name + "s"


def build_property(prop: dict, dataset_rid_placeholder: str, is_primary: bool) -> dict:
    name = prop["name"]
    yaml_type = prop["type"]
    if yaml_type not in TYPE_MAP:
        raise ValueError(f"Unknown YAML type {yaml_type!r} on property {name!r}")
    foundry_type = TYPE_MAP[yaml_type]
    required = bool(prop.get("required", False))

    base = {
        "displayName": snake_to_title(name),
        "apiName": snake_to_camel(name),
        "description": prop.get("description") or f"{snake_to_title(name)} (from object-types.yaml).",
        "type": foundry_type,
        "isArray": False,
        "nullability": "REQUIRED" if required else "OPTIONAL",
        "propertyTypeId": snake_to_kebab(name),
        "visibility": "NORMAL" if is_primary else "PROMINENT",
        "displayFormatting": None,
        "defaultCipherChannelRid": None,
        "sharedPropertyRid": None,
    }

    if is_primary:
        base["sourceResourceColumnMap"] = [
            {
                "sourceResourceRid": dataset_rid_placeholder,
                "sourceResourceColumn": "primary-key",
            }
        ]
    else:
        base["sourceResourceRid"] = dataset_rid_placeholder
        base["sourceResourceColumn"] = None
        base["status"] = "experimental"

    return base


def build_object_type_entry(ot: dict) -> dict:
    api_name = ot["api_name"]
    object_type_id = pascal_to_kebab(api_name)
    backing_dataset_name = f"{object_type_id}-backing-dataset"
    dataset_rid_placeholder = f"<DATASET_RID_FOR_{api_name}>"

    pk_name = ot["primary_key"]
    title_property = ot.get("title_property", pk_name)

    pk_prop_yaml = next((p for p in ot["properties"] if p["name"] == pk_name), None)
    if pk_prop_yaml is None:
        raise ValueError(f"{api_name}: primary_key {pk_name!r} not found in properties")

    primary_key_property = build_property(pk_prop_yaml, dataset_rid_placeholder, is_primary=True)
    non_pk_properties = [
        build_property(p, dataset_rid_placeholder, is_primary=False)
        for p in ot["properties"]
        if p["name"] != pk_name
    ]

    create_payload = {
        "objectTypeId": object_type_id,
        "ontologyBranchRid": "<ONTOLOGY_BRANCH_RID>",
        "apiName": api_name,
        "displayName": ot.get("display_name") or api_name,
        "pluralDisplayName": pluralize(ot.get("display_name") or api_name),
        "description": ot.get("description") or f"{api_name} object type.",
        "status": "experimental",
        "editsEnabled": True,
        "visibility": "NORMAL",
        "icon": None,
        "aliases": None,
        "interfaceImplementations": None,
        "titlePropertyTypeId": snake_to_kebab(title_property),
        "saveLocationFolderRid": SAVE_LOCATION_FOLDER_RID,
        "primaryKeyPropertyType": primary_key_property,
        "propertyTypes": non_pk_properties,
    }

    return {
        "apiName": api_name,
        "objectTypeId": object_type_id,
        "backingDatasetName": backing_dataset_name,
        "datasetRidPlaceholder": dataset_rid_placeholder,
        "createObjectTypePayload": create_payload,
    }


def build_pk_registry(object_types: list[dict]) -> dict[str, str]:
    """Map primary-key property name -> Object Type api_name."""
    return {ot["primary_key"]: ot["api_name"] for ot in object_types}


def derive_link_types(object_types: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Walk every non-PK *_id property; resolve to a target Object Type by:
      1. exact primary_key match
      2. FK_ALIASES override
      3. otherwise: emit a warning, skip
    Each derived link is many-to-one (source's FK property -> target's PK).
    """
    pk_registry = build_pk_registry(object_types)
    links: list[dict] = []
    unresolved: list[str] = []

    for ot in object_types:
        source_api = ot["api_name"]
        pk_name = ot["primary_key"]
        for prop in ot["properties"]:
            name = prop["name"]
            if name == pk_name or not name.endswith("_id"):
                continue
            if name in FK_SKIP:
                continue
            target = pk_registry.get(name) or FK_ALIASES.get(name)
            if target is None:
                unresolved.append(f"{source_api}.{name}")
                continue
            link = {
                "apiName": f"{source_api}{target}",  # e.g. PolicyClientProgram
                "displayName": f"{source_api} -> {target} via {name}",
                "description": (
                    f"Foreign-key edge: {source_api}.{name} references "
                    f"{target}.{pk_registry.get(target, '<pk>')}."
                ),
                "sourceObjectTypeApiName": source_api,
                "sourcePropertyName": name,
                "sourcePropertyApiName": snake_to_camel(name),
                "targetObjectTypeApiName": target,
                "targetPropertyName": next(
                    (k for k, v in pk_registry.items() if v == target), None
                ),
                "cardinality": "MANY_TO_ONE",
                "required": bool(prop.get("required", False)),
            }
            links.append(link)

    return links, unresolved


def build_action_type_entry(at: dict) -> dict:
    api_name = at["api_name"]
    parameters = []
    for p in at["parameters"]:
        param = {
            "apiName": snake_to_camel(p["name"]),
            "parameterName": p["name"],
            "displayName": snake_to_title(p["name"]),
            "type": TYPE_MAP[p["type"]],
            "required": bool(p.get("required", False)),
            "description": p.get("description") or snake_to_title(p["name"]),
        }
        if "enum" in p:
            param["enum"] = p["enum"]
        parameters.append(param)

    return {
        "apiName": api_name,
        "displayName": at.get("display_name") or api_name,
        "description": at.get("description") or f"{api_name} action.",
        "targetObjectTypeApiName": at["target_object_type"],
        "parameters": parameters,
    }


def main() -> None:
    raw = yaml.safe_load(YAML_SRC.read_text())
    yaml_object_types = raw["object_types"]
    yaml_action_types = raw.get("action_types", [])

    object_types = [build_object_type_entry(ot) for ot in yaml_object_types]
    link_types, unresolved = derive_link_types(yaml_object_types)
    action_types = [build_action_type_entry(at) for at in yaml_action_types]

    spec = {
        "_instructions_for_ai_fde": [
            "Branch + proposal:",
            "  1a. Call create_global_branch with: branchName, branchDescription, namespaceRid, ontologyRid. Capture globalBranchRid AND ontologyBranchRid.",
            "  After all link types + action types are created (steps 2+3 below), call create_or_update_global_branch_proposal at the end.",
            "Object Types:",
            "  This run includes only NEW Object Types if the objectTypes list is non-empty. If it is empty (link/action-only run), skip to step 2.",
            "  For each entry: (a) create_object_type_permissions_datasets with {folderRid: saveLocationFolderRid, datasetNames: [<entry>.backingDatasetName]}; (b) substitute <entry>.datasetRidPlaceholder and <ONTOLOGY_BRANCH_RID> in createObjectTypePayload; (c) create_object_type with the substituted payload.",
            "Link Types (step 2):",
            "  For each entry in linkTypes: call create_link_type (or the equivalent ontology-edits tool) on the ontologyBranchRid, with sourceObjectTypeApiName/targetObjectTypeApiName/sourcePropertyApiName/cardinality from the entry. The source Object Type already has the FK property (named in sourcePropertyName); the link expresses the relationship. Use whatever arg shape your MCP catalog requires; adapt the spec fields to match.",
            "  IMPORTANT: the 28 Object Types from argos-ontology-poc-1 must already be merged into main ontology before this branch can resolve them. If a link target Object Type is not found, stop and report.",
            "Action Types (step 3):",
            "  For each entry in actionTypes: call create_action_type (or equivalent) on the ontologyBranchRid. Each action targets a single Object Type (targetObjectTypeApiName) and accepts the parameters listed. For enum parameters, configure the action's parameter constraint to the enum list.",
            "Reporting:",
            "  At the end, report: globalBranchRid, ontologyBranchRid, proposal RID, and per-section RID tables: {apiName -> linkTypeRid} and {apiName -> actionTypeRid}.",
            "If ANY call fails, stop and report the failure with the full tool response.",
        ],
        "branchName": BRANCH_NAME,
        "branchDescription": BRANCH_DESCRIPTION,
        "namespaceRid": NAMESPACE_RID,
        "ontologyRid": ONTOLOGY_RID,
        "saveLocationFolderRid": SAVE_LOCATION_FOLDER_RID,
        "proposalTitle": PROPOSAL_TITLE,
        "proposalDescription": PROPOSAL_DESCRIPTION,
        # Empty for this branch — the 28 Object Types live on argos-ontology-poc-1.
        # Future regenerations that include new Object Types should populate this.
        "objectTypes": [],
        "linkTypes": link_types,
        "actionTypes": action_types,
        "_unresolvedForeignKeys": unresolved,
        "_objectTypesReferenceOnly": [ot["apiName"] for ot in object_types],
    }

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(spec, indent=2) + "\n")
    print(
        f"Wrote spec to {JSON_OUT.relative_to(REPO)}: "
        f"{len(object_types)} object types (reference), "
        f"{len(link_types)} link types, "
        f"{len(action_types)} action types, "
        f"{len(unresolved)} unresolved FKs"
    )
    if unresolved:
        print("Unresolved (skipped) foreign keys:")
        for u in unresolved:
            print(f"  - {u}")


if __name__ == "__main__":
    main()

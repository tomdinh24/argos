"""
Generate an AI FDE-ready ontology spec from foundry/ontology/object-types.yaml.

Output: foundry/ontology/ai-fde-spec.json — a worklist AI FDE chat can execute
to create all 28 Object Types on a new global branch and open a single proposal.

Per the verified pattern (memory: feedback-foundry-ontology-via-aifde):
  For each Object Type:
    1. create_object_type_permissions_datasets -> capture dataset RID
    2. substitute <DATASET_RID> placeholders in createObjectTypePayload
    3. create_object_type with substituted payload
  After all 28: create_or_update_global_branch_proposal once

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

BRANCH_NAME = "argos-ontology-poc-1"
BRANCH_DESCRIPTION = "Initial scale-out of the Argos ontology: 28 Object Types."
PROPOSAL_TITLE = "Argos ontology — initial 28 Object Types"
PROPOSAL_DESCRIPTION = (
    "Scale-out of the Argos ontology from object-types.yaml. "
    "28 Object Types covering portfolio, claim, party, financial, evidence, "
    "workflow, regulatory, and system-trace layers. "
    "Link Types and Action Types follow in separate branches."
)

# YAML primitive -> Foundry property type
TYPE_MAP = {
    "string": "string",
    "boolean": "boolean",
    "date": "date",
    "integer": "integer",
    "number": "double",
    "timestamp": "timestamp",
}


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


def main() -> None:
    raw = yaml.safe_load(YAML_SRC.read_text())
    yaml_types = raw["object_types"]

    object_types = [build_object_type_entry(ot) for ot in yaml_types]

    spec = {
        "_instructions_for_ai_fde": [
            "1. Call create_global_branch with: branchName, branchDescription, namespaceRid, ontologyRid below. Capture globalBranchRid AND ontologyBranchRid.",
            "2. For EACH entry in objectTypes (28 total): "
            "  a. Call create_object_type_permissions_datasets with {folderRid: saveLocationFolderRid, datasetNames: [<entry>.backingDatasetName]}. Capture the returned dataset RID."
            "  b. In <entry>.createObjectTypePayload, replace ALL occurrences of <entry>.datasetRidPlaceholder with the dataset RID from step 2a, and replace <ONTOLOGY_BRANCH_RID> with the ontologyBranchRid from step 1."
            "  c. Call create_object_type with the substituted payload.",
            "3. After all 28 Object Types are created, call create_or_update_global_branch_proposal with globalBranchRid + proposalTitle + proposalDescription.",
            "4. Report: globalBranchRid, ontologyBranchRid, proposal RID, and the dataset RID + objectType RID for each of the 28 types.",
            "If ANY create_object_type call fails, stop and report the failure with the full tool response.",
        ],
        "branchName": BRANCH_NAME,
        "branchDescription": BRANCH_DESCRIPTION,
        "namespaceRid": NAMESPACE_RID,
        "ontologyRid": ONTOLOGY_RID,
        "saveLocationFolderRid": SAVE_LOCATION_FOLDER_RID,
        "proposalTitle": PROPOSAL_TITLE,
        "proposalDescription": PROPOSAL_DESCRIPTION,
        "objectTypes": object_types,
    }

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Wrote {len(object_types)} Object Types to {JSON_OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()

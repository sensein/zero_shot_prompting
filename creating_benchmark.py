import json
from pathlib import Path
from typing import List, Dict, Set, Tuple, Union
from collections import defaultdict
LABEL_FILTER = {
    "ACTION", "ADJECTIVE", "ADVERB", "ARTICLE", "AUXILIARY", "AUTHOR_AND_DATE", 
    "CITATION", "CONJUNCTION", "COUNT",
    "DIMENSION", "DURATION", "EFFECT", "FIGURE", "FIGURE_PART", "FIGURE_REFERENCE",
    "IDENTIFIER", "MODIFIER", "NOUN", "NUMBER", "OTHER", "PARAMETER", "PHRASE",
    "PREPOSITION", "PRONOUN", "PRODUCT_ID", "PROPERTY", "QUANTITY", "QUANTIFIER",
    "REFERENCE", "TEMPERATURE", "TIME", "TIME_DURATION", "TIME_POINT", "TRANSITION_WORD"
    "VALUE", "VERB", "UNIT", "UNITS", "PUBLICATION"
}

def union_ner_entities(json_files: List[Union[str, Path]], output_file_name=None) -> Dict[str, Set[str]]:
    """
    Reads multiple NER-output JSON files and returns a mapping from each entity
    (normalized to lowercase) to the set of labels it was assigned across all files.

    Args:
        json_files: List of paths to JSON files. Each file must contain an "entities"
                    list under data["results"][...]["entities"].

    Returns:
        A dict where keys are entity strings (lowercase) and values are sets of labels.
    """
    entity_labels = defaultdict(lambda: defaultdict(set))

    for fp in json_files:
        path = Path(fp)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        results = data.get("results", {})
        for res in results.values():
            for ent in res.get("entities", []):
                # normalize entity text to lowercase
                name = ent["entity"].strip()
                standardized_name = name.lower()
                label = ent["label"]
                if label not in LABEL_FILTER:
                    entity_labels[standardized_name][name].add(label)
    output = defaultdict(list)
    for standardized_name, names in entity_labels.items():
        if len(names) > 1:
            # If there are multiple names for the same entity, we need to merge them
            # into a single entry in the output.
            # This is a simple way to handle it, but you might want to customize this
            # logic based on your specific requirements.
            merged_labels = set()
            for name_variants in names.values():
                merged_labels.update(name_variants)
            output[standardized_name] = list(merged_labels)
        else:
            for name, labels in names.items():
                output[name] = list(labels)
    # sort the output by entity name
    output = dict(sorted(output.items(), key=lambda x: x[0]))
    if output_file_name:
        with open(output_file_name, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
            print(f"Wrote merged entity map to {Path(output_file_name).resolve()}")
    return entity_labels

def union_ner_entities_with_positions(
    json_files: List[Union[str, Path]]
) -> Dict[str, Dict[Tuple[int, int], Set[str]]]:
    """
    Reads multiple NER-output JSON files and returns a nested mapping:
      entity_text_lowercase -> {
          (start_index, end_index) -> set of labels seen for that span
      }

    Args:
        json_files: List of file paths to NER-output JSONs. Each file must
                    contain data["results"][...]["entities"].

    Returns:
        A dict mapping each normalized entity to a dict that maps
        (start_index, end_index) tuples to the set of labels assigned there.
    """
    entity_map: Dict[str, Dict[Tuple[int, int], Set[str]]] = {}

    for fp in json_files:
        path = Path(fp)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        data = json.loads(path.read_text())
        results = data.get("results", {})
        for section in results.values():
            for ent in section.get("entities", []):
                print(ent)
                name = ent["entity"].strip().lower()
                
                span = (ent.get("start_index"), ent.get("end_index"))
                label = ent.get("label")

                # Check if label is None before adding to the entity_map
                if label is not None:
                    # ensure nested dict exists
                    if name not in entity_map:
                        entity_map[name] = {}
                    if span not in entity_map[name]:
                        entity_map[name][span] = set()

                entity_map[name][span].add(label)

    return entity_map

def save_entity_map_to_json(
    entity_map: Dict[str, Dict[Tuple[int, int], Set[str]]],
    output_path: Union[str, Path]
) -> None:
    """
    Serializes the nested entity_map to JSON, converting tuple-keys to objects.
    Output format:
    {
      "entity_text": [
         {"start": int, "end": int, "labels": [str, ...]},
         ...
      ],
      ...
    }
    """
    serializable: Dict[str, List[Dict]] = {}

    for entity, spans in entity_map.items():
        span_list = []
        for (start, end), labels in spans.items():
            span_list.append({
                "start": start,
                "end": end,
                "labels": sorted(labels)
            })
        serializable[entity] = span_list

    out_path = Path(output_path)
    out_path.write_text(json.dumps(serializable, indent=2))
    print(f"Wrote merged entity map to {out_path.resolve()}")

def merge_ner_sections(
    json_files: List[Union[str, Path]],
    output_path: Union[str, Path]
) -> None:
    """
    Reads multiple NER-output JSONs and writes a merged JSON preserving
    the same 'results' section structure, but with each entity's labels
    combined into a list.

    Output format:
    {
      "results": {
        "1": {
          "raw_text": "...",               # from first file
          "in_place_annotation": "...",    # from first file
          "entities": [
            {
              "entity": "...",
              "start_index": ...,
              "end_index": ...,
              "labels": ["LABEL1", "LABEL2", ...]
            },
            ...
          ]
        },
        ...
      }
    }
    """
    # Will hold per-section span→set(labels)
    merged: Dict[str, Dict[Tuple[str,int,int], Set[str]]] = {}
    # To store raw_text & in_place_annotation from the first file
    section_info: Dict[str, Dict[str, str]] = {}

    for fp in json_files:
        data = json.loads(Path(fp).read_text())
        results = data.get("results", {})

        for sec_id, sec_data in results.items():
            # capture raw_text & annotation once
            if sec_id not in section_info:
                section_info[sec_id] = {
                    "raw_text": sec_data.get("raw_text", ""),
                    "in_place_annotation": sec_data.get("in_place_annotation", "")
                }

            # prepare merged bucket
            merged.setdefault(sec_id, {})

            for ent in sec_data.get("entities", []):
                key = (ent["entity"].strip().lower(),
                       ent.get("start_index"),
                       ent.get("end_index"))
                merged[sec_id].setdefault(key, set()).add(ent.get("label"))

    # Build the final structure
    output = {"results": {}}
    for sec_id, spans in merged.items():
        sec_out = {
            "raw_text": section_info[sec_id]["raw_text"],
            "in_place_annotation": section_info[sec_id]["in_place_annotation"],
            "entities": []
        }
        for (ent_text, start, end), labels in spans.items():
            sec_out["entities"].append({
                "entity": ent_text,
                "start_index": start,
                "end_index": end,
                "labels": sorted(labels)
            })
        output["results"][sec_id] = sec_out

    # Write to disk
    out_path = Path(output_path)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Merged JSON written to {out_path.resolve()}")

if __name__ == "__main__":
    # Example usage:
    files = [
        "output/prompt_5/phillips_claude-3.7-sonnet_2025-05-08_23-47-46.json",
        "output/prompt_5/phillips_deepseek-chat-v3-0324_2025-05-09_00-09-01.json",
        "output/prompt_5/phillips_gemini-2.0-flash-001_2025-05-08_23-42-35.json",
        "output/prompt_5/phillips_gpt-4o-mini_2025-05-08_23-32-22.json",
        
    ]
    # merged_entites = union_ner_entities(files)
    # for entity, labels in merged_entites.items():
    #     print(f"{entity!r}: {labels}")

    # merged_with_position = union_ner_entities_with_positions(files)
    # save_entity_map_to_json(merged_with_position, "phillips_allmodels_merged_entities_positions.json")
    
    #merge_ner_sections(files, "merged_sections.json")

    union_ner_entities(files,"output/prompt_5/benchmark_generation/phillips_merged_filtered_entities_allmodels.json")
    # # Example print‑out
    # for entity, spans in merged_with_position.items():
    #     for (start, end), labels in spans.items():
            
    #         print(f"Entity '{entity}' at [{start}:{end}] → labels: {labels}")
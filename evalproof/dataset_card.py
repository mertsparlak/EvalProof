"""Bounded local card observations; never retain card values or body text."""

import hashlib
import stat

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode
from yaml.tokens import (AliasToken, AnchorToken, TagToken, BlockMappingStartToken,
                         BlockSequenceStartToken, FlowMappingStartToken,
                         FlowSequenceStartToken, BlockEndToken, FlowMappingEndToken,
                         FlowSequenceEndToken)

from evalproof.config import ConfigError, resolve_provenance_source


def _license_status(header):
    depth = 0
    starts = (BlockMappingStartToken, BlockSequenceStartToken, FlowMappingStartToken, FlowSequenceStartToken)
    ends = (BlockEndToken, FlowMappingEndToken, FlowSequenceEndToken)
    for count, token in enumerate(yaml.scan(header, Loader=yaml.SafeLoader), 1):
        if count > 4096 or isinstance(token, (AliasToken, AnchorToken, TagToken)):
            return "unavailable"
        if isinstance(token, starts):
            depth += 1
            if depth > 16:
                return "unavailable"
        elif isinstance(token, ends):
            depth -= 1
    root = yaml.compose(header, Loader=yaml.SafeLoader)
    if not isinstance(root, MappingNode):
        return "unavailable"
    fields = {}
    for key, value in root.value:
        if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str" or key.value in fields:
            return "unavailable"
        fields[key.value] = value
    value = fields.get("license")
    if value is None or isinstance(value, ScalarNode) and value.tag == "tag:yaml.org,2002:null":
        return "missing"
    if isinstance(value, ScalarNode) and value.tag == "tag:yaml.org,2002:str":
        return "present" if value.value.strip() else "missing"
    if isinstance(value, SequenceNode):
        if not value.value:
            return "missing"
        if all(isinstance(item, ScalarNode) and item.tag == "tag:yaml.org,2002:str" and item.value.strip()
               for item in value.value):
            return "present"
    return "unavailable"


def read_dataset_card(scan_root, ref, max_bytes):
    facts = {"card_ref_hash": "sha256:" + hashlib.sha256(ref.encode("utf-8")).hexdigest(),
             "license_status": "unavailable", "card_header_fingerprint": None}
    limit = min(max_bytes, 1024 * 1024)
    try:
        path = resolve_provenance_source(scan_root, ref)
        if not stat.S_ISREG(path.stat().st_mode):
            return facts
        with path.open("rb") as stream:
            first = stream.readline(limit + 1)
            if len(first) > limit or first.decode("utf-8-sig").rstrip("\r\n") != "---":
                return facts
            physical = bytearray(first)
            content = []
            while len(physical) < limit:
                line = stream.readline(limit - len(physical) + 1)
                if not line or len(physical) + len(line) > limit:
                    return facts
                physical.extend(line)
                if line.rstrip(b"\r\n") == b"---":
                    facts["card_header_fingerprint"] = "sha256:" + hashlib.sha256(physical).hexdigest()
                    facts["license_status"] = _license_status(b"".join(content).decode("utf-8"))
                    return facts
                content.append(line)
    except (OSError, RuntimeError, ConfigError, UnicodeError, yaml.YAMLError):
        pass  # Exceptions may quote private metadata; expose observation state only.
    return facts

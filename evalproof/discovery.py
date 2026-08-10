"""File discovery under scan root using include/exclude glob patterns."""

import os
from pathlib import Path
import re
from typing import List, Set

from evalproof.config import Config


def glob_to_regex(pattern: str) -> re.Pattern:
    """Convert a repository-relative POSIX glob pattern to a regex Pattern.

    Handles:
    - '**/' matching zero or more directory levels
    - '/**' matching any trailing path
    - '*' matching characters within a single path component
    - '?' matching a single character within a path component
    """
    p = pattern.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    if p.endswith("/"):
        p = p + "**"

    # Tokenize special glob patterns: **, *, ?
    i = 0
    n = len(p)
    res = []
    
    # If pattern has no slash, it can match anywhere in path or at top-level
    has_slash = "/" in p

    while i < n:
        c = p[i]
        if c == "*":
            if i + 1 < n and p[i + 1] == "*":
                # Double asterisk **
                i += 2
                if i < n and p[i] == "/":
                    # ** / -> zero or more subdirectories followed by /
                    res.append("(?:|.*/)")
                    i += 1
                else:
                    # ** at end or before non-slash -> match anything
                    res.append(".*")
            else:
                # Single asterisk * -> match within single path segment (non-slash)
                res.append("[^/]*")
                i += 1
        elif c == "?":
            res.append("[^/]")
            i += 1
        elif c in r".^$+{}()[]\|":
            res.append("\\" + c)
            i += 1
        else:
            res.append(c)
            i += 1

    regex_str = "".join(res)
    if not has_slash:
        # Match either top level or any directory component
        regex_str = f"^(?:.*/)?{regex_str}$"
    else:
        regex_str = f"^{regex_str}$"

    return re.compile(regex_str)


def is_pattern_matched(path_str: str, patterns: List[str]) -> bool:
    """Check if POSIX path string matches any of the given glob patterns."""
    for pat in patterns:
        regex = glob_to_regex(pat)
        if regex.match(path_str):
            return True
    return False


def discover_files(scan_root: str, config: Config) -> List[str]:
    """Discover candidate files under scan_root matching config include/exclude rules.

    Returns deterministic sorted list of repository-relative POSIX file paths.
    """
    scan_path = Path(scan_root).resolve()
    if not scan_path.exists() or not scan_path.is_dir():
        raise FileNotFoundError(f"Scan root directory not found or unreadable: {scan_root}")

    candidate_files: Set[str] = set()

    for root, dirs, files in os.walk(scan_path):
        rel_root = Path(root).relative_to(scan_path)

        for filename in files:
            full_path = Path(root) / filename
            rel_file_path = full_path.relative_to(scan_path)
            posix_path = str(rel_file_path).replace("\\", "/")

            # Exclude patterns take precedence over include patterns
            if is_pattern_matched(posix_path, config.exclude):
                continue

            if is_pattern_matched(posix_path, config.include):
                candidate_files.add(posix_path)

    # Sort deterministically
    sorted_files = sorted(list(candidate_files))
    return sorted_files

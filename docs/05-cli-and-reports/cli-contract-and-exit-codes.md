# CLI Contract And Exit Codes

## Question

How must the MVP CLI behave, including exit codes?

## MVP Command

The MVP command is:

```text
evalproof scan [path]
```

If `path` is omitted, the scanner uses the current working directory.

The rule discovery command is:

```text
evalproof rules
```

`evalproof rules` lists all built-in rules in deterministic rule ID order. It does not read configuration, discover files, build a project index, execute a scan, or write a report. It has no JSON output mode.

## Rule Selection

The `scan` command accepts an optional comma-separated rule allowlist:

```text
evalproof scan [path] --rules <rule-id>,<rule-id>
```

When `--rules` is absent, all registered rules run except rules disabled by configuration. When it is present, only the selected rule IDs are candidates, and `rules.disabled` still takes precedence.

Rule IDs are case-sensitive. Whitespace around comma-separated IDs is ignored and duplicate IDs are removed. Empty IDs, unknown IDs, and selections that resolve to no enabled rules are invalid CLI usage and return exit code `2` before discovery starts. Rule execution and report order remain deterministic regardless of the order supplied on the command line.

## Supported Options

```text
--config <path>       Use an explicit configuration file.
--json               Write JSON report to stdout.
--output <path>      Write JSON report to a file. Requires --json.
--fail-on <severity> Override configured failing severity.
--no-color           Disable terminal colors.
--rules <ids>        Run only selected comma-separated rule IDs.
```

Tag, wildcard, prefix, and regular-expression rule selection are not supported.

## Default Behavior

Without `--json`, the CLI prints a human-readable terminal summary.

The scanner writes a JSON report to `evalproof_report.json` in the scanned folder when no explicit output path is provided.

With `--json`, the CLI prints the JSON report defined in [JSON Report](json-report.md) and still writes the default report file unless `--output` is provided.

`--output` is valid only with `--json`. When `--output` is used with `--json`, JSON is written to the output path and terminal output remains concise. Using `--output` without `--json` is invalid CLI usage.

## Exit Codes

Exit codes:

- `0`: scan completed and no finding met or exceeded the failing severity, or rule listing/help completed successfully.
- `1`: scan completed and at least one finding met or exceeded the failing severity.
- `2`: invalid CLI usage.
- `3`: invalid configuration.
- `4`: scan root is unreadable or not found.
- `5`: output path cannot be written.
- `6`: unexpected internal error.

The default failing severity value is defined in [Configuration And Schema](../02-architecture/configuration-and-schema.md). This document defines how the CLI applies that value to process exit behavior.

Invalid `--fail-on` values are invalid CLI usage and must return exit code `2`.

`evalproof --help`, `evalproof scan --help`, and `evalproof rules --help` print help
without scanning or writing reports. Missing commands remain invalid usage (`2`).

## Terminal Summary

The terminal summary must include:

- scan root
- number of artifacts scanned
- active rule mode and active rule count
- number of findings by severity
- highest-severity findings with rule id, path, and message
- path to JSON report if written

The terminal summary must not be the machine-readable contract.

## CI Behavior

CI systems should use exit codes and JSON output.

The CLI must not require interactive input.

The CLI must not require network access.

## Design Decisions

- `scan` remains the scanning command; `rules` is the read-only rule discovery command.
- JSON output is the machine-readable contract.
- Every completed scan writes a JSON report file.
- Exit code `1` means trust findings crossed the configured threshold, not that the scanner crashed.
- Invalid configuration and internal errors use distinct exit codes.

## Open Questions

None.

## Dependencies

- [MVP Scope](../00-product/mvp-scope.md)
- [Configuration And Schema](../02-architecture/configuration-and-schema.md)
- [JSON Report](json-report.md)

## Future Considerations

Future commands may add config initialization, SARIF output, baselines, or suppressions after the MVP is stable.

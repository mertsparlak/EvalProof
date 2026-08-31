"""Lazy, local-only Parquet decoding into the existing JSON-like record model."""


class OptionalDependencyMissing(Exception):
    pass


class UnsupportedParquetSchema(Exception):
    pass


class ParquetReadError(Exception):
    pass


def _load_arrow():
    try:
        import pyarrow as pa
        if str(pa.__version__).split(".")[0] != "25":
            raise OptionalDependencyMissing
        import pyarrow.parquet as pq
        return pa, pq
    except (ImportError, OSError) as error:
        raise OptionalDependencyMissing from error


def _supported_fields(pa, fields):
    names = [field.name for field in fields]
    return len(names) == len(set(names)) and all(_supported_type(pa, field.type) for field in fields)


def _supported_type(pa, dtype):
    types = pa.types
    if any(check(dtype) for check in (
        types.is_null, types.is_boolean, types.is_integer, types.is_floating,
        types.is_string, types.is_large_string, types.is_string_view,
    )):
        return True
    if types.is_dictionary(dtype) or types.is_list(dtype) or types.is_large_list(dtype) or types.is_fixed_size_list(dtype):
        return _supported_type(pa, dtype.value_type)
    if types.is_struct(dtype):
        return _supported_fields(pa, list(dtype))
    return False


def iter_parquet_rows(path):
    """Yield rows in file order; never infer a remote filesystem from a path."""
    pa, pq = _load_arrow()
    try:
        with open(path, "rb") as source:
            with pq.ParquetFile(source, arrow_extensions_enabled=False, page_checksum_verification=True) as reader:
                if not _supported_fields(pa, list(reader.schema_arrow)):
                    raise UnsupportedParquetSchema
                for batch in reader.iter_batches(batch_size=65536, use_threads=False):
                    yield from batch.to_pylist()
    except UnsupportedParquetSchema:
        raise
    except Exception as error:
        # Decoder exceptions can include user data, metadata, or absolute paths.
        raise ParquetReadError from error

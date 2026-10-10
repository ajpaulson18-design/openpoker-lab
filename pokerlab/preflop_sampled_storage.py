"""Pre-allocation logical storage bound for exact sampled-world CDFs."""

from math import isfinite


MAX_SAMPLER_ENTRIES = 250_000
MAX_SAMPLER_CDF_BITS = 128_000_000


def estimate_sampler_storage(worlds):
    """Bound exact-integer CDF rows and retained integer bit payload.

    This census does not construct cumulative CDF integers. It rejects on row
    count before reading any weights, then finds a conservative maximum CDF
    integer width from exact float ratios. The reported bit count is logical
    payload only, not Python allocated bytes or RSS. Temporary ratios,
    float-weight arrays, list/tuple slots, integer headers/limbs, and other
    object overhead are excluded; the row cap bounds those allocations.
    """
    if (isinstance(worlds, (str, bytes)) or not hasattr(worlds, "__len__") or
            not hasattr(worlds, "__getitem__")):
        raise TypeError("worlds must be a sized sequence")
    row_count = len(worlds)
    if row_count < 1:
        raise ValueError("at least one world is required for sampled storage")
    if row_count > MAX_SAMPLER_ENTRIES:
        raise ValueError("sampled sampler exceeds 250,000 CDF entries")

    ratios = []
    denominator_exponent = 0
    positive_count = 0
    for index in range(row_count):
        world = worlds[index]
        if not isinstance(world, (tuple, list)) or len(world) < 3:
            raise ValueError("each world must contain a weight at index 2")
        weight = world[2]
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError("world weights must be finite nonnegative floats or integers")
        if isinstance(weight, float):
            if not isfinite(weight) or weight < 0:
                raise ValueError("world weights must be finite and nonnegative")
            numerator, denominator = weight.as_integer_ratio()
            exponent = denominator.bit_length() - 1
        else:
            if weight < 0:
                raise ValueError("world weights must be finite and nonnegative")
            numerator, exponent = weight, 0
            try:
                finite_weight = isfinite(float(weight))
            except (TypeError, ValueError, OverflowError):
                finite_weight = False
            if not finite_weight:
                raise ValueError("world weights must be finite and nonnegative")
        denominator_exponent = max(denominator_exponent, exponent)
        positive_count += numerator > 0
        ratios.append((numerator, exponent))

    if positive_count == 0:
        raise ValueError("world weights must have positive total mass")

    max_shifted_width = 0
    for numerator, exponent in ratios:
        if numerator:
            max_shifted_width = max(
                max_shifted_width,
                numerator.bit_length() + denominator_exponent - exponent,
            )
    cdf_width = max_shifted_width + (positive_count - 1).bit_length()
    logical_cdf_bits = row_count * cdf_width
    if logical_cdf_bits > MAX_SAMPLER_CDF_BITS:
        raise ValueError("sampled sampler exceeds 128,000,000 logical CDF bits")

    return {
        "storage_version": "preflop-sampled-storage-v1",
        "sampler_entries": row_count,
        "positive_weight_entries": positive_count,
        "common_denominator_exponent": denominator_exponent,
        "cdf_integer_width_upper_bound": cdf_width,
        "logical_cdf_bits_upper_bound": logical_cdf_bits,
        "sampler_entry_limit": MAX_SAMPLER_ENTRIES,
        "logical_cdf_bit_limit": MAX_SAMPLER_CDF_BITS,
        "scope": (
            "Logical retained exact-CDF integer bit payload and row count only; "
            "not Python allocated bytes or RSS. Temporary ratios/float arrays, "
            "container slots, integer object overhead and query scratch are excluded."
        ),
    }

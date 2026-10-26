"""Fail closed when binary64 chance normalization would lose precision/support."""
import math
import sys


def normal_positive_mass(value):
    """Return the unchanged mass, rejecting zero/subnormal/nonfinite results.

    Positive range weights can multiply or divide into subnormal values before
    normalization, materially changing even a large posterior probability.
    This guard deliberately rejects that numeric envelope; it does not rescale
    inputs, change reduction order, or promise exact floating-point arithmetic.
    """
    if not math.isfinite(value) or value < sys.float_info.min:
        raise ValueError(
            "Joint chance mass is outside the normal binary64 range; "
            "rescale positive range weights to avoid probability underflow."
        )
    return value

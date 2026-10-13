"""Pure exact realization-flow subtraction for research-only CFR+ tails.

Callers must independently validate the complete serialized river tree and
legal action rows before passing their strategy rows here. The two inputs must
be normalized average policies from the same CFR+ training trajectory on the
same perfect-recall game. This helper reconstructs only a player's own action
reach; opponent actions and public chance probabilities are deliberately
excluded.
"""
from copy import deepcopy
from fractions import Fraction
import math
from numbers import Real


ROW_SUM_TOLERANCE = Fraction(1, 10**12)
REALIZATION_TOLERANCE = Fraction(1, 10**12)
RECONSTRUCTION_TOLERANCE = Fraction(1, 10**11)
MAX_ITERATIONS = 10_000

_ROW_FIELDS = frozenset(("player", "hand", "history", "actions"))
_ACTION_FIELDS = frozenset(("name", "amount", "raise_to", "history_key", "probability"))


def _fraction_probability(value, *, row_key, action_index):
    if isinstance(value, bool):
        raise ValueError(f"Boolean probability at {row_key!r} action {action_index}.")
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, int):
        result = Fraction(value)
    elif isinstance(value, Real):
        try:
            as_float = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Probability must be finite and numeric.") from exc
        if not math.isfinite(as_float):
            raise ValueError(f"Nonfinite probability at {row_key!r} action {action_index}.")
        result = Fraction.from_float(as_float)
    else:
        raise ValueError("Probability must be a float, integer, or Fraction.")
    if result < 0 or result > 1:
        raise ValueError(f"Probability outside [0, 1] at {row_key!r} action {action_index}.")
    return result


def _row_key(row):
    if not isinstance(row, dict):
        raise ValueError("Every strategy row must be a mapping.")
    if not _ROW_FIELDS.issubset(row):
        raise ValueError("Strategy row is missing a required field.")
    player, hand, history = row["player"], row["hand"], row["history"]
    if player not in ("oop", "ip"):
        raise ValueError("Strategy row player must be 'oop' or 'ip'.")
    if not isinstance(hand, str) or not hand:
        raise ValueError("Strategy row hand must be a nonempty string.")
    if not isinstance(history, (tuple, list)) or any(not isinstance(token, str) for token in history):
        raise ValueError("Strategy row history must be a sequence of string tokens.")
    return player, hand, tuple(history)


def _validate_action_metadata(action, key):
    if not isinstance(action, dict) or not _ACTION_FIELDS.issubset(action):
        raise ValueError(f"Malformed action metadata at {key!r}.")
    if not isinstance(action["name"], str) or not action["name"]:
        raise ValueError(f"Action name must be nonempty at {key!r}.")
    if not isinstance(action["history_key"], str) or not action["history_key"]:
        raise ValueError(f"Action history key must be nonempty at {key!r}.")
    for field in ("amount", "raise_to"):
        value = action[field]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"Action {field} must be a finite nonnegative number at {key!r}.")
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Action {field} must be a finite nonnegative number at {key!r}.") from exc
        if not math.isfinite(numeric) or numeric < 0:
            raise ValueError(f"Action {field} must be a finite nonnegative number at {key!r}.")


def _snapshot(rows, label):
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError(f"{label} snapshot must contain at least one strategy row.")
    keyed = {}
    order = []
    normalized = {}
    max_adjustment = Fraction(0)
    for row in rows:
        key = _row_key(row)
        if key in keyed:
            raise ValueError(f"Duplicate information-set row {key!r} in {label} snapshot.")
        actions = row["actions"]
        if not isinstance(actions, (list, tuple)) or not actions:
            raise ValueError(f"Strategy row {key!r} must have at least one legal action.")
        action_keys = []
        raw_probabilities = []
        for index, action in enumerate(actions):
            _validate_action_metadata(action, key)
            token = action["history_key"]
            if token in action_keys:
                raise ValueError(f"Duplicate action history key at {key!r}.")
            action_keys.append(token)
            raw_probabilities.append(_fraction_probability(
                action["probability"], row_key=key, action_index=index))
        probability_sum = sum(raw_probabilities, Fraction(0))
        if probability_sum <= 0 or abs(probability_sum - 1) > ROW_SUM_TOLERANCE:
            raise ValueError(f"Probability row at {key!r} does not sum to one within tolerance.")
        probabilities = tuple(probability / probability_sum for probability in raw_probabilities)
        max_adjustment = max(max_adjustment, *(abs(a - b) for a, b in
                                                zip(raw_probabilities, probabilities)))
        keyed[key] = row
        order.append(key)
        normalized[key] = probabilities
    return keyed, order, normalized, max_adjustment


def _metadata_without_probabilities(row):
    result = {}
    for field, value in row.items():
        if field == "actions":
            result[field] = [
                {key: item for key, item in action.items() if key != "probability"}
                for action in value
            ]
        else:
            result[field] = value
    return result


def _validate_matching_snapshots(prefix_rows, full_rows):
    prefix, prefix_order, prefix_probabilities, prefix_adjustment = _snapshot(prefix_rows, "prefix")
    full, full_order, full_probabilities, full_adjustment = _snapshot(full_rows, "full")
    if prefix_order != full_order:
        raise ValueError("Prefix/full strategy rows must have identical keys and order.")
    for key in full_order:
        if _metadata_without_probabilities(prefix[key]) != _metadata_without_probabilities(full[key]):
            raise ValueError(f"Prefix/full row or action metadata differs at {key!r}.")
    return (prefix, full, full_order, prefix_probabilities, full_probabilities,
            prefix_adjustment, full_adjustment)


def _own_reaches(rows, order, probabilities):
    """Return each row's own-sequence reach from its validated action history."""
    reaches = {}
    positions = {key: index for index, key in enumerate(order)}
    for key in sorted(order, key=lambda item: (len(item[2]), positions[item])):
        player, hand, history = key
        reach = Fraction(1)
        for index, token in enumerate(history):
            ancestor = (player, hand, history[:index])
            if ancestor not in rows:
                continue
            ancestor_actions = rows[ancestor]["actions"]
            matches = [action_index for action_index, action in enumerate(ancestor_actions)
                       if action["history_key"] == token]
            if len(matches) != 1:
                raise ValueError(
                    f"Own ancestor {ancestor!r} has no unique action history_key {token!r}.")
            reach *= probabilities[ancestor][matches[0]]
        reaches[key] = reach
    return reaches


def _flow(reach, probability_sum, discard_weight, total_weight, tail_weight):
    return (total_weight * reach[1] * probability_sum[1] -
            discard_weight * reach[0] * probability_sum[0]) / tail_weight


def reconstruct_tail(prefix_rows, full_rows, discard, total):
    """Construct an exact realization-equivalent CFR+ tail policy.

    ``prefix_rows`` and ``full_rows`` must be complete normalized snapshots
    from iterations ``discard`` and ``total`` of the same CFR+ trajectory and
    the same perfect-recall river game. Before calling, independently replay
    the complete serialized tree to establish legality, board/range identity,
    and row completeness. This helper validates row/action identity but is not
    a game-tree or poker legality validator.

    Returns ``(rows, ledger)``. The rows preserve full-snapshot row/action
    order and metadata, with exact ``Fraction`` action probabilities. Only a
    player's own ancestral action probabilities enter sequence reach; chance
    and opponent reach must not be included.
    """
    if type(discard) is not int or type(total) is not int:
        raise ValueError("Checkpoint iterations must be integers, not booleans.")
    if not 1 <= discard < total <= MAX_ITERATIONS:
        raise ValueError(f"Checkpoints must satisfy 1 <= discard < total <= {MAX_ITERATIONS}.")
    (prefix, full, order, prefix_probabilities, full_probabilities,
     prefix_adjustment, full_adjustment) = _validate_matching_snapshots(
         prefix_rows, full_rows)

    prefix_reach = _own_reaches(prefix, order, prefix_probabilities)
    full_reach = _own_reaches(full, order, full_probabilities)
    discard_weight = Fraction(discard * (discard + 1), 2)
    total_weight = Fraction(total * (total + 1), 2)
    tail_weight = total_weight - discard_weight

    raw_parent_flows = {}
    raw_child_flows = {}
    for key in order:
        reaches = (prefix_reach[key], full_reach[key])
        raw_parent = _flow(reaches, (Fraction(1), Fraction(1)),
                           discard_weight, total_weight, tail_weight)
        raw_parent_flows[key] = raw_parent
        child_flows = []
        for prefix_probability, full_probability in zip(
                prefix_probabilities[key], full_probabilities[key]):
            child_flows.append(_flow(
                reaches, (prefix_probability, full_probability),
                discard_weight, total_weight, tail_weight))
        raw_child_flows[key] = tuple(child_flows)

    output = []
    changed_rows = []
    fallback_rows = []
    negative_child_count = 0
    projected_negative_child_count = 0
    fallback_negative_child_count = 0
    max_negative = Fraction(0)
    max_projected_mass_moved = Fraction(0)

    for key in order:
        parent = raw_parent_flows[key]
        children = raw_child_flows[key]
        if parent < -REALIZATION_TOLERANCE or parent > 1 + REALIZATION_TOLERANCE:
            raise ValueError(f"Tail realization parent flow outside tolerance at {key!r}.")
        if any(child < -REALIZATION_TOLERANCE or child > 1 + REALIZATION_TOLERANCE
               for child in children):
            raise ValueError(f"Tail realization child flow outside tolerance at {key!r}.")
        if sum(children, Fraction(0)) != parent:
            raise ValueError(f"Tail child flows do not exactly conserve parent flow at {key!r}.")
        negative = tuple(child for child in children if child < 0)
        negative_child_count += len(negative)
        if negative:
            max_negative = max(max_negative, *(abs(child) for child in negative))

        fallback = parent <= 0
        if fallback:
            if any(abs(child) > REALIZATION_TOLERANCE for child in children):
                raise ValueError(f"Zero-tail parent has material child flow at {key!r}.")
            probabilities = full_probabilities[key]
            fallback_negative_child_count += len(negative)
            local_fallback_flows = tuple(parent * probability for probability in probabilities)
            moved = sum((abs(adjusted - raw) for adjusted, raw in
                         zip(local_fallback_flows, children)), Fraction(0))
            max_projected_mass_moved = max(max_projected_mass_moved, moved)
            change = {
                "row": key, "raw_parent_flow": parent,
                "raw_child_flows": children,
                "full_snapshot_fallback_probabilities": probabilities,
                # This local estimate can be slightly negative when the raw
                # parent is a tolerated negative. Actual output flows are
                # recorded below after reconstructing the entire profile.
                "local_fallback_child_flow_estimate": local_fallback_flows,
                "projected_mass_moved": moved,
                "reason": "zero-tail-full-snapshot-fallback",
            }
            fallback_rows.append(change)
            changed_rows.append(change)
        else:
            positive_total = sum((child for child in children if child > 0), Fraction(0))
            if negative:
                projected_negative_child_count += len(negative)
                if positive_total <= 0:
                    raise ValueError(f"Negative tail children have no positive support at {key!r}.")
                adjusted_children = tuple(
                    Fraction(0) if child < 0 else parent * child / positive_total
                    for child in children)
                moved = sum((abs(adjusted - raw) for adjusted, raw in
                             zip(adjusted_children, children)), Fraction(0))
                max_projected_mass_moved = max(max_projected_mass_moved, moved)
                changed_rows.append({
                    "row": key, "reason": "tiny-negative-child-projection",
                    "raw_parent_flow": parent, "raw_child_flows": children,
                    "adjusted_child_flows": adjusted_children,
                    "projected_mass_moved": moved,
                })
            else:
                adjusted_children = children
            probabilities = tuple(child / parent for child in adjusted_children)

        if any(probability < 0 or probability > 1 for probability in probabilities):
            raise ValueError(f"Constructed tail policy is invalid at {key!r}.")
        row = deepcopy(full[key])
        for action, probability in zip(row["actions"], probabilities):
            action["probability"] = probability
        output.append(row)

    output_by_key = {_row_key(row): row for row in output}
    output_probabilities = {
        _row_key(row): tuple(action["probability"] for action in row["actions"])
        for row in output
    }
    output_reach = _own_reaches(output_by_key, order, output_probabilities)
    max_discrepancy = Fraction(0)
    max_output_flow_l1_discrepancy = Fraction(0)
    changed_by_key = {record["row"]: record for record in changed_rows}
    for key in order:
        parent_discrepancy = abs(output_reach[key] - raw_parent_flows[key])
        max_discrepancy = max(max_discrepancy, parent_discrepancy)
        actual_child_flows = tuple(output_reach[key] * probability
                                   for probability in output_probabilities[key])
        child_discrepancies = tuple(abs(actual - raw) for actual, raw in
                                    zip(actual_child_flows, raw_child_flows[key]))
        for discrepancy in child_discrepancies:
            max_discrepancy = max(max_discrepancy, discrepancy)
        row_l1 = parent_discrepancy + sum(child_discrepancies, Fraction(0))
        max_output_flow_l1_discrepancy = max(max_output_flow_l1_discrepancy, row_l1)
        if key in changed_by_key:
            record = changed_by_key[key]
            record["actual_output_parent_flow"] = output_reach[key]
            record["actual_output_child_flows"] = actual_child_flows
            record["parent_flow_discrepancy"] = parent_discrepancy
            record["child_flow_discrepancies"] = child_discrepancies
            record["actual_output_flow_l1_discrepancy"] = row_l1
    if max_discrepancy > RECONSTRUCTION_TOLERANCE:
        raise ValueError("Constructed policy does not reconstruct tail flows within tolerance.")

    ledger = {
        "discard": discard,
        "total": total,
        "prefix_max_normalization_adjustment": prefix_adjustment,
        "full_max_normalization_adjustment": full_adjustment,
        "raw_negative_child_count": negative_child_count,
        "projected_negative_child_count": projected_negative_child_count,
        "fallback_negative_child_count": fallback_negative_child_count,
        "maximum_negative_child_magnitude": max_negative,
        "maximum_projected_mass_moved": max_projected_mass_moved,
        "changed_rows": changed_rows,
        "fallback_rows": fallback_rows,
        "maximum_reconstruction_discrepancy": max_discrepancy,
        "maximum_output_flow_l1_discrepancy": max_output_flow_l1_discrepancy,
    }
    return output, ledger

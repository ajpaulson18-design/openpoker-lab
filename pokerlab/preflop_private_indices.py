"""Bounded compaction of globally inactive private-hand indices.

This helper only renumbers hand indices. It preserves the world row order,
weights, signs, future-card fields, public histories, and info-row order. It is
used only when the caller selects the public-vector resource model. Its census
uses bounded active-index sets before copying rows; the caps count logical
rows and fields, not Python allocation overhead or RSS.
"""

from collections.abc import Mapping


MAX_ACTIVE_HANDS_PER_PLAYER = 1326
MAX_COMPACT_WORLD_ROWS = 3_000_000
MAX_COMPACT_WORLD_FIELDS = 25_000_000
MAX_COMPACT_INFO_ROWS = 500_000
MAX_COMPACT_INFO_ACTION_SLOTS = 1_000_000


class CompactedPrivateIndices:
    """Compact world/info structures and an inverse map for policy keys."""

    __slots__ = ("worlds", "infos", "original_to_compact", "_compact_to_original",
                 "metadata", "_original_info_order", "_compact_info_order", "__weakref__")

    def __init__(self, worlds, infos, original_to_compact, compact_to_original,
                 metadata, original_info_order, compact_info_order):
        self.worlds = tuple(worlds)
        self.infos = infos
        self.original_to_compact = tuple(original_to_compact)
        self._compact_to_original = tuple(compact_to_original)
        self.metadata = metadata
        self._original_info_order = tuple(original_info_order)
        self._compact_info_order = tuple(compact_info_order)

    def restore_policy(self, compact_policy):
        """Restore original hand indices and source info insertion order.

        The full info-key set is required so an incomplete or foreign policy
        cannot silently lose rows while returning to the public solver API.
        """
        if not isinstance(compact_policy, Mapping):
            raise TypeError("compact_policy must be a mapping")
        if (len(compact_policy) != len(self._compact_info_order) or
                any(key not in compact_policy for key in self._compact_info_order)):
            raise ValueError("compact_policy keys must match compact infos exactly")
        restored = {}
        for original_key, compact_key in zip(self._original_info_order,
                                             self._compact_info_order):
            restored[original_key] = compact_policy[compact_key]
        return restored


def _positive_limit(name, value):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _copy_world_row(world, mapping):
    copied = list(world)
    copied[0] = mapping[0][world[0]]
    copied[1] = mapping[1][world[1]]
    return tuple(copied)


def compact_private_indices(worlds, infos, *,
                            max_active_hands=MAX_ACTIVE_HANDS_PER_PLAYER,
                            max_world_rows=MAX_COMPACT_WORLD_ROWS,
                            max_world_fields=MAX_COMPACT_WORLD_FIELDS,
                            max_info_rows=MAX_COMPACT_INFO_ROWS,
                            max_info_action_slots=MAX_COMPACT_INFO_ACTION_SLOTS):
    """Return compact world/info copies after a bounded census.

    Original and compact indices are ordered ascending. All input worlds are
    retained in their original order; only fields zero and one change.
    """
    for name, value in (("max_active_hands", max_active_hands),
                        ("max_world_rows", max_world_rows),
                        ("max_world_fields", max_world_fields),
                        ("max_info_rows", max_info_rows),
                        ("max_info_action_slots", max_info_action_slots)):
        _positive_limit(name, value)
    if not isinstance(worlds, (tuple, list)) or not worlds:
        raise ValueError("worlds must be a nonempty tuple or list")
    if not isinstance(infos, Mapping):
        raise TypeError("infos must be a mapping")
    row_count = len(worlds)
    if row_count > max_world_rows:
        raise ValueError("private-index compaction world-row cap exceeded")

    active = (set(), set())
    world_fields = 0
    for world in worlds:
        if not isinstance(world, (tuple, list)) or len(world) < 4:
            raise ValueError("each world needs two hands, weight, and sign")
        world_fields += len(world)
        if world_fields > max_world_fields:
            raise ValueError("private-index compaction world-field cap exceeded")
        for player in (0, 1):
            index = world[player]
            if type(index) is not int or not 0 <= index < 1326:
                raise ValueError("world hand indices must be integers in [0, 1326)")
            if index not in active[player]:
                if len(active[player]) >= max_active_hands:
                    raise ValueError("private-index compaction active-hand cap exceeded")
                active[player].add(index)

    info_count = len(infos)
    if info_count > max_info_rows:
        raise ValueError("private-index compaction info-row cap exceeded")
    action_slots = 0
    for key, action_count in infos.items():
        if (not isinstance(key, tuple) or len(key) != 3 or
                type(key[0]) is not int or key[0] not in (0, 1) or
                type(key[1]) is not int or not 0 <= key[1] < 1326 or
                not isinstance(key[2], tuple) or type(action_count) is not int or
                action_count < 1):
            raise ValueError("infos must map valid (player, hand, history) keys to action counts")
        if key[1] not in active[key[0]]:
            raise ValueError("infos contain a hand absent from all physical worlds")
        action_slots += action_count
        if action_slots > max_info_action_slots:
            raise ValueError("private-index compaction info-action cap exceeded")

    ordered_original = tuple(tuple(sorted(indices)) for indices in active)
    original_to_compact = tuple({original: compact for compact, original in enumerate(indices)}
                                for indices in ordered_original)
    compact_to_original = ordered_original

    # No copied world or info row is allocated before every resource and
    # active-index check above has succeeded.
    compact_worlds = [_copy_world_row(world, original_to_compact) for world in worlds]
    original_info_order = []
    compact_info_order = []
    compact_infos = {}
    for original_key, action_count in infos.items():
        player, hand_index, history = original_key
        compact_key = (player, original_to_compact[player][hand_index], history)
        original_info_order.append(original_key)
        compact_info_order.append(compact_key)
        compact_infos[compact_key] = action_count

    metadata = {
        "original_hand_dimensions": [max(indices, default=-1) + 1
                                     for indices in ordered_original],
        "compact_hand_dimensions": [len(indices) for indices in ordered_original],
        "active_hand_counts": [len(indices) for indices in ordered_original],
        "original_active_indices": [list(indices) for indices in ordered_original],
        "world_rows": row_count,
        "world_fields_copied": world_fields,
        "info_rows": info_count,
        "info_action_slots": action_slots,
        "caps": {
            "active_hands_per_player": max_active_hands,
            "world_rows": max_world_rows,
            "world_fields": max_world_fields,
            "info_rows": max_info_rows,
            "info_action_slots": max_info_action_slots,
        },
        "scope": "Input rows are copied to preserve caller data; limits count logical rows/fields, not Python object overhead or RSS.",
    }
    return CompactedPrivateIndices(compact_worlds, compact_infos,
                                   original_to_compact, compact_to_original,
                                   metadata, original_info_order,
                                   compact_info_order)

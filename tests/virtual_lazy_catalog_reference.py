"""Scalar lazy-bitmap ledger and independent feasible-state maximization."""
WORK_CAP, ENTRIES_CAP, PAYLOAD_CAP = 75000000, 2000000, 1 << 30


def require(value, message):
    if not value:
        raise ValueError(message)


def forecast(blocks, rows, menus, holdings, lookups, lazy=True):
    require(all(type(x) is int and x > 0 for x in (blocks, rows, menus, holdings, lookups)) and
            max(blocks, rows, menus) <= ENTRIES_CAP and holdings <= 1326 and type(lazy) is bool,
            'bounded catalog ledger geometry')
    require(not lazy or rows >= blocks, 'lazy catalog row/block reservation contract')
    words = (holdings + 63) // 64
    bitmap_blocks = min(blocks, rows - blocks) if lazy else blocks
    metadata = 1024 + 32 * blocks + 320 * menus + words * bitmap_blocks
    access = 512 + 256 * 20 + 32 * (blocks + 1).bit_length() + 8 * words + (32 if lazy else 0)
    setup = 1024 + 8 * blocks + 8 * menus + (256 if lazy else 0)
    work = setup + lookups * access
    return {'metadata_words': metadata, 'metadata_payload_bits': 64 * metadata, 'work': work,
            'per_access_work': access, 'setup_work': setup, 'bitmap_words_per_dense_block': words,
            'passes_component_caps': metadata <= ENTRIES_CAP and 64 * metadata <= PAYLOAD_CAP and work <= WORK_CAP}


def feasible_peak(blocks, rows, bitmap_words):
    """Enumerate occupied b,d states; no candidate forecast formula is used."""
    require(type(blocks) is int and 1 <= blocks <= 16 and type(rows) is int and blocks <= rows <= 40 and
            type(bitmap_words) is int and 1 <= bitmap_words <= 21, 'bounded proof census')
    maximum = 0
    for occupied in range(1, blocks + 1):
        for promoted in range(occupied + 1):
            if occupied + promoted <= rows:
                maximum = max(maximum, 32 * occupied + bitmap_words * promoted)
    return maximum


GUARDS = ('lazy-row-cap-before-bitmap', 'lazy-foreign-row', 'lazy-default-row', 'lazy-changed-menu',
          'lazy-metadata-one-short', 'lazy-work-one-short', 'lazy-invalid-mode', 'lazy-rows-below-blocks')


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 65536 and raw.endswith(b'\n'), 'lazy component wire boundary')
    normalized = raw.replace(b'\r\n', b'\n')
    require(b'\r' not in normalized and (b'\r\n' not in raw or raw.count(b'\r\n') == raw.count(b'\n')),
            'lazy complete newline convention')
    marker = b'VIRTUAL_LAZY_CATALOG_V1\n'
    require(normalized.count(marker) == 1, 'lazy wire version')
    legacy, tail = normalized.split(marker)
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_strategy_catalog_reference import parse_catalog_wire, _decode_full_key
    fixture = Fixture(); old = parse_catalog_wire(legacy, fixture)
    lines = tail.decode('ascii').splitlines()
    require(len(lines) == 17 and lines[-1] == 'LAZY_END', 'lazy exact record inventory')
    def exact(index, prefix, values):
        parts = lines[index].split()
        require(parts[:len(prefix)] == list(prefix) and tuple(map(int, parts[len(prefix):])) == values,
                'lazy independent record: ' + ' '.join(prefix))
    exact(0, ('SNAP', 'first'), (1, 1, 0, 1376))
    for index, label, holding in ((1, 'lazy-first', 1325), (2, 'lazy-promoted', 0)):
        parts = lines[index].split()
        require(parts[:2] == ['ROW', label] and len(parts) >= 7, 'lazy original holding row grammar')
        ordinal, actor, original, source, count = map(int, parts[2:7])
        key = _decode_full_key(fixture, ordinal, actor, original)
        require(original == holding and actor == 0 and key['source_menu_ref'] == source and
                key['actions'] == parts[7:] and count == len(parts[7:]), 'lazy independent full-history/menu identity')
    parts = lines[3].split()
    require(parts[:2] == ['IDS', '1326'] and tuple(map(int, parts[2:])) == (1325, *range(1325)),
            'lazy all1326 original holding identities')
    exact(4, ('SNAP', 'all'), (1, 1326, 21, 1397))
    lazy = forecast(32, 32, 1, 1326, 64); eager = forecast(32, 32, 1, 1326, 64, False)
    exact(5, ('SPARSE',), (32, 32, 0, 672, lazy['metadata_words'], eager['metadata_words']))
    coupled = forecast(2, 2, 2, 1326, 8)
    exact(6, ('COUPLED',), (1, 2, 21, coupled['metadata_words'], 1397))
    require(lines[7:15] == ['GUARD ' + label + ' PASS' for label in GUARDS], 'lazy exact typed guard inventory')
    wide = forecast(1, 1326, 1, 1326, 4000)
    exact(15, ('FORECAST', 'wide'), (1, 1326, 1, 1326, 4000, wide['work'],
                                      wide['metadata_words'], wide['metadata_payload_bits']))
    return {'status': 'lazy-catalog-identity-reservation-controls-exact', 'legacy': old,
            'generic_original_holding_ids': 1326, 'new_typed_guards': len(GUARDS),
            'sparse_public_blocks': 32, 'lazy_sparse_bitmap_words': 0, 'eager_sparse_bitmap_words': 672,
            'scope': 'Catalog identity/metadata controls only. Generic holding IDs are not physical support; no whole-game, runtime, memory/RSS, longer learning or quality admission.'}

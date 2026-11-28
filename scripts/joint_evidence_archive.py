"""Bounded stdlib-only admission of an exactly pinned pooled evidence packet."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import stat
import zipfile

CAP = 8 << 20
EXPANDED = 80 << 20


def need(value, message):
    if not value: raise ValueError(message)


def digest(raw): return sha256(raw).hexdigest()


def read(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= CAP, 'bounded regular packet file')
    raw = path.read_bytes(); need(len(raw) == path.stat().st_size and len(raw) <= CAP, 'packet file drift')
    return raw


def load(packet, helper, *, pin, version, labels, packager):
    packet = Path(packet); need(packet.is_dir() and not packet.is_symlink(), 'regular packet directory')
    raw = read(packet / 'manifest.json'); need((len(raw), digest(raw)) == pin, 'joint CPU literal packet pin: manifest.json')
    manifest = helper.decode(raw); records = manifest['archives']
    need(manifest['version'] == version + '-package-v1' and manifest['native_calls_during_packaging'] == 0 and
         manifest['archived_source_executed'] is False and manifest['limits'] ==
         {'member_bytes': CAP, 'archive_bytes': CAP, 'expanded_bytes': EXPANDED}, 'packet schema/caps')
    need(len(records) == len(labels) and {r['file'] for r in records} == {label + '.zip' for label in labels} and
         {p.name for p in packet.iterdir()} == {'manifest.json', *(r['file'] for r in records)}, 'exact flat packet inventory')
    loaded = {}; pins = {}; total = 0
    for record in records:
        name = helper.safe_name(record['file']); raw = read(packet / name)
        need((len(raw), digest(raw)) == (record['bytes'], record['sha256']), 'joint CPU literal packet pin: ' + name)
        pins[name] = digest(raw); files = {}; folded = set()
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist(); expanded = sum(i.file_size for i in infos); total += expanded
            need(not archive.comment and len(infos) == record['members'] <= 16384 and expanded == record['expanded_bytes'] and total <= EXPANDED, 'ZIP count/expansion cap')
            for info in infos:
                member = helper.safe_name(info.filename); mode = info.external_attr >> 16
                need(member not in files and member.casefold() not in folded and info.create_system == 3 and
                     stat.S_ISREG(mode) and not stat.S_ISLNK(mode) and not info.is_dir() and not info.flag_bits & 1 and
                     not info.extra and not info.comment and info.compress_type == zipfile.ZIP_DEFLATED and
                     0 <= info.file_size <= CAP, 'safe regular archive member')
                folded.add(member.casefold())
                with archive.open(info) as stream: body = stream.read(CAP + 1)
                need(len(body) == info.file_size, 'bounded exact inflation'); files[member] = body
        need(digest(files['MANIFEST.json']) == record['manifest_sha256'], 'inner manifest pin')
        inner = helper.decode(files['MANIFEST.json']); entries = inner['members']; label = name[:-4]
        need(inner['version'] == version + '-archive-v1' and inner['archive'] == label and
             len(entries) == len(files) - 1 and len({e['path'] for e in entries}) == len(entries) and
             {e['path'] for e in entries} == set(files) - {'MANIFEST.json'}, 'complete member inventory')
        for entry in entries:
            body = files[helper.safe_name(entry['path'])]
            need((len(body), digest(body)) == (entry['bytes'], entry['sha256']), 'exact member identity')
        loaded[label] = files
    need(total == manifest['stored_expanded_bytes'] and set(loaded) == set(labels), 'complete archive expansion/scope')
    objects = loaded['objects']; used = set(); refs = 0
    for label, files in loaded.items():
        if label == 'objects': continue
        for member in tuple(files):
            if not member.endswith('.ref.json'): continue
            ref = helper.decode(files[member]); original = helper.safe_name(ref['original_member']); obj = helper.safe_name(ref['object'])
            need(original + '.ref.json' == member and original not in files and obj in objects and
                 obj == ref['sha256'] + '.bin' and ref['encoding'] == 'Exact original bytes; shared content address only.', 'exact original-path reference')
            body = objects[obj]; need((len(body), digest(body)) == (ref['bytes'], ref['sha256']), 'exact pooled bytes')
            files[original] = body; del files[member]; used.add(obj); refs += 1
    need(used == set(objects) - {'MANIFEST.json'} and len(used) == manifest['exact_shared_objects'] and refs <= 16384, 'nonorphan bounded object pool')
    need(digest(loaded['builds'][packager]) == manifest['packager_sha256'], 'original packager identity')
    return manifest, loaded, pins

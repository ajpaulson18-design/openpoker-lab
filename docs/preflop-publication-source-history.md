# Historical preflop publication source identity

Saved count and exact-witness observations retain their original source maps
and raw bytes. A later clean main may contain a separately validated change to
CI orchestration. This does not change the observed calculation, but the old
saved-source guard also covered the workflow and therefore rejected replay.

The [JJ authenticator](../scripts/verify_preflop_jj_kk_basis_publication.py)
now authenticates the original workflow from an immutable LF archive and accepts
only its original LF identity or the single later workflow identity below. The
later workflow adds two native river test modules to its existing test command.
The workflow itself is preserved from main; this change does not edit it.

The transport and exact-witness source maps include the JJ authenticator, so
their saved-publication guards explicitly authenticate that helper's original
archived LF bytes and require its one exact current LF identity. The current
transport publication helper has the same sealed treatment for later count
publication. These exceptions are implemented in the
[source-history helper](../scripts/preflop_publication_source_history.py):

| Source | Original LF SHA-256 | Accepted later LF SHA-256 |
| --- | --- | --- |
| .github/workflows/native-fixed-street.yml | f707f54e8f0644bdddf12cf1de00826ef4bcf505dc11919749ae83c838dc6d66 | da2f20cda4e62d8edc70f9f81983c83e904ca14971ceced08e895fad5a1ee039 |
| scripts/verify_preflop_jj_kk_basis_publication.py | 56dd358774d3e49fdf5c54213dd706cc9b7135abbdec12f8181b18ffade0215f | 689d5c55e090973d684c0d683e51060eefcab6fae63a462eb957403dea2547ef |
| scripts/verify_preflop_three_rank_transport_publication.py | 7d5b74a502022b98a34c7b9a47744743b6ac49547fe962a9d1158ce7a5d8dc7b | 0f0b5a37bf3058352f65df35402ee742fa2ef50760dce348bead5be930fa124b |

The [workflow archive](../benchmarks/sources/preflop-publication-context-v1/native-fixed-street.yml.txt),
[JJ helper archive](../benchmarks/sources/preflop-publication-context-v1/verify_preflop_jj_kk_basis_publication.py.txt)
and [transport helper archive](../benchmarks/sources/preflop-publication-context-v1/verify_preflop_three_rank_transport_publication.py.txt)
contain the exact original normalized LF bytes, protected from checkout newline
conversion. Further edits, an unlisted calculation source, a changed archive,
or dirty current source reject verification. The existing four historical
documentation-context archives remain separately attested as before.

Current clean HEAD/status and actual current LF hashes are recorded before
and after saved replay. The transition receipt names both historical and
current identities and the archive. No source snapshot is rewritten, and the
compatibility tests do not substitute for an actual committed clean CLI replay.
This publication repair performs no count, candidate search, LP solve or
training and changes no shared solver kernel, production default or Coach.

"""R28 single-writer immutable batches; the atomic receipt is the commit point.

commit buffers terminal queries; flush publishes a short final batch explicitly.
Events and statuses are fsynced and read back before the receipt is published.
Reopen verifies all published batches; orphan blocks are retained but not counted.
Local same-directory atomic rename is required. This is not a hardware power-loss
certificate. The query plan, indexes and records are still memory-resident.
"""
import hashlib
import json
import math
import os
import time
import uuid
from pathlib import Path

SUCCESS = frozenset(('COMPLETED_WITH_ACCESS', 'COMPLETED_NO_ACCESS'))
STATES = SUCCESS | frozenset(('COMPUTATION_ERROR', 'NOT_RUN'))


class StoreError(ValueError):
    pass


class StoreCorruption(StoreError):
    pass


class StoreConflict(StoreError):
    pass


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _window(spec):
    value = spec.get('window_epsec', spec.get('query_window_epsec'))
    if not isinstance(value, list) or len(value) != 2:
        raise StoreError('Query requires explicit [start, stop] window_epsec')
    if not all(type(v) in (int, float) and math.isfinite(v) for v in value) or value[0] >= value[1]:
        raise StoreError('Invalid query window')
    return value


class Store:
    """Append-only terminal results. Error is committed but never completed.

    The single-writer contract is explicit. A buffered result is not committed
    until its receipt has been atomically published. Repeated equal inputs are
    idempotent; conflicting results or duplicate IDs across batches are errors.
    """
    schema = 'R28_QUERY_BATCHES_V1'

    def __init__(self, folder, metadata=None, query_specs=None, batch_size=None):
        started = time.perf_counter()
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.bytes_written = self.bytes_read = 0
        self.files_written = self.file_open_count = self.fsync_count = 0
        self.commit_wall_s = self.flush_wall_s = 0.0
        self.idempotent_commits = 0
        self.records = {}
        self.pending = {}
        self.receipts = []
        self._spec_by_id = {}
        self._ordered_ids = []
        self.closed = False
        for subdir in ('events', 'statuses', 'batches'):
            (self.folder / subdir).mkdir(exist_ok=True)
        meta_path = self.folder / 'metadata.json'
        existing_meta = self._read_json(meta_path) if meta_path.is_file() else None
        if metadata is None:
            if existing_meta is None:
                raise StoreError('New store requires metadata')
            metadata = existing_meta.get('metadata')
        if batch_size is None:
            batch_size = existing_meta.get('batch_size') if existing_meta else 64
        if type(batch_size) is not int or batch_size < 1:
            raise StoreError('batch_size must be a positive integer')
        self.batch_size = batch_size
        self.metadata = json.loads(encode(metadata))
        self.metadata_sha256 = digest(self.metadata)
        meta_doc = dict(schema=self.schema, metadata=self.metadata,
                        metadata_sha256=self.metadata_sha256, batch_size=batch_size)
        self._publish(meta_path, encode(meta_doc))
        specs_path = self.folder / 'queries.json'
        if query_specs is None:
            if not specs_path.is_file():
                raise StoreError('New store requires query_specs')
            query_specs = self._read_json(specs_path).get('query_specs')
        if not isinstance(query_specs, list):
            raise StoreError('query_specs must be an ordered list')
        self.query_specs = json.loads(encode(query_specs))
        semantic_ids = set()
        for spec in self.query_specs:
            if not isinstance(spec, dict) or any(type(spec.get(k)) is not str or not spec[k] for k in ('point_id', 'sat_id')):
                raise StoreError('Query requires nonempty point_id and sat_id strings')
            window = _window(spec)
            key = (spec['point_id'], spec['sat_id'], tuple(window))
            if key in semantic_ids:
                raise StoreError('Duplicate satellite-point-window query')
            semantic_ids.add(key)
            qid = self.query_id(spec)
            if qid in self._spec_by_id:
                raise StoreError('Duplicate query ID')
            self._spec_by_id[qid] = spec
            self._ordered_ids.append(qid)
        specs_doc = dict(schema=self.schema, metadata_sha256=self.metadata_sha256,
                         query_specs=self.query_specs, query_ids=self._ordered_ids)
        self.query_table_sha256 = digest(specs_doc)
        self._publish(specs_path, encode(specs_doc))
        self.fixed_bytes = meta_path.stat().st_size + specs_path.stat().st_size
        self._recover()
        self.initialization_wall_s = time.perf_counter() - started

    def _read_bytes(self, path):
        self.file_open_count += 1
        try:
            with path.open('rb') as stream:
                data = stream.read()
            self.bytes_read += len(data)
            return data
        except OSError as exc:
            raise StoreCorruption('Unreadable block: ' + str(path)) from exc

    def _read_json(self, path):
        try:
            value = json.loads(self._read_bytes(path))
        except (ValueError, UnicodeError) as exc:
            raise StoreCorruption('Unreadable JSON block: ' + str(path)) from exc
        if type(value) is not dict:
            raise StoreCorruption('Block must be JSON object: ' + str(path))
        return value

    def _publish(self, path, data):
        if path.exists():
            if self._read_bytes(path) != data:
                raise StoreConflict('Conflicting immutable content: ' + str(path))
            return False
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
        try:
            self.file_open_count += 1
            with temp.open('xb') as stream:
                written = stream.write(data)
                self.bytes_written += written
                stream.flush()
                os.fsync(stream.fileno())
                self.fsync_count += 1
            if path.exists():
                if self._read_bytes(path) != data:
                    raise StoreConflict('Concurrent conflicting publisher: ' + str(path))
                return False
            os.replace(temp, path)
            self.files_written += 1
            return True
        finally:
            if temp.exists():
                temp.unlink()

    def query_id(self, spec):
        clean = {k: v for k, v in spec.items() if k != 'query_id'}
        qid = digest(dict(schema=self.schema, metadata_sha256=self.metadata_sha256,
                          query=clean))
        if 'query_id' in spec and spec['query_id'] != qid:
            raise StoreError('Supplied query_id differs from stable query identity')
        return qid

    def _qid(self, spec_or_id):
        qid = spec_or_id if isinstance(spec_or_id, str) else self.query_id(spec_or_id)
        if qid not in self._spec_by_id:
            raise StoreError('Unknown query identity: ' + str(qid))
        return qid

    def committed(self, spec_or_id):
        return self._qid(spec_or_id) in self.records

    def completed(self, spec_or_id):
        row = self.records.get(self._qid(spec_or_id))
        return row is not None and row['status']['computation_status'] in SUCCESS

    def _prepare(self, qid, events, status):
        spec = self._spec_by_id[qid]
        window = _window(spec)
        if type(events) is not list or type(status) is not dict:
            raise StoreError('Events must be list and status must be dict')
        status = dict(status)
        state = status.get('computation_status')
        if state not in STATES or state == 'NOT_RUN':
            raise StoreError('Only terminal Access or explicit error states may commit')
        for key in ('point_id', 'sat_id'):
            if key in status and status[key] != spec[key]:
                raise StoreError('Status identity mismatch: ' + key)
            status[key] = spec[key]
        if 'query_id' in status and status['query_id'] != qid:
            raise StoreError('Status query_id mismatch')
        status['query_id'] = qid
        for key in ('sensor_object_path', 'protocol_sha256', 'source_sha256', 'point_table_sha256'):
            if key in spec and key in status and status[key] != spec[key]:
                raise StoreError('Status source binding mismatch: ' + key)
        if 'query_window_epsec' in status and encode(status['query_window_epsec']) != encode(window):
            # Equal int/float physical values are valid; booleans are never numbers.
            supplied = status['query_window_epsec']
            if not isinstance(supplied, list) or len(supplied) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in supplied) or supplied != window:
                raise StoreError('Status window mismatch')
        status['query_window_epsec'] = window
        declared = status.get('raw_interval_count', len(events))
        if type(declared) is not int or declared != len(events):
            raise StoreError('Status event count must be exact integer')
        if state in SUCCESS and (state == 'COMPLETED_NO_ACCESS') != (not events):
            raise StoreError('Access state conflicts with events')
        status['raw_interval_count'] = declared
        seen = set()
        for event in events:
            if type(event) is not dict:
                raise StoreError('Event must be mapping')
            for key in ('point_id', 'sat_id'):
                if event.get(key) != spec[key]:
                    raise StoreError('Event identity mismatch: ' + key)
            if event.get('query_id') != qid:
                raise StoreError('Event query_id mismatch')
            for key in ('sensor_object_path', 'protocol_sha256', 'source_sha256', 'point_table_sha256'):
                if key in spec and event.get(key) != spec[key]:
                    raise StoreError('Event source binding mismatch: ' + key)
            if 'sensor_object_path' in spec and event.get('sensor_id') != spec['sensor_object_path'].split('/')[-1]:
                raise StoreError('Event sensor ID differs from declared camera path')
            if 'query_window_epsec' in event:
                supplied = event['query_window_epsec']
                if type(supplied) is not list or len(supplied) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in supplied) or supplied != window:
                    raise StoreError('Event query window mismatch')
            if 'solver_sha256' in status and event.get('event_solver_config_sha256') != status['solver_sha256']:
                raise StoreError('Event solver binding differs from query status')
            st, sp = event.get('start_epsec'), event.get('stop_epsec')
            if not all(type(v) in (int, float) and math.isfinite(v) for v in (st, sp)) or not window[0] <= st <= sp <= window[1]:
                raise StoreError('Invalid event interval')
            identity = (event.get('sensor_id'), st, sp)
            if identity in seen:
                raise StoreError('Duplicate raw interval identity')
            seen.add(identity)
        return json.loads(encode(events)), json.loads(encode(status))

    def _recover(self):
        for number, path in enumerate(sorted((self.folder / 'batches').glob('*.json'))):
            receipt = self._read_json(path)
            qids = receipt.get('query_ids')
            batch_id = receipt.get('batch_id')
            if type(qids) is not list or not qids or len(qids) > self.batch_size or any(type(q) is not str or q not in self._spec_by_id for q in qids) or len(set(qids)) != len(qids):
                raise StoreCorruption('Invalid batch query IDs')
            if any(q in self.records for q in qids):
                raise StoreCorruption('Duplicate query across committed batches')
            if type(batch_id) is not str or path.name != batch_id + '.json' or not batch_id.startswith(f'{number:08d}-'):
                raise StoreCorruption('Incorrectly named or discontinuous receipt')
            if receipt.get('schema') != self.schema or receipt.get('metadata_sha256') != self.metadata_sha256 or receipt.get('query_table_sha256') != self.query_table_sha256:
                raise StoreCorruption('Batch identity binding mismatch')
            if receipt.get('query_spec_sha256') != [digest(self._spec_by_id[q]) for q in qids]:
                raise StoreCorruption('Query specification binding mismatch')
            if type(receipt.get('batch_query_count')) is not int or receipt['batch_query_count'] != len(qids):
                raise StoreCorruption('Batch query count mismatch')
            blocks = {}
            for kind in ('events', 'statuses'):
                expected_rel = kind + '/' + batch_id + '.json'
                entry = receipt.get('blocks', {}).get(kind, {})
                if entry.get('relative_path') != expected_rel:
                    raise StoreCorruption('Invalid block path in receipt')
                data = self._read_bytes(self.folder / expected_rel)
                if type(entry.get('size_bytes')) is not int or len(data) != entry['size_bytes'] or _sha_bytes(data) != entry.get('sha256'):
                    raise StoreCorruption('Committed block hash mismatch: ' + expected_rel)
                try:
                    block = json.loads(data)
                except (ValueError, UnicodeError) as exc:
                    raise StoreCorruption('Unreadable committed JSON: ' + expected_rel) from exc
                if type(block) is not dict or block.get('schema') != self.schema or block.get('query_ids') != qids or block.get('metadata_sha256') != self.metadata_sha256:
                    raise StoreCorruption('Block identity mismatch')
                values = block.get(kind)
                if type(values) is not list or len(values) != len(qids):
                    raise StoreCorruption('Block query count mismatch')
                blocks[kind] = values
            prepared = []
            for i, qid in enumerate(qids):
                try:
                    events, status = self._prepare(qid, blocks['events'][i], blocks['statuses'][i])
                except StoreError as exc:
                    raise StoreCorruption('Invalid committed query: ' + qid) from exc
                prepared.append((qid, events, status))
            expected = self._receipt_assertions(prepared)
            for key, value in expected.items():
                if encode(receipt.get(key)) != encode(value):
                    raise StoreCorruption('Receipt assertion mismatch: ' + key)
            content_id = digest(dict(query_ids=qids, events=blocks['events'], statuses=blocks['statuses']))
            if batch_id != f'{number:08d}-{content_id}':
                raise StoreCorruption('Batch content identity mismatch')
            self.receipts.append(receipt)
            for qid, events, status in prepared:
                self.records[qid] = dict(events=events, status=status, receipt=receipt)

    @staticmethod
    def _receipt_assertions(prepared):
        return dict(event_counts=[len(e) for _, e, _ in prepared],
                    completion_states=[s['computation_status'] for _, _, s in prepared],
                    complete=[s['computation_status'] in SUCCESS for _, _, s in prepared],
                    event_count=sum(len(e) for _, e, _ in prepared))

    def commit(self, query_spec, events, status):
        if self.closed:
            raise StoreError('Store is closed')
        started = time.perf_counter()
        qid = self._qid(query_spec)
        events, status = self._prepare(qid, events, status)
        old = self.records.get(qid, self.pending.get(qid))
        if old is not None:
            if encode(old['events']) != encode(events) or encode(old['status']) != encode(status):
                raise StoreConflict('Different result for existing query ' + qid)
            self.idempotent_commits += 1
            return dict(query_id=qid, newly_committed=False, pending=qid in self.pending, receipt=old.get('receipt'))
        self.pending[qid] = dict(events=events, status=status)
        receipt = self.flush() if len(self.pending) >= self.batch_size else None
        self.commit_wall_s += time.perf_counter() - started
        return dict(query_id=qid, newly_committed=receipt is not None, pending=qid in self.pending, receipt=receipt)

    def flush(self):
        if self.closed:
            raise StoreError('Store is closed')
        if not self.pending:
            return None
        started = time.perf_counter()
        qids = list(self.pending)
        prepared = [(qid, self.pending[qid]['events'], self.pending[qid]['status']) for qid in qids]
        event_rows = [e for _, e, _ in prepared]
        status_rows = [s for _, _, s in prepared]
        content_id = digest(dict(query_ids=qids, events=event_rows, statuses=status_rows))
        batch_id = f'{len(self.receipts):08d}-{content_id}'
        blocks = {}
        for kind, values in (('events', event_rows), ('statuses', status_rows)):
            data = encode(dict(schema=self.schema, query_ids=qids, metadata_sha256=self.metadata_sha256, **{kind: values}))
            rel = kind + '/' + batch_id + '.json'
            self._publish(self.folder / rel, data)
            # Actual disk readback before the commit point, not an in-memory hash.
            readback = self._read_bytes(self.folder / rel)
            if readback != data:
                raise StoreCorruption('Published block failed readback: ' + rel)
            blocks[kind] = dict(relative_path=rel, size_bytes=len(data), sha256=_sha_bytes(readback))
        receipt = dict(schema=self.schema, batch_id=batch_id, query_ids=qids,
                       metadata_sha256=self.metadata_sha256, query_table_sha256=self.query_table_sha256,
                       query_spec_sha256=[digest(self._spec_by_id[q]) for q in qids], blocks=blocks,
                       batch_query_count=len(qids), **self._receipt_assertions(prepared))
        self._publish(self.folder / 'batches' / (batch_id + '.json'), encode(receipt))
        self.receipts.append(receipt)
        for qid, events, status in prepared:
            self.records[qid] = dict(events=events, status=status, receipt=receipt)
        self.pending.clear()
        self.flush_wall_s += time.perf_counter() - started
        return receipt

    def close(self):
        if not self.closed:
            self.flush()
            self.closed = True

    def snapshot(self):
        events, statuses = [], []
        for qid in self._ordered_ids:
            spec = self._spec_by_id[qid]
            row = self.records.get(qid)
            if row:
                events.extend(row['events'])
                statuses.append(row['status'])
            else:
                statuses.append(dict(query_id=qid, point_id=spec['point_id'], sat_id=spec['sat_id'],
                                     computation_status='NOT_RUN', raw_interval_count=None,
                                     query_window_epsec=_window(spec)))
        return json.loads(encode(dict(events=events, query_statuses=statuses, statuses=statuses,
                                      metadata=self.metadata, metadata_sha256=self.metadata_sha256)))

    def metrics(self):
        paths = [p for p in self.folder.rglob('*') if p.is_file()]
        published = [p for p in paths if p.suffix == '.json']
        committed_blocks = {entry['relative_path'] for receipt in self.receipts for entry in receipt['blocks'].values()}
        incomplete = [p.relative_to(self.folder).as_posix() for p in paths
                      if p.suffix == '.pending' or (p.parent.name in ('events', 'statuses') and p.relative_to(self.folder).as_posix() not in committed_blocks)]
        return dict(schema=self.schema, batch_size=self.batch_size, required_query_count=len(self._ordered_ids),
                    committed_query_count=len(self.records), pending_query_count=len(self.pending),
                    committed_batch_count=len(self.receipts), completed_query_count=sum(
                        r['status']['computation_status'] in SUCCESS for r in self.records.values()),
                    failed_query_count=sum(r['status']['computation_status']=='COMPUTATION_ERROR' for r in self.records.values()),
                    not_run_query_count=len(self._ordered_ids)-len(self.records),
                    session_written_bytes=self.bytes_written, session_read_bytes=self.bytes_read,
                    session_files_written=self.files_written, session_file_open_count=self.file_open_count,
                    session_fsync_count=self.fsync_count, actual_store_file_count=len(paths),
                    cumulative_published_bytes=sum(p.stat().st_size for p in published),
                    fixed_metadata_and_query_table_bytes=self.fixed_bytes,
                    event_status_receipt_bytes=sum(p.stat().st_size for p in published if p.parent != self.folder),
                    session_commit_wall_s=self.commit_wall_s, session_flush_wall_s=self.flush_wall_s,
                    initialization_wall_s=self.initialization_wall_s,
                    idempotent_commit_count=self.idempotent_commits, incomplete_blocks=sorted(incomplete),
                    persistence_semantics='Buffered queries; explicit short-tail flush; fsynced event/status disk readback before atomic immutable batch receipt',
                    io_measurement_scope='This Store instance Python content opens/read bytes/temp-file write bytes/fsync; includes initialization,recovery,pre-receipt readback. Excludes caller I/O, directory/stat metadata, OS cache/physical I/O and other Store instances.',
                    memory_scope='Query plan, ID indexes and all committed records resident; snapshot deep-copies JSON; full-scale upper bound unmeasured',
                    writer_scope='Single collector writer; local filesystem; fsync does not certify arbitrary hardware power-loss durability')

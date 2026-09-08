"""Bound public event payloads without dropping occurrences or descriptions."""
import json
from pathlib import Path

MAX_CHUNK_BYTES = 512 * 1024


def split_events(events, descriptions, max_bytes=MAX_CHUNK_BYTES):
    """Keep each event intact; an unusually large single event may exceed the cap."""
    chunks, current, size = [], [], 2
    for event in events:
        description = descriptions.get(str(event['id']), descriptions.get(event['id'], ''))
        cost = len(json.dumps([event, description], ensure_ascii=False,
                              separators=(',', ':')).encode('utf-8')) + 1
        if current and size + cost > max_bytes:
            chunks.append(current)
            current, size = [], 2
        current.append(event)
        size += cost
    if current:
        chunks.append(current)
    return chunks


def write_remainder_chunks(output_dir, events, descriptions):
    output = Path(output_dir)
    names = []
    for i, chunk in enumerate(split_events(events, descriptions)):
        name = f'remainder{i}'
        names.append(name)
        desc = {}
        for e in chunk:
            value = descriptions.get(str(e['id']), descriptions.get(e['id']))
            if value is not None:
                desc[e['id']] = value
        for filename, data in [(f'events.{name}.json', chunk),
                               (f'events.{name}.desc.json', desc)]:
            (output / filename).write_text(json.dumps(data, ensure_ascii=False,
                                                      separators=(',', ':')), encoding='utf-8')
    # Keep legacy remainder files: cached older app bundles still request them.
    return names


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Partition an existing public export without DB access')
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    def read(name):
        return json.loads((args.directory / name).read_text(encoding='utf-8'))
    manifest = read('manifest.json')
    manifest['remainderChunks'] = write_remainder_chunks(
        args.directory, read('events.remainder.json'), read('events.remainder.desc.json'))
    (args.directory / 'manifest.json').write_text(json.dumps(manifest, separators=(',', ':')),
                                                encoding='utf-8')
    print(f"Wrote {len(manifest['remainderChunks'])} remainder chunks")

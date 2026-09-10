"""Uploads must not expose partial files or mark failed transfers complete."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from upload_public_html import upload_directory, upload_file


class AtomicUploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'events.day0.json'
        self.path.write_bytes(b'[{"id":1}]')

    def test_live_file_changes_only_after_complete_transfer(self):
        ftp = Mock()
        files = {self.path.name: b'[{"id":0}]'}

        def store(command, stream):
            target = command.removeprefix('STOR ')
            self.assertNotEqual(target, self.path.name)
            files[target] = stream.read(3)
            self.assertEqual(files[self.path.name], b'[{"id":0}]')
            files[target] += stream.read()

        def rename(source, target):
            self.assertEqual(files[source], self.path.read_bytes())
            files[target] = files.pop(source)

        ftp.storbinary.side_effect = store
        ftp.rename.side_effect = rename
        upload_file(ftp, self.path, self.path.name)
        self.assertEqual(files, {self.path.name: b'[{"id":1}]'})
        ftp.delete.assert_not_called()

    def test_failed_transfer_never_replaces_live_file(self):
        ftp = Mock()
        ftp.storbinary.side_effect = OSError('interrupted')
        with self.assertRaisesRegex(OSError, 'interrupted'):
            upload_file(ftp, self.path, self.path.name)
        ftp.rename.assert_not_called()
        temporary = ftp.storbinary.call_args.args[0].removeprefix('STOR ')
        ftp.delete.assert_called_once_with(temporary)
        self.assertNotEqual(temporary, self.path.name)

    def test_failed_rename_has_no_destructive_fallback(self):
        ftp = Mock()
        ftp.rename.side_effect = OSError('rename refused')
        with self.assertRaisesRegex(OSError, 'rename refused'):
            upload_file(ftp, self.path, self.path.name)
        self.assertEqual(ftp.storbinary.call_count, 1)
        ftp.delete.assert_called_once_with(ftp.rename.call_args.args[0])

    def test_failed_publication_stops_and_does_not_record_new_hash(self):
        ftp = Mock()
        ftp.rename.side_effect = OSError('rename refused')
        previous = {'public_html/events.day0.json': 'old-hash'}
        current = {}
        with self.assertRaises(OSError):
            upload_directory(ftp, self.directory.name, 'public_html',
                             previous_state=previous, new_state=current)
        self.assertEqual(current, {})
        self.assertEqual(previous['public_html/events.day0.json'], 'old-hash')


if __name__ == '__main__':
    unittest.main()

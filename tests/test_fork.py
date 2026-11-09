import json
import os
import pathlib
import socket
import struct
import subprocess
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = '''interface IBase
{
    void Base();
}
interface IFoo : IBase, IXOutside
{
    int Bonus(int Value) { return Value + 1; }
    void Call();
}
class UReceiver : UObject, IFoo
{
    void Test() { this.Bonus(1); }
}
void Test(IFoo Captured)
{
    Single.BindLambda([IFoo Captured](int Argument) { Captured.Call(); Print(Argument); });
    Multi.AddLambda([IBase Captured](int Argument) { Captured.Base(); Print(Captured); Print(Argument); });
    Values.Sort([IFoo Captured](int Argument, int B) { Captured.Call(); return Argument < B; });
    Values.StableSort([IFoo Captured](int Argument, int B) { return Argument < B; });
    Values.KeySort([IFoo Captured](int Argument, int B) { return Argument < B; });
    Values.ValueSort([IFoo Captured](int Argument, int B) { return Argument < B; });
    Cast<IFoo>(Object).Call();
}
interface UWrong {}
'''

def debug_server():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 27099))
        server.listen()
        server.settimeout(15)
        conn, _ = server.accept()
        with conn:
            conn.recv(4096)
            conn.sendall(struct.pack('<IB', 0, 26))
            time.sleep(10)

class ForkLSP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        threading.Thread(target=debug_server, daemon=True).start()
        cls.p = subprocess.Popen(['node', str(ROOT.parent / 'language-server/dist/server.js'), '--stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cls.seq = 0
        cls.diagnostics = {}
        cls.uri = (ROOT / 'fork-test.as').as_uri()
        cls.request('initialize', {'processId': os.getpid(), 'rootUri': ROOT.as_uri(), 'rootPath': str(ROOT), 'capabilities': {}, 'workspaceFolders': None})
        cls.notify('initialized', {})
        time.sleep(2)
        cls.notify('textDocument/didOpen', {'textDocument': {'uri': cls.uri, 'languageId': 'soloas-angelscript', 'version': 1, 'text': SOURCE}})
        time.sleep(2)

    @classmethod
    def send(cls, obj):
        data = json.dumps(obj).encode()
        cls.p.stdin.write(b'Content-Length: ' + str(len(data)).encode() + b'\r\n\r\n' + data)
        cls.p.stdin.flush()

    @classmethod
    def notify(cls, method, params):
        cls.send({'jsonrpc': '2.0', 'method': method, 'params': params})

    @classmethod
    def request(cls, method, params):
        cls.seq += 1
        ident = cls.seq
        cls.send({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params})
        while True:
            headers = b''
            while not headers.endswith(b'\r\n\r\n'):
                char = cls.p.stdout.read(1)
                if not char:
                    raise RuntimeError('Language server exited')
                headers += char
            length = int(next(x for x in headers.decode().split('\r\n') if x.lower().startswith('content-length:')).split(':')[1])
            response = json.loads(cls.p.stdout.read(length))
            if response.get('method') == 'textDocument/publishDiagnostics':
                cls.diagnostics[response['params']['uri']] = response['params']['diagnostics']
            if response.get('id') == ident:
                if 'error' in response:
                    raise AssertionError(response['error'])
                return response.get('result')

    @classmethod
    def tearDownClass(cls):
        cls.request('shutdown', None)
        cls.notify('exit', None)
        cls.p.wait(timeout=5)

    def completion(self, line, fragment):
        text = SOURCE.splitlines()[line]
        character = text.index(fragment) + len(fragment)
        result = self.request('textDocument/completion', {'textDocument': {'uri': self.uri}, 'position': {'line': line, 'character': character}})
        return [item['label'] for item in (result or [])]

    def test_interface_naming(self):
        self.request('textDocument/documentSymbol', {'textDocument': {'uri': self.uri}})
        messages = [d['message'] for d in self.diagnostics.get(self.uri, [])]
        self.assertFalse(any("Type 'IFoo' violates" in m or "Type 'IBase' violates" in m for m in messages), messages)
        self.assertTrue(any("Type 'UWrong' violates" in m and 'IWrong' in m for m in messages), messages)

    def test_outline(self):
        symbols = self.request('textDocument/documentSymbol', {'textDocument': {'uri': self.uri}})
        interface = next(x for x in symbols if x['name'] == 'IFoo')
        self.assertEqual(interface['kind'], 11)
        self.assertEqual({x['name'] for x in interface['children']}, {'Bonus(…)', 'Call()'})
        self.assertEqual([x['name'] for x in symbols].count('Test(…)'), 1)

    def test_inheritance_and_cast(self):
        cast_line = next(i for i, line in enumerate(SOURCE.splitlines()) if 'Cast<IFoo>' in line)
        self.assertIn('Bonus', self.completion(11, 'this.'))
        self.assertIn('Call', self.completion(cast_line, 'Cast<IFoo>(Object).'))
        self.assertIn('Base', self.completion(cast_line, 'Cast<IFoo>(Object).'))
        self.assertIn('External', self.completion(cast_line, 'Cast<IFoo>(Object).'))

    def test_lambda_scopes(self):
        lines = SOURCE.splitlines()
        for line in (15, 16, 17):
            with self.subTest(line=line):
                method = 'Base' if line == 16 else 'Call'
                self.assertIn(method, self.completion(line, 'Captured.'))
                if line == 16:
                    self.assertNotIn('Call', self.completion(line, 'Captured.'))
                self.assertIn('Argument', self.completion(line, 'Print(Arg') if line != 17 else self.completion(line, 'return Arg'))
        for index, text in enumerate(lines):
            if any(name in text for name in ('StableSort(', 'KeySort(', 'ValueSort(')):
                self.assertIn('Argument', self.completion(index, 'return Arg'))

    def test_lambda_capture_completion_deduplicated(self):
        line = 16
        character = SOURCE.splitlines()[line].index('Print(Captured)') + len('Print(Cap')
        items = self.request('textDocument/completion', {'textDocument': {'uri': self.uri}, 'position': {'line': line, 'character': character}})
        matches = [item for item in items if item['label'] == 'Captured']
        self.assertEqual(len(matches), 1, matches)
        self.assertEqual(matches[0]['labelDetails']['description'], 'IBase')

    def test_argument_hover(self):
        line = 15
        character = SOURCE.splitlines()[line].index('Print(Argument)') + len('Print(Arg')
        result = self.request('textDocument/hover', {'textDocument': {'uri': self.uri}, 'position': {'line': line, 'character': character}})
        self.assertIn('int Argument', json.dumps(result))

    def test_z_incremental_edit(self):
        updated = SOURCE.replace('int Argument', 'int Changed').replace('Print(Argument)', 'Print(Changed)').replace('return Argument', 'return Changed')
        self.notify('textDocument/didChange', {'textDocument': {'uri': self.uri, 'version': 2}, 'contentChanges': [{'text': updated}]})
        time.sleep(0.5)
        line = 15
        character = updated.splitlines()[line].index('Print(Changed)') + len('Print(Cha')
        result = self.request('textDocument/completion', {'textDocument': {'uri': self.uri}, 'position': {'line': line, 'character': character}})
        labels = [item['label'] for item in (result or [])]
        self.assertIn('Changed', labels)
        self.assertNotIn('Argument', labels)

if __name__ == '__main__':
    unittest.main(verbosity=2)
